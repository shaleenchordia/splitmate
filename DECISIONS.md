# DECISIONS.md — decision log

Each entry: the decision, the options considered, and why.

---

### D1. Money is stored as integer minor units (paise), never floats or DB decimals

- **Options:** float columns · DECIMAL columns · integer minor units
- **Chose:** `BigIntegerField` minor units everywhere (`amount_minor`,
  `share_base_minor`).
- **Why:** floats drift (0.1 + 0.2 ≠ 0.3) and were disqualified immediately. DECIMAL
  is fine at rest but arithmetic still needs a rounding policy at every step. Integers
  make "the splits must sum exactly to the total" a provable invariant — the split
  allocator literally cannot lose or invent a paisa. Formatting to ₹ happens only at
  the UI edge.

### D2. Split rounding: largest-remainder allocation, ties broken by input order

- **Options:** round each share independently and dump the difference on the payer ·
  round-half-up per share (totals drift) · largest-remainder method
- **Chose:** compute exact fractional shares, floor them, then hand the leftover paise
  to the largest fractional remainders; ties break by participant input order
  (`expenses/services/splits.py`).
- **Why:** deterministic, order-stable, reproducible by hand in the live session, and
  the error per person is bounded by one paisa. ₹10.00 across 3 people = 334/333/333 —
  never 999 or 1001 total.

### D3. Group members are decoupled from login users

- **Options:** every member must be a registered user · members are plain rows a user
  can *claim*
- **Chose:** `GroupMember` with a nullable `user` FK and a `claim` endpoint.
- **Why:** the CSV contains people who will never log in (Dev is a visitor, Kabir is
  "Dev's friend"). Requiring accounts would make the import impossible or force fake
  accounts. Real Splitwise-style apps make the same call.

### D4. Membership is a window, not a boolean

- **Options:** delete members who leave · an `is_active` flag · `joined_on`/`left_on`
  dates
- **Chose:** date windows; "delete" is only allowed for members with no history.
- **Why:** Sam's question ("why would March electricity affect my balance?") is a
  *date* question. Windows let the importer flag any expense that includes someone
  outside their window (Meera in an April split) while correctly *not* flagging her
  March 28 farewell dinner. Deleting Meera would orphan two months of history.

### D5. Balances are computed in one base currency; conversion happens at entry, visibly

- **Options:** keep multi-currency balances per currency · convert at display time with
  a live rate · convert once at entry/import with a stored rate
- **Chose:** every expense stores original `amount_minor` + `currency` + `fx_rate` +
  `amount_base_minor`; balances sum only the base amounts.
