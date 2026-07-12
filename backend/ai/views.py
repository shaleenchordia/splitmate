"""AI endpoints. Every feature tries Gemini first and degrades to the
deterministic fallbacks in local.py, reporting which engine answered via
`source` so the UI can label the result. AI never writes to the ledger:
each endpoint returns a *proposal* the human confirms in the normal UI
(same philosophy as the import pipeline).
"""
from collections import defaultdict
from datetime import date

from django.db.models import Sum
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from expenses.models import Expense
from expenses.views import get_group_for
from imports.models import ImportAnomaly, ImportBatch
from imports.views import batch_summary

from . import gemini, local

# ------------------------------------------------------------------ status


@api_view(["GET"])
def status(request):
    return Response(
        {
            "gemini": gemini.available(),
            "model": gemini.model_name() if gemini.available() else None,
        }
    )


# ----------------------------------------------------------- smart add (NL)

EXPENSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "description": {"type": "STRING"},
        "date": {"type": "STRING", "description": "ISO date YYYY-MM-DD"},
        "amount": {"type": "NUMBER", "description": "major units, e.g. 450.50"},
        "currency": {"type": "STRING", "description": "3-letter code"},
        "paid_by": {"type": "STRING", "description": "member name or empty"},
        "split_type": {
            "type": "STRING",
            "enum": ["equal", "unequal", "percentage", "share"],
        },
        "participants": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "percent": {"type": "NUMBER"},
                    "units": {"type": "INTEGER"},
                    "amount": {"type": "NUMBER"},
                },
                "required": ["name"],
            },
        },
        "notes": {"type": "STRING"},
        "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["description", "split_type", "participants"],
}


def _parse_prompt(group, text):
    members = ", ".join(m.name for m in group.members.all())
    return f"""You turn one natural-language line about a shared expense into structured data.

Group members: {members}
Group base currency: {group.base_currency}
Today's date: {date.today().isoformat()}

Rules:
- participants are the people the cost is split between. If the text names nobody, include every member. "everyone"/"all of us" means every member. The payer participates unless the text says otherwise.
- paid_by must be one of the member names if the text says who paid; otherwise empty string.
- Names must exactly match the member list when they clearly refer to a member (match nicknames/first names). A name not in the group goes in as written, plus a warning.
- amount is in major units; pick the currency from symbols/words, defaulting to the base currency. If no amount is present, use 0 and add a warning.
- date: resolve words like "yesterday" against today's date; default to today.
- description: short and human, e.g. "Dinner at Truffles" — strip amounts, names and split instructions.
- Put anything you were unsure about into warnings (short sentences).

Expense text: {text}"""


def _finalize_proposal(group, expense, warnings, source):
    """Resolve names to member ids and normalize the proposal."""
    members = {m.name.lower(): m for m in group.members.all()}

    def resolve(name):
        if not name:
            return None
        m = members.get(name.strip().lower())
        if not m:
            for full, member in members.items():
                if full.split(" ")[0] == name.strip().lower():
                    return member
        return m

    payer = resolve(expense.get("paid_by"))
    if expense.get("paid_by") and not payer:
        warnings.append(f"'{expense['paid_by']}' is not a group member — pick the payer.")
    participants = []
    for p in expense.get("participants", []):
        m = resolve(p.get("name"))
        if m:
            participants.append({**p, "member_id": m.id, "name": m.name})
        else:
            warnings.append(f"'{p.get('name')}' is not a group member — left out of the split.")
    expense["paid_by_id"] = payer.id if payer else None
    expense["participants"] = participants
    if not expense.get("date"):
        expense["date"] = date.today().isoformat()
    if not expense.get("currency"):
        expense["currency"] = group.base_currency
    return Response(
        {"source": source, "expense": expense, "warnings": list(dict.fromkeys(warnings))}
    )


@api_view(["POST"])
def parse_expense(request, group_id):
    group = get_group_for(request.user, group_id)
    text = (request.data.get("text") or "").strip()
    if not text:
        return Response({"detail": "Send the expense as 'text'."}, status=400)

    if gemini.available():
        try:
            result = gemini.generate_json(_parse_prompt(group, text), EXPENSE_SCHEMA)
            warnings = result.pop("warnings", [])
            return _finalize_proposal(group, result, warnings, "gemini")
        except gemini.GeminiError:
            pass  # degrade to the offline parser below

    member_names = [m.name for m in group.members.all()]
    parsed = local.parse_expense_text(text, member_names, group.base_currency)
    return _finalize_proposal(group, parsed["expense"], parsed["warnings"], "local")


# ------------------------------------------------------------ receipt scan


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def scan_receipt(request, group_id):
    group = get_group_for(request.user, group_id)
    if not gemini.available():
        return Response(
            {"detail": "Receipt scanning needs the Gemini API key (GEMINI_API_KEY)."},
            status=503,
        )
    upload = request.FILES.get("image")
    if not upload:
        return Response({"detail": "Attach the receipt photo as 'image'."}, status=400)
    if upload.size > 8 * 1024 * 1024:
        return Response({"detail": "Image too large (max 8 MB)."}, status=400)

    prompt = _parse_prompt(group, "(see the attached receipt photo)") + (
        "\n\nRead the attached receipt image. description = merchant/what was bought, "
        "amount = the final total actually charged (after taxes/discounts), date = the "
        "receipt date if printed. Split equally between all members unless the receipt "
        "obviously says otherwise. Add a warning if the total or date is hard to read."
    )
    try:
        result = gemini.generate_json(
            prompt, EXPENSE_SCHEMA, image_bytes=upload.read(), image_mime=upload.content_type
        )
    except gemini.GeminiError as e:
        return Response({"detail": str(e)}, status=502)
    warnings = result.pop("warnings", [])
    return _finalize_proposal(group, result, warnings, "gemini")


