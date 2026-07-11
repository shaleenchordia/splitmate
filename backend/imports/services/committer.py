"""Commit a staged batch: apply each row's final (reviewer-approved)
actions and write ledger records. Runs in a single transaction — a batch
commits fully or not at all.

Commit is refused while any review-severity anomaly is unresolved:
the reviewer must approve or override every proposal first (Meera's
requirement). Info/warning proposals apply as proposed unless overridden.
"""
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from django.db import transaction
from django.utils import timezone

from expenses.models import Expense, ExpenseSplit, GroupMember, Settlement
from expenses.services import splits as split_service

from ..models import ImportAnomaly, ImportRow
from .pipeline import parse_split_details


class CommitError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def unresolved_reviews(batch):
    return ImportAnomaly.objects.filter(
        row__batch=batch,
        severity=ImportAnomaly.Severity.REVIEW,
        resolved_action__isnull=True,
    )


def _apply_actions(row):
    """Fold every anomaly's final action into a working copy of parsed.

    Returns (parsed_dict, disposition) where disposition is
    'skip' | 'expense' | 'settlement'.
    """
    parsed = dict(row.parsed)
    parsed["participants"] = [dict(p) for p in row.parsed.get("participants", [])]
    disposition = parsed.get("kind", "expense")
    new_members = []

    for anomaly in row.anomalies.all():
        action = anomaly.final_action()
        kind = action.get("action")
        if kind == "skip_row":
            return parsed, "skip", []
        elif kind == "set_date":
            parsed["date"] = action["date"]
        elif kind == "set_payer":
            parsed["paid_by"] = action["name"]
        elif kind == "set_currency":
            parsed["currency"] = action["currency"]
        elif kind == "set_amount_minor":
            parsed["amount_minor"] = action["amount_minor"]
        elif kind == "convert_currency":
            parsed["fx_rate"] = action["rate"]
        elif kind in ("convert_to_settlement", "record_as_settlement"):
            disposition = "settlement"
            parsed["payee"] = action.get("payee") or parsed.get("payee") or (
                parsed["participants"][0]["name"] if parsed["participants"] else None
            )
            if action.get("payer"):
                parsed["paid_by"] = action["payer"]
        elif kind == "set_split_type":
            parsed["split_type"] = action["split_type"]
        elif kind == "normalize_percents":
            total = sum(Decimal(p["percent"]) for p in parsed["participants"] if "percent" in p)
            if total > 0:
                for p in parsed["participants"]:
                    if "percent" in p:
                        p["percent"] = str(
                            (Decimal(p["percent"]) * 100 / total).quantize(Decimal("0.0001"))
                        )
        elif kind == "remove_participant":
            parsed["participants"] = [
                p for p in parsed["participants"] if p["name"] != action["name"]
            ]
        elif kind == "add_member":
            new_members.append(action)
        elif kind in ("keep", "map_name"):
            pass
        else:
            raise CommitError([f"Row {row.row_number}: unknown action '{kind}'"])
    return parsed, disposition, new_members


def _member_for(group, name, member_cache, new_member_specs):
    key = name.strip().lower()
    if key in member_cache:
        return member_cache[key]
    spec = next(
        (s for s in new_member_specs if s["name"].strip().lower() == key), {}
    )
    member = GroupMember.objects.create(
        group=group,
        name=name,
        joined_on=date.fromisoformat(spec["joined_on"]) if spec.get("joined_on") else None,
        is_guest=spec.get("is_guest", False),
    )
    member_cache[key] = member
    return member