- **Why:** Priya's complaint is that the sheet silently pretended $1 = ₹1. The fix is
  an explicit, auditable rate — not a hidden live-rate lookup that changes the ledger
  every day. A stored rate means the drill-down can always show `$540 @ 83.00 =
  ₹44,820`, and changing the batch rate before commit re-derives everything. Display-
  time conversion would make historical balances unstable; per-currency balances would
  make "one number per person" (Aisha's ask) impossible.

### D6. The import is staged: parse → detect → human review → commit

- **Options:** import directly and log warnings · auto-fix with an undo · stage
  everything and gate the commit on explicit approval
- **Chose:** staging (`ImportBatch/ImportRow/ImportAnomaly`), commit refused while any
  review-severity finding lacks a decision.
- **Why:** the assignment is explicit that a silent guess is a failing answer, and
  Meera demands approval of anything the app changes or deletes. Severity does the
  triage: mechanical normalizations (name casing) are info, safe defaults (missing
  currency) are warnings, judgment calls (duplicates, refunds, membership conflicts)
  are review and *block* the commit. `raw` is never mutated — the original file
  contents stay in the DB verbatim next to what the app did.

### D7. Three severities instead of blocking on everything

- **Options:** every finding blocks · nothing blocks (just a report) · tiered
- **Chose:** info / warning / review tiers; only review blocks.
- **Why:** 26 findings on 42 rows — if all blocked, review fatigue would make people
  rubber-stamp. If none blocked, the app would be guessing silently. The tier boundary
  is: *would two reasonable flatmates disagree about the right answer?* If yes, review.

### D8. The settlement-shaped row becomes a Settlement, not an expense

- **Options:** import "Rohan paid Aisha back" as an expense with Aisha as sole
  participant · drop it · convert to a first-class Settlement
- **Chose:** propose conversion (review severity).
- **Why:** as an "expense", ₹5,000 would enter total spending and skew per-person
  shares; the note itself says "this is a settlement not an expense??". A Settlement
  moves ₹5,000 from Rohan's debt to Aisha's credit — exactly what repayment means.

### D9. Sam's deposit is excluded from group balances by default

- **Options:** expense (Aisha sole participant) · settlement Sam → Aisha · exclude
- **Chose:** propose exclusion (review severity), reviewer may record as settlement.
- **Why:** there is no deposit *expense* anywhere in this ledger for the transfer to
  offset. Recording it as a settlement would fabricate a ₹15,000 debt: Aisha would
  suddenly "owe" Sam within the group, distorting Aisha's ask for "one number per
  person". It is a personal transaction between two people about the landlord's
  deposit, which lives outside this ledger. The report still shows the row and the
  decision.

### D10. Negative amounts are refunds, not errors

- **Options:** reject negative rows · absolute-value them · import as negative with
  negative splits
- **Chose:** negative amount = refund; every participant's share goes negative too
  (review severity on import).
- **Why:** the parasailing refund is real money flowing back. Allocation works
  unchanged on negative totals (allocate |total|, negate), so the payer is debited and
  participants credited symmetrically. Rejecting would lose ₹2,490 of truth.

### D11. Duplicate policy: exact copies auto-drop, conflicting copies are a human call

- **Options:** hash rows and drop all matches · flag everything similar · two-tier
- **Chose:** exact duplicates (same date/payer/amount + same normalized description
  token-set) are warnings that keep the first row; suspect duplicates (same date &
  participants, different amount/payer) are review, with the note's own dispute
  ("I think hers is wrong") used to pick which row the *proposal* keeps.
- **Why:** the two Thalassa rows differ by ₹50 — the app cannot know which is right,
  so it must not pick silently. But it can read the evidence and propose; the reviewer
  decides.

### D12. Bad dates get proposals, and downstream checks use the proposed date

- **Options:** reject rows with impossible dates · silently correct the year ·
  propose a correction, blocking on review
- **Chose:** `2014-03-01` → propose `2026-03-01`; `2026-05-04` breaking chronological
  order → propose the day/month swap `2026-04-05`. Membership-window checks evaluate
  against the *proposed* date.
- **Why:** the year is unknowable with certainty, so a human confirms. Using the
  proposed date for window checks prevents one typo from cascading into four bogus
  "member not active in 2014" flags (this exact cascade appeared during development
  and is covered by a regression test).

### D13. Django + DRF + PostgreSQL, React + Vite

- **Options:** Flask/FastAPI + SQLAlchemy · Node/Express · Django + DRF
- **Chose:** Django 5 + DRF; Postgres in production (SQLite for local dev); React 18.
- **Why:** relational DB is a hard requirement; Django's ORM, migrations, auth and
  admin cover the assignment's plumbing so effort goes into the importer (the actual
  differentiator). The role is Python/Django + React, so the stack demonstrates the
  relevant skills. No UI framework — hand-rolled CSS keeps every line explainable.

### D14. Token auth (DRF authtoken) instead of JWT

- **Options:** session auth · JWT (simplejwt) · DRF TokenAuthentication
- **Chose:** DRF tokens.
- **Why:** the SPA needs a bearer credential; tokens are one table and zero
  refresh-token ceremony. JWT adds expiry/rotation complexity with no benefit at this
  scale. Sessions complicate the dev-mode cross-origin story.

### D15. Group-level authorization, not per-object roles

- **Options:** role system (admin/member/viewer) · flat "you're in or you're not"
- **Chose:** a user sees a group if they created it or claimed a member in it; all
  members can do everything.
- **Why:** four flatmates who already share money don't need RBAC. The check lives in
  one function (`get_group_for`) so a role system can be added there later.

### D16. One group holds the flat *and* the Goa trip

- **Options:** split the CSV into two groups on import · one group with guests
- **Chose:** one group; Dev/Kabir are guest members.
- **Why:** the file is one ledger and must be imported "exactly as provided" — rows
  don't declare which group they belong to, so splitting would itself be a guess. Trip
  expenses simply include Dev; the balance math is identical. Guests are visually
  badged so the flat's core four stay obvious.

### D17. Re-detection preserves reviewer decisions

- **Options:** lock the batch after staging · wipe decisions on re-run · re-run and
  restore matching decisions
- **Chose:** `redetect` re-parses stored raw rows (with current member windows and FX
  rates) and restores every decision whose (row, code) pair still exists.
- **Why:** the reviewer will edit member windows or the USD rate *because of* what the
  first pass showed them. Losing their 10 decisions on every tweak would punish
  exactly the careful behaviour the flow exists to encourage.

### D18. The XLSX is accepted as-is; the CSV is a scripted conversion

- **Options:** hand-convert the provided XLSX to CSV · make the importer read both
- **Chose:** importer reads CSV *and* XLSX; `scripts/convert_annex.py` produces the
  CSV from the XLSX mechanically (dates → ISO, no value edits) since the assignment
  distributes the data as `expenses_export.csv` but our copy arrived as `.xlsx`.
- **Why:** "editing the CSV by hand before importing is not allowed" — so no hand
  touches the data. Both files import identically (covered by the test suite for CSV
  and verified end-to-end for XLSX).
