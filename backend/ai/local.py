"""Deterministic fallbacks for every AI feature.

When GEMINI_API_KEY is missing (or the API call fails) these produce a
useful, if less clever, result — the UI labels them "offline" so the
user knows which engine answered. Keeping them pure functions also
makes them unit-testable.
"""
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

# ------------------------------------------------------------- NL parsing

CURRENCY_HINTS = {
    "$": "USD",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "rupees": "INR",
}

AMOUNT_RE = re.compile(
    r"(?:(₹|\$|€|rs\.?|inr|usd|eur)\s*)?(\d+(?:[,.]\d{1,2})?)(?:\s*(₹|\$|€|rs\.?|inr|usd|eur|rupees|dollars?|euros?))?",
    re.IGNORECASE,
)
PAID_BY_RE = re.compile(r"\bpaid\s+by\s+([A-Za-z]+)", re.IGNORECASE)
X_PAID_RE = re.compile(r"\b([A-Za-z]+)\s+paid\b", re.IGNORECASE)
SPLIT_WITH_RE = re.compile(
    r"\b(?:split|share[d]?|divide[d]?)\s+(?:it\s+)?(?:between|among|with)\s+(.+?)(?:$|[.;])",
    re.IGNORECASE,
)
WITH_RE = re.compile(r"\bwith\s+(.+?)(?:$|[.;])", re.IGNORECASE)
PERCENT_ITEM_RE = re.compile(r"([A-Za-z]+)\s+(\d+(?:\.\d+)?)\s*%")
SHARE_ITEM_RE = re.compile(r"([A-Za-z]+)\s+(\d+)\s+shares?", re.IGNORECASE)


def _split_names(blob):
    return [n for n in re.split(r"\s*(?:,|and|&)\s*", blob.strip()) if n]


def parse_expense_text(text, member_names, base_currency, today=None):
    """Best-effort parse of a natural-language expense line.

    Returns the same proposal shape the Gemini path produces, plus a
    list of warnings about what could not be inferred.
    """
    today = today or date.today()
    warnings = []
    lower = text.lower()

    # amount + currency: prefer a number adjacent to a currency marker.
    amount = None
    amount_text = None
    currency = base_currency
    for m in AMOUNT_RE.finditer(text):
        marker = m.group(1) or m.group(3)
        try:
            value = Decimal(m.group(2).replace(",", ""))
        except (InvalidOperation, TypeError):
            continue
        if marker:
            amount = value
            amount_text = m.group(0)
            currency = CURRENCY_HINTS.get(marker.lower().rstrip("."), base_currency)
            break
        if amount is None:
            amount = value
            amount_text = m.group(0)
    if amount is None:
        warnings.append("Could not find an amount — fill it in manually.")

    # date words
    when = today
    if "yesterday" in lower or "last night" in lower:
        when = today - timedelta(days=1)
    elif "tomorrow" in lower:
        when = today + timedelta(days=1)
    m = re.search(r"\bon\s+(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", lower)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            when = date(year, month, day)
        except ValueError:
            warnings.append(f"Ignored unparseable date '{m.group(0)}'.")

    # payer
    paid_by = None
    m = PAID_BY_RE.search(text) or X_PAID_RE.search(text)
    if m:
        candidate = _match_member(m.group(1), member_names)
        if candidate:
            paid_by = candidate
        else:
            warnings.append(f"'{m.group(1)}' is not a group member — pick the payer.")

    # participants + split type
    split_type = "equal"
    participants = []
    percents = PERCENT_ITEM_RE.findall(text)
    shares = SHARE_ITEM_RE.findall(text)
    if percents:
        split_type = "percentage"
        for name, pct in percents:
            resolved = _match_member(name, member_names)
            participants.append({"name": resolved or name.title(), "percent": float(pct)})
            if not resolved:
                warnings.append(f"'{name}' is not a group member.")
    elif shares:
        split_type = "share"
        for name, units in shares:
            resolved = _match_member(name, member_names)
            participants.append({"name": resolved or name.title(), "units": int(units)})
            if not resolved:
                warnings.append(f"'{name}' is not a group member.")
    else:
        m = SPLIT_WITH_RE.search(text) or WITH_RE.search(text)
        if m and not re.fullmatch(r"(everyone|everybody|all)", m.group(1).strip(), re.IGNORECASE):
            for name in _split_names(m.group(1)):
                resolved = _match_member(name, member_names)
                if resolved:
                    participants.append({"name": resolved})
                else:
                    warnings.append(f"'{name}' is not a group member — left out of the split.")
            # "split with A and B" usually includes the payer too
            if paid_by and paid_by not in [p["name"] for p in participants]:
                participants.append({"name": paid_by})
        else:
            participants = [{"name": n} for n in member_names]

    # description: strip the mechanical clauses, keep what's left.
    desc = text
    for pattern in (SPLIT_WITH_RE, WITH_RE, PAID_BY_RE):
        desc = pattern.sub("", desc)
    desc = X_PAID_RE.sub("", desc)
    if amount_text:
        desc = desc.replace(amount_text, "", 1)
    desc = re.sub(r"\b(yesterday|today|last night|tomorrow)\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\bon\s+\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\s{2,}", " ", desc).strip(" ,.;-") or text.strip()

    return {
        "expense": {
            "description": desc[:1].upper() + desc[1:] if desc else "",
            "date": when.isoformat(),
            "amount": float(amount) if amount is not None else None,
            "currency": currency,
            "paid_by": paid_by,
            "split_type": split_type,
            "participants": participants,
            "notes": "",
        },
        "warnings": warnings,
    }


def _match_member(token, member_names):
    key = token.strip().lower()
    if not key:
        return None
    for name in member_names:
        if name.lower() == key or name.lower().split(" ")[0] == key:
            return name
    return None


