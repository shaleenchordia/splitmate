"""Import staging: parse the uploaded file and detect anomalies.

Principles (see DECISIONS.md):
- `raw` is never modified. `parsed` is a neutral interpretation (ISO
  dates, minor units, trimmed names). Every deviation from the raw data
  is recorded as an ImportAnomaly carrying a proposed action.
- Detection never writes to the ledger. Commit happens separately,
  after review (Meera's requirement).
- Severities: info = mechanical normalization, warning = applied by
  default but surfaced, review = blocks commit until a human decides.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import openpyxl
from django.conf import settings

from ..models import ImportAnomaly, ImportRow

EXPECTED_COLUMNS = [
    "date",
    "description",
    "paid_by",
    "amount",
    "currency",
    "split_type",
    "split_with",
    "split_details",
    "notes",
]

SETTLEMENT_HINTS = ("paid", "back", "settle", "repay", "return")
TRANSFER_HINTS = ("deposit", "advance", "transfer")
DISPUTE_HINTS = ("wrong", "also logged", "duplicate", "logged this")


class ImportFormatError(ValueError):
    pass


# ---------------------------------------------------------------- parsing


def read_rows(file_obj, filename):
    """Yield dicts of raw string cell values from a CSV or XLSX upload."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        try:
            header = [str(h).strip().lower() if h is not None else "" for h in next(rows)]
        except StopIteration:
            raise ImportFormatError("The file is empty.")
        raw_rows = []
        for r in rows:
            cells = []
            for c in r:
                if c is None:
                    cells.append("")
                elif isinstance(c, datetime):
                    cells.append(c.date().isoformat())
                elif isinstance(c, float) and c == int(c):
                    cells.append(str(int(c)))
                else:
                    cells.append(str(c))
            raw_rows.append(cells)
    else:
        text = file_obj.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        try:
            header = [h.strip().lower() for h in next(reader)]
        except StopIteration:
            raise ImportFormatError("The file is empty.")
        raw_rows = [row for row in reader if any(cell.strip() for cell in row)]

    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    if missing:
        raise ImportFormatError(
            f"Missing expected columns: {', '.join(missing)}. Found: {', '.join(header)}"
        )
    idx = {c: header.index(c) for c in EXPECTED_COLUMNS}
    out = []
    for cells in raw_rows:
        cells = list(cells) + [""] * (len(header) - len(cells))
        out.append({c: (cells[idx[c]] or "").strip() for c in EXPECTED_COLUMNS})
    return out


def parse_date(value):
    """Return (date, ambiguous: bool) or (None, False)."""
    value = value.strip()
    if not value:
        return None, False
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", value)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])), False
        except ValueError:
            return None, False
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", value)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        dmy_ok = 1 <= b <= 12 and 1 <= a <= 31
        mdy_ok = 1 <= a <= 12 and 1 <= b <= 31
        try:
            if dmy_ok and mdy_ok and a != b:
                return date(y, b, a), True  # ambiguous: prefer D/M/Y (Indian context)
            if dmy_ok:
                return date(y, b, a), False
            if mdy_ok:
                return date(y, a, b), False
        except ValueError:
            return None, False
    return None, False


NAME_EXTRACT_RE = re.compile(r"'s\s+friend\s+(\S+)\s*$", re.IGNORECASE)


class NameResolver:
    """Maps raw name tokens to canonical member names.

    Canonical names come from existing group members, then from names
    discovered earlier in the file (first spelling wins). Matching is
    case/whitespace-insensitive, and a lone first name matches a
    'First Last'-style variant ('Priya S' -> 'Priya').
    """

    def __init__(self, existing_names):
        self.canonical = {}  # key -> display name
        for n in existing_names:
            self.canonical[self._key(n)] = n

    @staticmethod
    def _key(name):
        return re.sub(r"\s+", " ", name.strip()).lower()

    def resolve(self, token):
        """Return (canonical_name, variant_flag, guest_extracted_flag).

        canonical_name is None when the token names an unknown person.
        """
        cleaned = re.sub(r"\s+", " ", token.strip())
        if not cleaned:
            return None, False, False
        extracted = NAME_EXTRACT_RE.search(cleaned)
        if extracted:
            cleaned = extracted.group(1)
        key = self._key(cleaned)
        if key in self.canonical:
            name = self.canonical[key]
            return name, cleaned != token.strip() or name != cleaned, bool(extracted)
        # 'Priya S' -> 'Priya'; 'priya' -> 'Priya'
        first = key.split(" ")[0]
        if first in self.canonical:
            return self.canonical[first], True, bool(extracted)
        return None, False, bool(extracted)

    def register(self, display_name):
        self.canonical[self._key(display_name)] = display_name