@transaction.atomic
def commit_batch(batch, user):
    if batch.status != batch.Status.STAGED:
        raise CommitError([f"Batch is {batch.status}, not staged."])
    pending = unresolved_reviews(batch)
    if pending.exists():
        raise CommitError(
            [
                f"Row {a.row.row_number}: {a.code} needs a decision before commit"
                for a in pending.select_related("row")
            ]
        )

    member_cache = {
        m.name.strip().lower(): m for m in batch.group.members.all()
    }
    errors = []
    results = []

    rows = list(batch.rows.prefetch_related("anomalies"))
    plans = []
    for row in rows:
        parsed, disposition, new_members = _apply_actions(row)
        plans.append((row, parsed, disposition, new_members))
        if disposition == "skip":
            continue
        if not parsed.get("date"):
            errors.append(f"Row {row.row_number}: no usable date")
        if not parsed.get("paid_by"):
            errors.append(f"Row {row.row_number}: no payer assigned")
        if disposition == "expense" and not parsed.get("participants"):
            errors.append(f"Row {row.row_number}: no participants left in split")
        if parsed.get("amount_minor") in (None, 0) and disposition != "skip":
            errors.append(f"Row {row.row_number}: amount is zero or invalid")
    if errors:
        raise CommitError(errors)

    for row, parsed, disposition, new_members in plans:
        if disposition == "skip":
            row.kind = ImportRow.Kind.SKIP
            row.approved = True
            row.save()
            results.append({"row": row.row_number, "disposition": "skipped"})
            continue

        payer = _member_for(batch.group, parsed["paid_by"], member_cache, new_members)
        amount_minor = parsed["amount_minor"]
        rate = Decimal(parsed.get("fx_rate", "1"))
        if parsed["currency"] == batch.group.base_currency:
            rate = Decimal("1")
        amount_base_minor = int(
            (Decimal(amount_minor) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
        )

        if disposition == "settlement":
            payee = _member_for(batch.group, parsed["payee"], member_cache, new_members)
            settlement = Settlement.objects.create(
                group=batch.group,
                payer=payer,
                payee=payee,
                amount_base_minor=amount_base_minor,
                date=date.fromisoformat(parsed["date"]),
                note=parsed["description"],
                created_by=user,
                source_batch=batch,
                source_row_number=row.row_number,
            )
            row.kind = ImportRow.Kind.SETTLEMENT
            row.created_settlement = settlement
            row.approved = True
            row.save()
            results.append({"row": row.row_number, "disposition": "settlement", "id": settlement.id})
            continue

        split_type = parsed["split_type"]
        participants = parsed["participants"]
        # A reviewer switching split type (e.g. equal -> share on a
        # conflicting row) means detail values weren't attached at parse
        # time; recover them from the raw cell.
        if split_type in ("percentage", "share", "unequal"):
            needs = {"percentage": "percent", "share": "units", "unequal": "amount_minor"}[
                split_type
            ]
            if any(needs not in p for p in participants):
                details = parse_split_details(row.raw.get("split_details", "")) or []
                by_name = {n.strip().lower(): v for n, v, _ in details}
                for p in participants:
                    v = by_name.get(p["name"].strip().lower())
                    if v is not None:
                        if split_type == "percentage":
                            p["percent"] = str(v)
                        elif split_type == "share":
                            p["units"] = int(v)
                        else:
                            p["amount_minor"] = int(v * 100)

        member_ids = []
        split_participants = []
        for p in participants:
            m = _member_for(batch.group, p["name"], member_cache, new_members)
            member_ids.append(m.id)
            entry = {"member_id": m.id}
            if "percent" in p:
                entry["percent"] = Decimal(p["percent"])
            if "units" in p:
                entry["units"] = p["units"]
            if "amount_minor" in p:
                entry["amount_minor"] = p["amount_minor"]
            split_participants.append(entry)

        try:
            shares = split_service.compute_splits(
                split_type, amount_base_minor, split_participants
            )
        except split_service.SplitError as e:
            raise CommitError([f"Row {row.row_number}: {e}"])

        expense = Expense.objects.create(
            group=batch.group,
            description=parsed["description"],
            date=date.fromisoformat(parsed["date"]),
            paid_by=payer,
            currency=parsed["currency"],
            amount_minor=amount_minor,
            fx_rate=rate,
            amount_base_minor=amount_base_minor,
            split_type=split_type,
            notes=parsed.get("notes", ""),
            created_by=user,
            source_batch=batch,
            source_row_number=row.row_number,
        )
        for entry in split_participants:
            ExpenseSplit.objects.create(
                expense=expense,
                member_id=entry["member_id"],
                share_base_minor=shares[entry["member_id"]],
                input_percent=entry.get("percent"),
                input_share_units=entry.get("units"),
                input_amount_minor=entry.get("amount_minor"),
            )
        row.kind = ImportRow.Kind.EXPENSE
        row.created_expense = expense
        row.approved = True
        row.save()
        results.append({"row": row.row_number, "disposition": "expense", "id": expense.id})

    batch.status = batch.Status.COMMITTED
    batch.committed_at = timezone.now()
    batch.save()
    return results


def build_report(batch):
    """The import report: every anomaly, the action taken, and each row's
    final disposition. Available before commit (proposals) and after
    (final)."""
    rows_out = []
    counts = {"expense": 0, "settlement": 0, "skipped": 0}
    anomaly_count = 0
    for row in batch.rows.prefetch_related("anomalies"):
        anomalies = []
        for a in row.anomalies.all():
            anomaly_count += 1
            anomalies.append(
                {
                    "code": a.code,
                    "severity": a.severity,
                    "message": a.message,
                    "proposed_action": a.proposed_action,
                    "resolved_action": a.resolved_action,
                    "action_taken": a.final_action(),
                    "overridden": a.resolved_action is not None
                    and a.resolved_action != a.proposed_action,
                }
            )
        disposition = row.kind if batch.status == batch.Status.COMMITTED else "staged"
        if batch.status == batch.Status.COMMITTED:
            key = "skipped" if row.kind == ImportRow.Kind.SKIP else row.kind
            counts[key] = counts.get(key, 0) + 1
        rows_out.append(
            {
                "row_number": row.row_number,
                "raw": row.raw,
                "disposition": disposition,
                "created_expense_id": row.created_expense_id,
                "created_settlement_id": row.created_settlement_id,
                "anomalies": anomalies,
            }
        )
    return {
        "batch_id": batch.id,
        "file_name": batch.file_name,
        "status": batch.status,
        "group": batch.group.name,
        "fx_rates": batch.fx_rates,
        "created_at": batch.created_at.isoformat(),
        "committed_at": batch.committed_at.isoformat() if batch.committed_at else None,
        "total_rows": len(rows_out),
        "rows_with_anomalies": sum(1 for r in rows_out if r["anomalies"]),
        "total_anomalies": anomaly_count,
        "dispositions": counts if batch.status == batch.Status.COMMITTED else None,
        "rows": rows_out,
    }