# --------------------------------------------------------- categorization

CATEGORY_RULES = [
    ("Food & dining", ["dinner", "lunch", "breakfast", "restaurant", "pizza", "biryani",
                       "swiggy", "zomato", "cafe", "coffee", "snack", "food", "meal",
                       "takeout", "dominos", "burger", "juice"]),
    ("Groceries", ["grocery", "groceries", "vegetables", "bigbasket", "blinkit",
                   "zepto", "supermarket", "milk", "market"]),
    ("Rent & deposit", ["rent", "deposit", "lease", "brokerage"]),
    ("Utilities", ["electricity", "power", "wifi", "internet", "broadband", "water",
                   "gas", "cylinder", "bill", "recharge", "maintenance"]),
    ("Travel & transport", ["uber", "ola", "cab", "taxi", "auto", "flight", "train",
                            "bus", "petrol", "fuel", "metro", "trip", "hotel"]),
    ("Entertainment", ["movie", "netflix", "spotify", "prime", "concert", "game",
                       "party", "beer", "drinks", "bowling"]),
    ("Household", ["cleaning", "maid", "repair", "plumber", "furniture", "appliance",
                   "detergent", "kitchen", "bulb", "curtain"]),
]


def categorize(description, notes=""):
    text = f"{description} {notes}".lower()
    for category, keywords in CATEGORY_RULES:
        if any(k in text for k in keywords):
            return category
    return "Other"


def build_digest(group_name, base_currency, total_minor, months, categories, top):
    """Template digest used when Gemini is unavailable."""
    if not total_minor:
        return f"No spending recorded in {group_name} yet — add or import expenses to see insights."
    fmt = lambda m: f"{m / 100:,.0f} {base_currency}"
    parts = [f"{group_name} has recorded {fmt(total_minor)} in shared spending."]
    if categories:
        c = categories[0]
        parts.append(
            f"The biggest category is {c['category']} at {fmt(c['total_minor'])} "
            f"({c['total_minor'] * 100 // total_minor}% of everything)."
        )
    if len(months) >= 2:
        prev, last = months[-2], months[-1]
        if prev["total_minor"]:
            delta = (last["total_minor"] - prev["total_minor"]) * 100 // prev["total_minor"]
            direction = "up" if delta >= 0 else "down"
            parts.append(f"Spending in {last['month']} is {direction} {abs(delta)}% vs {prev['month']}.")
    if top:
        parts.append(f"{top['name']} has fronted the most money so far ({fmt(top['paid_minor'])}).")
    return " ".join(parts)


# ------------------------------------------------------- import briefing

CODE_BLURBS = {
    "AMBIGUOUS_DATE": "a date that reads both D/M/Y and M/D/Y",
    "DATE_FAR_PAST": "a date years in the past (almost certainly a typo)",
    "DATE_OUT_OF_SEQUENCE": "a date that breaks the file's chronological order",
    "BAD_DATE": "an unparseable date",
    "MISSING_PAYER": "no payer recorded",
    "UNKNOWN_PERSON": "a person who is not a group member",
    "NEGATIVE_AMOUNT": "a negative amount (likely a refund)",
    "BAD_AMOUNT": "a non-numeric amount",
    "UNKNOWN_CURRENCY_RATE": "a currency with no exchange rate configured",
    "SETTLEMENT_AS_EXPENSE": "a repayment logged as if it were an expense",
    "PERSONAL_TRANSFER": "a personal transfer that isn't a shared expense",
    "PERCENT_SUM_INVALID": "percentages that don't sum to 100",
    "SPLIT_TYPE_CONFLICT": "a split type that contradicts its details",
    "UNEQUAL_SUM_MISMATCH": "unequal split amounts that don't add up to the total",
    "SPLIT_DETAILS_MISSING": "a split type that needs details, with none given",
    "PARTICIPANT_WITHOUT_DETAIL": "participants missing their split detail",
    "BAD_SPLIT_DETAILS": "split details that could not be parsed",
    "MISSING_SPLIT_TYPE": "no split type given",
    "MEMBER_AFTER_DEPARTURE": "an expense involving someone after they left",
    "MEMBER_BEFORE_JOINING": "an expense involving someone before they joined",
    "DUPLICATE_SUSPECT": "two rows that look like the same expense logged twice",
}


def build_import_briefing(batch_summary, open_anomalies):
    """Plain-English batch summary + per-anomaly recommendations, offline."""
    n = batch_summary["total_rows"]
    open_count = len(open_anomalies)
    if not open_count:
        briefing = (
            f"All {n} rows are ready: every decision has been made, so the batch "
            "can be committed to the ledger."
        )
    else:
        by_code = {}
        for a in open_anomalies:
            by_code.setdefault(a["code"], []).append(a)
        themes = "; ".join(
            f"{len(items)}× {CODE_BLURBS.get(code, code.replace('_', ' ').lower())}"
            for code, items in sorted(by_code.items(), key=lambda kv: -len(kv[1]))
        )
        briefing = (
            f"{n} rows staged, {open_count} decision{'s' if open_count != 1 else ''} "
            f"still open. What needs your judgement: {themes}. Each item below has a "
            "proposed fix — approving the proposal is safe in most cases; the ones "
            "to read carefully are duplicates and settlements, where the proposal "
            "changes which rows reach the ledger."
        )
    recommendations = [
        {
            "anomaly_id": a["id"],
            "verdict": "approve",
            "rationale": "The detector's proposal is the conventional fix here; "
            "override only if you know the row's real story.",
        }
        for a in open_anomalies
    ]
    return {"briefing": briefing, "recommendations": recommendations}