def to_minor(amount_str):
    """Return (minor_units:int|None, fractional:bool, invalid:bool)."""
    try:
        d = Decimal(amount_str)
    except (InvalidOperation, TypeError):
        return None, False, True
    minor = d * 100
    if minor == minor.to_integral_value():
        return int(minor), False, False
    rounded = int(minor.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))
    return rounded, True, False


def parse_split_details(details):
    """'Rohan 700; Priya 400' -> [('Rohan', Decimal(700), False), ...]
    Percent entries ('Aisha 30%') get is_percent=True."""
    entries = []
    for part in details.split(";"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.*?)[\s:]+(-?[\d.]+)\s*(%?)$", part)
        if not m:
            return None
        try:
            value = Decimal(m.group(2))
        except InvalidOperation:
            return None
        entries.append((m.group(1).strip(), value, m.group(3) == "%"))
    return entries or None


# ---------------------------------------------------------------- staging


def stage_batch(batch, raw_rows):
    """Parse raw rows into ImportRows + ImportAnomalies. No ledger writes.

    raw_rows come from read_rows() on first staging, or from the stored
    ImportRow.raw values when detection is re-run after the reviewer
    edits member windows or FX rates.
    """
    group = batch.group
    base_currency = group.base_currency
    fx_rates = {k: Decimal(str(v)) for k, v in batch.fx_rates.items()}

    members = list(group.members.all())
    resolver = NameResolver([m.name for m in members])
    windows = {m.name: (m.joined_on, m.left_on) for m in members}
    first_seen = {}  # new-name -> first row date, for join-date proposals

    staged = []  # (ImportRow, [anomaly dicts]) — saved at the end

    for i, raw in enumerate(raw_rows):
        row_number = i + 2  # 1-based + header line, matches what users see in Excel
        anomalies = []
        parsed = {
            "description": raw["description"],
            "notes": raw["notes"],
            "split_type": raw["split_type"].strip().lower(),
        }

        def flag(code, severity, message, action, **params):
            anomalies.append(
                {
                    "code": code,
                    "severity": severity,
                    "message": message,
                    "proposed_action": {"action": action, **params},
                }
            )

        # --- date
        d, ambiguous = parse_date(raw["date"])
        if d is None:
            flag(
                "BAD_DATE",
                ImportAnomaly.Severity.REVIEW,
                f"Unparseable date '{raw['date']}'. Excluded unless you set a date.",
                "skip_row",
            )
        else:
            parsed["date"] = d.isoformat()
            if ambiguous:
                flag(
                    "AMBIGUOUS_DATE",
                    ImportAnomaly.Severity.REVIEW,
                    f"Date '{raw['date']}' could be D/M/Y or M/D/Y. "
                    f"Interpreted as {d.isoformat()} (D/M/Y). Confirm or correct.",
                    "set_date",
                    date=d.isoformat(),
                )
            if d.year < 2020:
                proposed = d.replace(year=2026)
                flag(
                    "DATE_FAR_PAST",
                    ImportAnomaly.Severity.REVIEW,
                    f"Date {d.isoformat()} is years before this group existed — "
                    f"almost certainly a typo. Proposing {proposed.isoformat()} "
                    "(same day/month, current year). Confirm or correct.",
                    "set_date",
                    date=proposed.isoformat(),
                )

        # --- payer
        payer_raw = raw["paid_by"]
        payer = None
        if not payer_raw:
            flag(
                "MISSING_PAYER",
                ImportAnomaly.Severity.REVIEW,
                "No payer recorded ('paid_by' is empty). Balances cannot be "
                "computed without one. Excluded unless you assign a payer.",
                "skip_row",
            )
        else:
            payer, variant, _ = resolver.resolve(payer_raw)
            if payer is None:
                payer = re.sub(r"\s+", " ", payer_raw.strip()).title()
                resolver.register(payer)
                first_seen.setdefault(payer, parsed.get("date"))
                flag(
                    "UNKNOWN_PERSON",
                    ImportAnomaly.Severity.WARNING,
                    f"'{payer_raw}' is not a group member. Will be added as a "
                    f"member named '{payer}' (join date = first appearance).",
                    "add_member",
                    name=payer,
                    joined_on=parsed.get("date"),
                )
            elif variant:
                flag(
                    "NAME_VARIANT",
                    ImportAnomaly.Severity.INFO,
                    f"Payer '{payer_raw}' matched to member '{payer}' "
                    "(case/spacing/surname variant).",
                    "map_name",
                    source=payer_raw,
                    target=payer,
                )
        parsed["paid_by"] = payer

        # --- amount
        minor, fractional, invalid = to_minor(raw["amount"])
        if invalid:
            flag(
                "BAD_AMOUNT",
                ImportAnomaly.Severity.REVIEW,
                f"Amount '{raw['amount']}' is not a number. Excluded unless corrected.",
                "skip_row",
            )
        else:
            parsed["amount_minor"] = minor
            if fractional:
                flag(
                    "FRACTIONAL_MINOR_UNITS",
                    ImportAnomaly.Severity.WARNING,
                    f"Amount {raw['amount']} has sub-paise precision; money is "
                    f"stored in whole paise. Rounded half-to-even to {minor / 100:.2f}.",
                    "set_amount_minor",
                    amount_minor=minor,
                )
            if minor == 0:
                flag(
                    "ZERO_AMOUNT",
                    ImportAnomaly.Severity.WARNING,
                    "Amount is zero — a no-op for balances "
                    f"(note says: '{raw['notes']}'). Row excluded.",
                    "skip_row",
                )
            if minor is not None and minor < 0:
                flag(
                    "NEGATIVE_AMOUNT",
                    ImportAnomaly.Severity.REVIEW,
                    f"Negative amount {minor / 100:.2f}. Proposing to import as a "
                    "refund: the payer returns money and every participant's owed "
                    "share is reduced. Alternatively exclude the row.",
                    "keep",
                )

        # --- currency
        currency = raw["currency"].upper()
        if not currency:
            currency = base_currency
            flag(
                "MISSING_CURRENCY",
                ImportAnomaly.Severity.WARNING,
                f"No currency set. Assumed group base currency {base_currency} "
                "(all neighbouring rows of this vendor are in it).",
                "set_currency",
                currency=base_currency,
            )
        parsed["currency"] = currency
        if currency != base_currency:
            rate = fx_rates.get(currency)
            if rate is None:
                flag(
                    "UNKNOWN_CURRENCY_RATE",
                    ImportAnomaly.Severity.REVIEW,
                    f"No exchange rate configured for {currency}. Set a batch "
                    "rate and re-run detection, or exclude the row.",
                    "skip_row",
                )
            else:
                base_minor = int(
                    (Decimal(parsed.get("amount_minor", 0)) * rate).quantize(
                        Decimal("1"), rounding=ROUND_HALF_EVEN
                    )
                )
                parsed["fx_rate"] = str(rate)
                parsed["amount_base_minor"] = base_minor
                flag(
                    "FOREIGN_CURRENCY",
                    ImportAnomaly.Severity.WARNING,
                    f"Row is in {currency}. Converted at {rate} {currency}/"
                    f"{base_currency}: {abs(parsed.get('amount_minor', 0)) / 100:.2f} "
                    f"{currency} → {abs(base_minor) / 100:.2f} {base_currency}. "
                    "The rate is stored on the expense and can be changed for the "
                    "whole batch before commit.",
                    "convert_currency",
                    rate=str(rate),
                )
        else:
            parsed["fx_rate"] = "1"
            parsed["amount_base_minor"] = parsed.get("amount_minor")

        # --- participants
        participants = []
        for token in [t for t in raw["split_with"].split(";") if t.strip()]:
            name, variant, extracted = resolver.resolve(token)
            if name is None:
                display = NAME_EXTRACT_RE.search(token.strip())
                display = (display.group(1) if display else token.strip()).title()
                resolver.register(display)
                first_seen.setdefault(display, parsed.get("date"))
                severity = (
                    ImportAnomaly.Severity.REVIEW
                    if extracted
                    else ImportAnomaly.Severity.WARNING
                )
                flag(
                    "UNKNOWN_PERSON",
                    severity,
                    f"Split includes '{token.strip()}', who is not a group member. "
                    f"Proposing to add '{display}' as a guest member so their share "
                    "is tracked; alternatively remove them and re-split.",
                    "add_member",
                    name=display,
                    joined_on=parsed.get("date"),
                    is_guest=True,
                )
                name = display
            elif variant:
                flag(
                    "NAME_VARIANT",
                    ImportAnomaly.Severity.INFO,
                    f"Participant '{token.strip()}' matched to member '{name}'.",
                    "map_name",
                    source=token.strip(),
                    target=name,
                )
            if name in [p["name"] for p in participants]:
                flag(
                    "DUPLICATE_PARTICIPANT",
                    ImportAnomaly.Severity.WARNING,
                    f"'{name}' appears twice in the split; second occurrence ignored.",
                    "keep",
                )
                continue
            participants.append({"name": name})
        parsed["participants"] = participants

        # --- split type & details
        split_type = parsed["split_type"]
        details = parse_split_details(raw["split_details"]) if raw["split_details"] else None
        if raw["split_details"] and details is None:
            flag(
                "BAD_SPLIT_DETAILS",
                ImportAnomaly.Severity.REVIEW,
                f"Could not parse split_details '{raw['split_details']}'.",
                "skip_row",
            )

        is_transferish = (
            len(participants) == 1 and payer is not None and participants[0]["name"] != payer
        )
        text = f"{raw['description']} {raw['notes']}".lower()
        if not split_type:
            if is_transferish and any(h in text for h in SETTLEMENT_HINTS):
                parsed["kind"] = "settlement"
                parsed["payee"] = participants[0]["name"]
                flag(
                    "SETTLEMENT_AS_EXPENSE",
                    ImportAnomaly.Severity.REVIEW,
                    f"'{raw['description']}' has no split type and reads as a "
                    f"repayment from {payer} to {participants[0]['name']}. Proposing "
                    "to record it as a settlement, not an expense (an expense here "
                    "would wrongly change everyone's balances).",
                    "convert_to_settlement",
                    payer=payer,
                    payee=participants[0]["name"],
                )
            else:
                flag(
                    "MISSING_SPLIT_TYPE",
                    ImportAnomaly.Severity.REVIEW,
                    "No split type given. Proposing equal split across the listed "
                    "participants.",
                    "set_split_type",
                    split_type="equal",
                )
                split_type = "equal"
                parsed["split_type"] = "equal"
        elif is_transferish and any(h in text for h in TRANSFER_HINTS):
            flag(
                "PERSONAL_TRANSFER",
                ImportAnomaly.Severity.REVIEW,
                f"'{raw['description']}' looks like a personal transfer from "
                f"{payer} to {participants[0]['name']} (e.g. a deposit hand-over), "
                "not a shared expense — there is no matching expense in this ledger, "
                "so importing it as expense or settlement would distort balances. "
                "Proposing to exclude it; alternatively record as a settlement.",
                "skip_row",
            )

        if split_type == "percentage" and details:
            total_pct = sum(v for _, v, _ in details)
            if total_pct != 100:
                normalized = {
                    n: (v * 100 / total_pct).quantize(Decimal("0.0001"))
                    for n, v, _ in details
                }
                flag(
                    "PERCENT_SUM_INVALID",
                    ImportAnomaly.Severity.REVIEW,
                    f"Percentages sum to {total_pct}%, not 100%. Proposing "
                    "proportional normalization: "
                    + ", ".join(f"{n} {v}%" for n, v in normalized.items())
                    + ". Alternatively correct the percentages or exclude the row.",
                    "normalize_percents",
                )
        if split_type == "equal" and details:
            values = {v for _, v, _ in details}
            if len(values) == 1:
                flag(
                    "REDUNDANT_SPLIT_DETAILS",
                    ImportAnomaly.Severity.INFO,
                    "split_type is 'equal' but split_details lists identical "
                    "shares for everyone — consistent, so details are ignored.",
                    "keep",
                )
            else:
                flag(
                    "SPLIT_TYPE_CONFLICT",
                    ImportAnomaly.Severity.REVIEW,
                    "split_type is 'equal' but split_details has unequal values. "
                    "Proposing to honour the detailed shares (they are more "
                    "specific); alternatively keep the equal split.",
                    "set_split_type",
                    split_type="share",
                )
        if split_type == "unequal" and details and "amount_minor" in parsed:
            total = sum(int(v * 100) for _, v, _ in details)
            if total != parsed["amount_minor"]:
                flag(
                    "UNEQUAL_SUM_MISMATCH",
                    ImportAnomaly.Severity.REVIEW,
                    f"Unequal split amounts sum to {total / 100:.2f} but the "
                    f"expense is {parsed['amount_minor'] / 100:.2f}. Correct the "
                    "amounts or exclude the row.",
                    "skip_row",
                )

        # attach detail values to participants
        if details:
            detail_by_name = {}
            for n, v, _ in details:
                resolved, _, _ = resolver.resolve(n)
                detail_by_name[resolved or n.title()] = v
            for p in participants:
                if p["name"] in detail_by_name:
                    v = detail_by_name[p["name"]]
                    if split_type == "percentage":
                        p["percent"] = str(v)
                    elif split_type == "share":
                        p["units"] = int(v)
                    elif split_type == "unequal":
                        p["amount_minor"] = int(v * 100)
            missing_detail = [
                p["name"]
                for p in participants
                if split_type in ("percentage", "share", "unequal")
                and "percent" not in p
                and "units" not in p
                and "amount_minor" not in p
            ]
            if missing_detail:
                flag(
                    "PARTICIPANT_WITHOUT_DETAIL",
                    ImportAnomaly.Severity.REVIEW,
                    f"No {split_type} detail for: {', '.join(missing_detail)}. "
                    "Correct the row or exclude it.",
                    "skip_row",
                )
        elif split_type in ("percentage", "share", "unequal"):
            flag(
                "SPLIT_DETAILS_MISSING",
                ImportAnomaly.Severity.REVIEW,
                f"split_type '{split_type}' needs split_details but none were "
                "given. Proposing equal split instead.",
                "set_split_type",
                split_type="equal",
            )

        # --- membership windows (Sam's requirement)
        # When the date itself is flagged with a correction proposal
        # (e.g. the 2014 typo), check windows against the proposed date —
        # otherwise every participant would be spuriously flagged too.
        effective_date = parsed.get("date")
        for a in anomalies:
            if a["proposed_action"].get("action") == "set_date":
                effective_date = a["proposed_action"]["date"]
        if effective_date:
            row_date = date.fromisoformat(effective_date)
            involved = [p["name"] for p in participants] + ([payer] if payer else [])
            for name in dict.fromkeys(involved):
                if name in windows:
                    joined_on, left_on = windows[name]
                    if left_on and row_date > left_on:
                        flag(
                            "MEMBER_AFTER_DEPARTURE",
                            ImportAnomaly.Severity.REVIEW,
                            f"{name} left the group on {left_on} but this "
                            f"{row_date} expense includes them. Proposing to "
                            "remove them and re-split among the remaining "
                            "participants; alternatively keep them (e.g. a "
                            "farewell dinner they attended).",
                            "remove_participant",
                            name=name,
                        )
                    if joined_on and row_date < joined_on:
                        flag(
                            "MEMBER_BEFORE_JOINING",
                            ImportAnomaly.Severity.REVIEW,
                            f"{name} joined on {joined_on} but this {row_date} "
                            "expense includes them. Proposing to remove them "
                            "and re-split.",
                            "remove_participant",
                            name=name,
                        )

        parsed.setdefault("kind", "expense")
        staged.append({"row_number": row_number, "raw": raw, "parsed": parsed, "anomalies": anomalies})

    _detect_duplicates(staged)
    _detect_order_breaks(staged)

    # persist
    rows = []
    for s in staged:
        needs_review = any(
            a["severity"] == ImportAnomaly.Severity.REVIEW for a in s["anomalies"]
        )
        row = ImportRow.objects.create(
            batch=batch,
            row_number=s["row_number"],
            raw=s["raw"],
            parsed=s["parsed"],
            kind=s["parsed"].get("kind", "expense"),
            needs_review=needs_review,
        )
        for a in s["anomalies"]:
            ImportAnomaly.objects.create(row=row, **a)
        rows.append(row)
    return rows