# ------------------------------------------------------- import copilot

REVIEW_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "briefing": {"type": "STRING"},
        "recommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "anomaly_id": {"type": "INTEGER"},
                    "verdict": {"type": "STRING", "enum": ["approve", "look_closer"]},
                    "rationale": {"type": "STRING"},
                },
                "required": ["anomaly_id", "verdict", "rationale"],
            },
        },
    },
    "required": ["briefing", "recommendations"],
}


@api_view(["POST"])
def import_review(request, group_id, batch_id):
    group = get_group_for(request.user, group_id)
    batch = ImportBatch.objects.filter(pk=batch_id, group=group).first()
    if not batch:
        return Response({"detail": "No such batch."}, status=404)

    open_anomalies = [
        {
            "id": a.id,
            "code": a.code,
            "message": a.message,
            "proposed_action": a.proposed_action,
            "row_number": a.row.row_number,
            "row": a.row.raw,
        }
        for a in ImportAnomaly.objects.filter(
            row__batch=batch,
            severity=ImportAnomaly.Severity.REVIEW,
            resolved_action__isnull=True,
        ).select_related("row")[:25]
    ]
    summary = batch_summary(batch)

    if gemini.available() and open_anomalies:
        import json

        prompt = f"""You are the review copilot for a shared-expenses CSV import. The pipeline
already detected problems and proposed a fix for each; a human must decide.
Your job: brief the human in plain English and say, per item, whether the
proposal is safe to approve or deserves a closer look (verdict "look_closer"
when the right answer depends on facts only the humans know — e.g. which of
two duplicate rows is real, or whether a departed member truly attended).

Batch: {summary['total_rows']} rows from "{batch.file_name}", {len(open_anomalies)} open decisions.

Open items (JSON): {json.dumps(open_anomalies, default=str)}

Write the briefing as 2-4 sentences a flatmate would understand: what kinds of
problems exist and which ones deserve real attention. Rationales: one concrete
sentence each, referencing the row's actual content, not the anomaly code."""
        try:
            result = gemini.generate_json(prompt, REVIEW_SCHEMA, temperature=0.3)
            known = {a["id"] for a in open_anomalies}
            recs = [r for r in result.get("recommendations", []) if r.get("anomaly_id") in known]
            covered = {r["anomaly_id"] for r in recs}
            for a in open_anomalies:  # Gemini occasionally skips items
                if a["id"] not in covered:
                    recs.append(
                        {"anomaly_id": a["id"], "verdict": "approve",
                         "rationale": "The proposed fix is the conventional choice here."}
                    )
            return Response(
                {"source": "gemini", "briefing": result["briefing"], "recommendations": recs}
            )
        except gemini.GeminiError:
            pass

    fallback = local.build_import_briefing(summary, open_anomalies)
    return Response({"source": "local", **fallback})


# ------------------------------------------------------------- insights

DIGEST_SCHEMA = {
    "type": "OBJECT",
    "properties": {"digest": {"type": "STRING"}},
    "required": ["digest"],
}


@api_view(["GET"])
def insights(request, group_id):
    group = get_group_for(request.user, group_id)
    expenses = list(
        Expense.objects.filter(group=group).select_related("paid_by")
    )

    cat_totals = defaultdict(int)
    month_totals = defaultdict(int)
    month_counts = defaultdict(int)
    payer_totals = defaultdict(int)
    for e in expenses:
        cat_totals[local.categorize(e.description, e.notes)] += e.amount_base_minor
        month_totals[e.date.strftime("%Y-%m")] += e.amount_base_minor
        month_counts[e.date.strftime("%Y-%m")] += 1
        payer_totals[e.paid_by.name] += e.amount_base_minor

    total = sum(e.amount_base_minor for e in expenses)
    categories = [
        {"category": c, "total_minor": t}
        for c, t in sorted(cat_totals.items(), key=lambda kv: -kv[1])
        if t > 0
    ]
    months = [
        {"month": m, "total_minor": t, "count": month_counts[m]}
        for m, t in sorted(month_totals.items())
    ]
    payers = [
        {"name": n, "paid_minor": t}
        for n, t in sorted(payer_totals.items(), key=lambda kv: -kv[1])
    ]

    stats = {
        "group": group.name,
        "base_currency": group.base_currency,
        "total_minor": total,
        "expense_count": len(expenses),
        "categories": categories,
        "months": months,
        "top_payers": payers[:5],
    }

    digest, source = None, "local"
    if gemini.available() and expenses:
        import json

        prompt = f"""Write a short, friendly spending digest (3-4 sentences, no bullet
points, no markdown) for a flat-share expense group, based only on these
numbers. Amounts are integer minor units (divide by 100); format them like
"₹12,340" for INR. Mention the biggest category, the month-over-month trend
if visible, and who has fronted the most money. Be concrete, never invent
numbers.

{json.dumps(stats)}"""
        try:
            digest = gemini.generate_json(prompt, DIGEST_SCHEMA, temperature=0.4)["digest"]
            source = "gemini"
        except gemini.GeminiError:
            digest = None
    if digest is None:
        digest = local.build_digest(
            group.name, group.base_currency, total, months, categories,
            payers[0] if payers else None,
        )

    return Response({**stats, "digest": digest, "source": source})
