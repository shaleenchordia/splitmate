# SCOPE.md — anomaly log & database schema

## Part 1: Every data problem in `expenses_export.csv`, and what the app does about it

Severities: **info** = mechanical normalization, auto-applied but reported ·
**warning** = applied by default, surfaced prominently · **review** = blocks the
commit until a human approves or overrides.

Row numbers match the file as seen in a spreadsheet (header = row 1).

| # | Row(s) | Problem | Detector code | Severity | Policy / default action |
|---|--------|---------|---------------|----------|------------------------|
| 1 | 5, 6 | Same dinner logged twice: "Dinner at Marina Bites" / "dinner - marina bites", same date, payer, amount | `DUPLICATE_EXACT` | warning | Keep the first row, exclude the later copy. Descriptions are compared as normalized token sets, so punctuation/casing/stop-words don't hide the duplicate. |
| 2 | 24, 25 | Same dinner logged twice with **different** amounts (₹2,400 by Aisha vs ₹2,450 by Rohan); row 25's note says "I think hers is wrong" | `DUPLICATE_SUSPECT` / `DUPLICATE_SUSPECT_KEPT` | review | Propose excluding the row the other note disputes (row 24), keep row 25. The reviewer decides which row wins — the app never picks silently. |
| 3 | 9, 27 | Payer name casing/whitespace variants: "priya", "rohan " | `NAME_VARIANT` | info | Map to the canonical member (case/space-insensitive), report the mapping. |
| 4 | 11 | "Priya S" — surname variant of an existing member | `NAME_VARIANT` | info | A lone first-name match maps to the existing member ("Priya S" → Priya). |
| 5 | 13 | No payer ("can't remember who paid", ₹780) | `MISSING_PAYER` | review | Balances cannot be computed without a payer. Default: exclude the row. Reviewer can assign a payer instead (`set_payer`). |
| 6 | 14 | A settlement logged as an expense ("Rohan paid Aisha back", no split type, note admits it) | `SETTLEMENT_AS_EXPENSE` | review | Propose converting to a **Settlement** (Rohan → Aisha ₹5,000). Importing it as an expense would wrongly shift everyone's balances. |
| 7 | 15, 32 | Percentage splits that sum to 110% (30+30+30+20) | `PERCENT_SUM_INVALID` | review | Propose proportional normalization (each % scaled by 100/110), showing the resulting shares. Reviewer may instead correct values or exclude. Allocation is by weight, exact to the paisa. |
| 8 | 10 | ₹899.995 — sub-paise precision | `FRACTIONAL_MINOR_UNITS` | warning | Money is integer paise. Round half-to-even → ₹900.00, recorded on the row. |
| 9 | 20, 21, 23, 26 | Amounts in USD while the sheet treats $1 = ₹1 (Priya's complaint) | `FOREIGN_CURRENCY` | warning | Convert at the batch FX rate (default 83.00, editable per batch; re-run detection after changing). The rate is stored **on the expense** so every conversion stays traceable. Original amount + currency are kept. |
| 10 | 28 | Missing currency (₹2,105 groceries) | `MISSING_CURRENCY` | warning | Assume the group's base currency (INR) — the row is a domestic vendor between INR rows. Reported, overridable. |
| 11 | 26 | Negative amount: −$30 parasailing refund | `NEGATIVE_AMOUNT` | review | Propose importing as a **refund**: payer returns money, every participant's owed share is reduced by their slice. A negative amount is not treated as an error by default because the note explains it. Reviewer may exclude instead. |
| 12 | 23 | "Dev's friend Kabir" in a split — not a member | `UNKNOWN_PERSON` | review | Propose adding **Kabir** as a *guest member* so his ₹2,490 share is tracked against him (he owes Dev). Alternative: remove him and re-split among 4. |
| 13 | 27 | Date `2014-03-01` — twelve years before the group existed | `DATE_FAR_PAST` | review | Obvious year typo. Propose same day/month in 2026 (`2026-03-01`). Reviewer can set any date. Membership-window checks use the *proposed* date so the typo doesn't cascade into false flags. |
| 14 | 34 | `2026-05-04` sitting between March 28 and April 1 rows; note says "is this April 5 or May 4?" | `DATE_OUT_OF_SEQUENCE` | review | The date breaks the file's chronological order; swapping day/month gives `2026-04-05`, which fits. Propose the swap, reviewer confirms. |
| 15 | 31 | Zero amount ("counted twice earlier - fixing later") | `ZERO_AMOUNT` | warning | A ₹0 expense is a no-op for balances; exclude, keep the note in the report. |
| 16 | 36 | Meera in an April 2 split — she left March 31 ("oops Meera still in the group list") | `MEMBER_AFTER_DEPARTURE` | review | Propose removing Meera and re-splitting among the remaining 3. Reviewer may keep her (contrast: her March 28 farewell dinner is *not* flagged — she was still a member). |
| 17 | 38 | "Sam deposit share" — ₹15,000 paid by Sam, `split_with` only Aisha | `PERSONAL_TRANSFER` | review | This is a deposit hand-over, not a shared expense: there is no matching deposit expense in this ledger, so recording it as an expense **or** a settlement would fabricate a ₹15,000 debt from Aisha to Sam. Default: exclude from group balances. Reviewer may record it as a settlement instead. |
| 18 | 42 | `split_type=equal` but `split_details` filled in ("Aisha 1; Rohan 1; Priya 1; Sam 1") | `REDUNDANT_SPLIT_DETAILS` | info | Details are all identical → consistent with equal; details ignored, reported. If they were unequal, `SPLIT_TYPE_CONFLICT` (review) proposes honouring the detailed shares. |

Also handled (present in the pipeline, not triggered by this file): unparseable
dates/amounts, D/M vs M/D ambiguous dates (`AMBIGUOUS_DATE`), unknown currency with no
batch rate, unequal splits whose amounts don't sum to the total, split details missing
for a detailed split type, duplicated participant in one split, member included
*before* their join date (`MEMBER_BEFORE_JOINING`).

**Count: 18 distinct problem classes across 26 findings in this file** (≥ the 12
promised). Every finding appears in the app's import report with the action taken and
whether a reviewer overrode it.

### Structural facts the import derives (not anomalies)

- **Membership timeline**: Aisha/Rohan/Priya from Feb 1; Meera Feb 1 → Mar 31 (her
  farewell dinner is Mar 28, "moving out Sunday"); Sam from Apr 8 (his deposit day —
  "mid-April" per the brief); Dev is a guest from Feb 8 (first dinner). These are set
  as member join/leave dates in the app; the importer flags rows that contradict them.
- **Split types in the file**: equal (35 rows), unequal (1), percentage (2), share (2),
  plus one settlement-shaped row and one transfer-shaped row.

## Part 2: Database schema

Relational (PostgreSQL in production, SQLite in dev). All money columns are
**integer minor units** (paise/cents) — no floats anywhere near money.

```
accounts_user                    Django AbstractUser (token auth)

expenses_group
  id · name · base_currency (INR) · created_by → user · created_at

expenses_groupmember             a person in a group; NOT necessarily a user
  id · group → group · name (unique per group)
  user → user (nullable: guests like Dev/Kabir have no account)
  joined_on (nullable date) · left_on (nullable date) · is_guest
  -- the membership window drives MEMBER_AFTER_DEPARTURE / _BEFORE_JOINING

expenses_expense
  id · group → group · description · date · paid_by → groupmember
  currency (original, e.g. USD) · amount_minor (original; negative = refund)
  fx_rate (decimal 12,6) · amount_base_minor (converted; what balances use)
  split_type (equal|unequal|percentage|share) · notes · created_by → user
  source_batch → importbatch (nullable) · source_row_number (nullable)
  -- provenance: every imported expense points back at its CSV row

expenses_expensesplit            one participant's owed share
  id · expense → expense · member → groupmember (unique together)
  share_base_minor                 -- allocated, sums exactly to expense total
  input_percent · input_share_units · input_amount_minor   -- raw inputs kept
  -- raw inputs make the drill-down show WHY a share is what it is

expenses_settlement              a payment that reduces debt
  id · group → group · payer → groupmember · payee → groupmember
  amount_base_minor · date · note · created_by → user
  source_batch · source_row_number (same provenance as expenses)

imports_importbatch              one upload
  id · group → group · uploaded_by → user · file_name
  status (staged|committed|discarded) · fx_rates (JSON, e.g. {"USD":"83.00"})
  created_at · committed_at

imports_importrow                one file row, verbatim + interpretation
  id · batch → batch · row_number (unique per batch)
  raw (JSON, untouched cell values) · parsed (JSON, neutral interpretation)
  kind (expense|settlement|skip) · needs_review · approved
  created_expense → expense · created_settlement → settlement

imports_importanomaly            one finding on one row
  id · row → importrow · code · severity (info|warning|review) · message
  proposed_action (JSON) · resolved_action (JSON, reviewer's decision)
  -- resolved_action == NULL on a review-severity finding blocks commit
```

Balance definition (see `expenses/services/balances.py`):
`net(member) = Σ amount_base_minor(expenses they paid) − Σ share_base_minor(their splits)
+ Σ settlements they paid − Σ settlements they received`. Positive = the group owes
them. The per-member ledger endpoint returns exactly these lines; their sum *is* the
balance.