def _norm_desc(desc):
    return re.sub(r"[^a-z0-9]+", " ", desc.lower()).strip()


def _desc_tokens(desc):
    return {t for t in _norm_desc(desc).split() if len(t) > 3}


def _detect_duplicates(staged):
    """Exact duplicates: same date+payer+amount+normalized description →
    propose skipping the later row. Suspect duplicates: same date, same
    participants, overlapping description tokens, but different amount or
    payer → review; the note usually says which row is wrong."""
    for i, a in enumerate(staged):
        pa = a["parsed"]
        if pa.get("kind") != "expense" or "amount_minor" not in pa:
            continue
        for b in staged[i + 1:]:
            pb = b["parsed"]
            if pb.get("kind") != "expense" or "amount_minor" not in pb:
                continue
            if pa.get("date") != pb.get("date"):
                continue
            tokens_a = _desc_tokens(pa["description"])
            tokens_b = _desc_tokens(pb["description"])
            same_desc = (
                _norm_desc(pa["description"]) == _norm_desc(pb["description"])
                or (tokens_a and tokens_a == tokens_b)  # 'Dinner at X' == 'dinner - x'
            )
            token_overlap = tokens_a & tokens_b
            exact = (
                same_desc
                and pa.get("paid_by") == pb.get("paid_by")
                and pa["amount_minor"] == pb["amount_minor"]
            )
            if exact:
                b["anomalies"].append(
                    {
                        "code": "DUPLICATE_EXACT",
                        "severity": ImportAnomaly.Severity.WARNING,
                        "message": (
                            f"Identical to row {a['row_number']} (same date, payer, "
                            "amount, description). This later copy is excluded."
                        ),
                        "proposed_action": {"action": "skip_row"},
                    }
                )
            elif token_overlap and (
                pa["amount_minor"] != pb["amount_minor"]
                or pa.get("paid_by") != pb.get("paid_by")
            ) and {p["name"] for p in pa["participants"]} == {
                p["name"] for p in pb["participants"]
            }:
                notes_b = pb.get("notes", "").lower()
                disputed_first = any(h in notes_b for h in DISPUTE_HINTS)
                target, keep = (a, b) if disputed_first else (b, a)
                target["anomalies"].append(
                    {
                        "code": "DUPLICATE_SUSPECT",
                        "severity": ImportAnomaly.Severity.REVIEW,
                        "message": (
                            f"Rows {a['row_number']} and {b['row_number']} look like "
                            "the same expense logged twice with different "
                            f"amounts/payers ('{pa['description']}' vs "
                            f"'{pb['description']}'). Proposing to keep row "
                            f"{keep['row_number']} and exclude this one"
                            + (
                                f" — row {b['row_number']}'s note says so"
                                if disputed_first
                                else ""
                            )
                            + ". You decide which row wins."
                        ),
                        "proposed_action": {"action": "skip_row"},
                    }
                )
                keep["anomalies"].append(
                    {
                        "code": "DUPLICATE_SUSPECT_KEPT",
                        "severity": ImportAnomaly.Severity.INFO,
                        "message": (
                            f"Counterpart of the suspected duplicate on row "
                            f"{target['row_number']}; this row is the one kept."
                        ),
                        "proposed_action": {"action": "keep"},
                    }
                )


