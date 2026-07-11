from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from django.conf import settings

from expenses.views import get_group_for

from .models import ImportAnomaly, ImportBatch, ImportRow
from .services import committer, pipeline

# Actions a reviewer is allowed to choose per anomaly. Anything else is
# rejected so the committer never sees an action it can't execute.
ALLOWED_ACTIONS = {
    "keep",
    "skip_row",
    "set_date",
    "set_payer",
    "set_currency",
    "set_amount_minor",
    "convert_currency",
    "convert_to_settlement",
    "record_as_settlement",
    "set_split_type",
    "normalize_percents",
    "remove_participant",
    "add_member",
    "map_name",
}


def batch_summary(batch):
    rows = list(batch.rows.prefetch_related("anomalies"))
    review_total = review_open = 0
    for r in rows:
        for a in r.anomalies.all():
            if a.severity == ImportAnomaly.Severity.REVIEW:
                review_total += 1
                if a.resolved_action is None:
                    review_open += 1
    return {
        "id": batch.id,
        "file_name": batch.file_name,
        "status": batch.status,
        "fx_rates": batch.fx_rates,
        "created_at": batch.created_at,
        "committed_at": batch.committed_at,
        "total_rows": len(rows),
        "rows_with_anomalies": sum(1 for r in rows if r.anomalies.all()),
        "review_needed": review_total,
        "review_open": review_open,
    }


def row_detail(row):
    return {
        "id": row.id,
        "row_number": row.row_number,
        "raw": row.raw,
        "parsed": row.parsed,
        "kind": row.kind,
        "needs_review": row.needs_review,
        "created_expense_id": row.created_expense_id,
        "created_settlement_id": row.created_settlement_id,
        "anomalies": [
            {
                "id": a.id,
                "code": a.code,
                "severity": a.severity,
                "message": a.message,
                "proposed_action": a.proposed_action,
                "resolved_action": a.resolved_action,
            }
            for a in row.anomalies.all()
        ],
    }


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def batch_list(request, group_id):
    group = get_group_for(request.user, group_id)
    if request.method == "GET":
        return Response(
            [batch_summary(b) for b in group.imports.order_by("-created_at")]
        )

    upload = request.FILES.get("file")
    if not upload:
        return Response({"detail": "Attach a CSV or XLSX as 'file'."}, status=400)
    fx_rates = dict(settings.DEFAULT_FX_RATES)
    if request.data.get("fx_rates"):
        import json

        try:
            fx_rates.update(json.loads(request.data["fx_rates"]))
        except (ValueError, TypeError):
            return Response({"detail": "fx_rates must be a JSON object."}, status=400)

    try:
        raw_rows = pipeline.read_rows(upload, upload.name)
    except pipeline.ImportFormatError as e:
        return Response({"detail": str(e)}, status=400)

    with transaction.atomic():
        batch = ImportBatch.objects.create(
            group=group,
            uploaded_by=request.user,
            file_name=upload.name,
            fx_rates={k: str(v) for k, v in fx_rates.items()},
        )
        pipeline.stage_batch(batch, raw_rows)
    return Response(batch_summary(batch), status=status.HTTP_201_CREATED)


def _get_batch(request, group_id, batch_id):
    group = get_group_for(request.user, group_id)
    return get_object_or_404(ImportBatch, pk=batch_id, group=group)


@api_view(["GET", "DELETE"])
def batch_detail(request, group_id, batch_id):
    batch = _get_batch(request, group_id, batch_id)
    if request.method == "DELETE":
        if batch.status == ImportBatch.Status.COMMITTED:
            return Response(
                {"detail": "Committed batches are permanent history."}, status=400
            )
        batch.status = ImportBatch.Status.DISCARDED
        batch.save()
        return Response(status=204)
    data = batch_summary(batch)
    data["rows"] = [row_detail(r) for r in batch.rows.prefetch_related("anomalies")]
    return Response(data)


@api_view(["POST"])
def resolve_anomaly(request, group_id, batch_id, anomaly_id):
    batch = _get_batch(request, group_id, batch_id)
    if batch.status != ImportBatch.Status.STAGED:
        return Response({"detail": "Batch is no longer staged."}, status=400)
    anomaly = get_object_or_404(ImportAnomaly, pk=anomaly_id, row__batch=batch)
    action = request.data.get("action")
    if action == "approve":
        anomaly.resolved_action = anomaly.proposed_action
    else:
        if not isinstance(request.data, dict) or action not in ALLOWED_ACTIONS:
            return Response(
                {"detail": f"action must be 'approve' or one of {sorted(ALLOWED_ACTIONS)}"},
                status=400,
            )
        anomaly.resolved_action = dict(request.data)
    anomaly.save()
    return Response(row_detail(anomaly.row))


@api_view(["POST"])
def approve_all(request, group_id, batch_id):
    """Accept every remaining proposal as-is (still an explicit human act)."""
    batch = _get_batch(request, group_id, batch_id)
    if batch.status != ImportBatch.Status.STAGED:
        return Response({"detail": "Batch is no longer staged."}, status=400)
    pending = ImportAnomaly.objects.filter(row__batch=batch, resolved_action__isnull=True)
    n = 0
    for a in pending:
        a.resolved_action = a.proposed_action
        a.save()
        n += 1
    return Response({"approved": n, **batch_summary(batch)})


@api_view(["POST"])
def redetect(request, group_id, batch_id):
    """Re-run detection (after member windows or FX rates changed).

    Prior decisions are preserved where the same anomaly (row + code)
    is found again.
    """
    batch = _get_batch(request, group_id, batch_id)
    if batch.status != ImportBatch.Status.STAGED:
        return Response({"detail": "Batch is no longer staged."}, status=400)
    if request.data.get("fx_rates"):
        rates = request.data["fx_rates"]
        if not isinstance(rates, dict):
            return Response({"detail": "fx_rates must be an object."}, status=400)
        batch.fx_rates = {**batch.fx_rates, **{k: str(v) for k, v in rates.items()}}
        batch.save()

    with transaction.atomic():
        old_resolutions = {
            (a.row.row_number, a.code): a.resolved_action
            for a in ImportAnomaly.objects.filter(
                row__batch=batch, resolved_action__isnull=False
            ).select_related("row")
        }
        raw_rows = [r.raw for r in batch.rows.all()]
        batch.rows.all().delete()
        pipeline.stage_batch(batch, raw_rows)
        restored = 0
        for a in ImportAnomaly.objects.filter(row__batch=batch).select_related("row"):
            key = (a.row.row_number, a.code)
            if key in old_resolutions:
                a.resolved_action = old_resolutions[key]
                a.save()
                restored += 1
    data = batch_summary(batch)
    data["resolutions_restored"] = restored
    return Response(data)


@api_view(["POST"])
def commit(request, group_id, batch_id):
    batch = _get_batch(request, group_id, batch_id)
    try:
        results = committer.commit_batch(batch, request.user)
    except committer.CommitError as e:
        return Response({"detail": "Commit blocked.", "errors": e.errors}, status=400)
    return Response({"results": results, **batch_summary(batch)})


@api_view(["GET"])
def report(request, group_id, batch_id):
    batch = _get_batch(request, group_id, batch_id)
    return Response(committer.build_report(batch))