def _detect_order_breaks(staged):
    """A date far out of the file's chronological flow usually means a
    day/month mix-up (e.g. 2026-05-04 sitting between March and April
    rows → probably 2026-04-05). Propose the day/month swap when it
    restores the ordering."""
    dated = [s for s in staged if "date" in s["parsed"]]
    for i, s in enumerate(dated):
        d = date.fromisoformat(s["parsed"]["date"])
        if d.year < 2020:
            continue  # already flagged as DATE_FAR_PAST
        prev_d = date.fromisoformat(dated[i - 1]["parsed"]["date"]) if i else None
        next_d = (
            date.fromisoformat(dated[i + 1]["parsed"]["date"])
            if i + 1 < len(dated)
            else None
        )
        # A week's slack on each side: neighbouring rows are rarely the
        # exact same day, so demand the swapped date lands near the
        # neighbours while the original date does not.
        slack = timedelta(days=7)
        if prev_d and next_d and prev_d.year >= 2020 and not (
            prev_d - slack <= d <= next_d + slack
        ):
            if d.day <= 12:
                try:
                    swapped = date(d.year, d.day, d.month)
                except ValueError:
                    continue
                if prev_d - slack <= swapped <= next_d + slack:
                    s["anomalies"].append(
                        {
                            "code": "DATE_OUT_OF_SEQUENCE",
                            "severity": ImportAnomaly.Severity.REVIEW,
                            "message": (
                                f"Date {d.isoformat()} breaks the file's "
                                f"chronological order (between {prev_d} and "
                                f"{next_d}). Swapping day and month gives "
                                f"{swapped.isoformat()}, which fits — likely a "
                                "D/M vs M/D mix-up. Confirm the proposed date "
                                "or keep the original."
                            ),
                            "proposed_action": {
                                "action": "set_date",
                                "date": swapped.isoformat(),
                            },
                        }
                    )
