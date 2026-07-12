# AI_USAGE.md — how AI was used to build this

## Tools

- **Claude Code** (Anthropic, Claude model) as the primary development collaborator —
  planning, code generation, and test writing, driven from the terminal against this
  repo.
- Every change was reviewed before committing; the verification loop below is what
  caught the AI's mistakes.

## How it was directed

The workflow that worked: describe the *product decision* precisely, let the AI write
the mechanical code, then **immediately execute the result against the real data** —
never accept output on faith. The single most valuable habit was keeping a runnable
end-to-end script (stage the real CSV → print every anomaly → approve-all → commit →
print balances) and running it after every pipeline change. Most of the AI's errors
below were caught by that loop within minutes of being written.

### Key prompts (abridged)

- *"Act as both PM and developer. Read the assignment PDF and the expense export; map
  each flatmate's request to a concrete feature before writing code."* — produced the
  feature framing (drill-down for Rohan, staged approval for Meera, FX-on-expense for
  Priya, membership windows for Sam).
- *"Design the import as: neutral parse → detectors that attach proposed actions →
  human review → transactional commit. Raw cell values must never be mutated."*
- *"Money is integer minor units end to end. Splits must sum exactly to the total —
  use largest-remainder allocation with deterministic tie-breaks."*
- *"Run the pipeline against the real CSV and show me every anomaly with row numbers
  before we write the review UI."*
- *"Write tests that assert each specific anomaly (row, code) exists in the real file,
  and hand-verify one member's balance in a test comment."*

## Three+ concrete cases where the AI was wrong

### 1. The duplicate detector missed one of the two planted duplicates

The AI's first `DUPLICATE_EXACT` check compared "normalized descriptions" by
lowercasing and stripping punctuation. Running the pipeline against the real file
showed rows 5/6 ("Dinner **at** Marina Bites" vs "dinner - marina bites") produced
**no finding at all** — the word "at" survived normalization, so the strings differed,
and because amount+payer matched, the *suspect*-duplicate branch didn't fire either.
The planted duplicate would have imported twice, silently — the exact failure the
assignment warns about.
**Caught:** by the run-against-real-data loop (the anomaly list printed 17 codes;
`DUPLICATE_EXACT` wasn't among them).
**Changed:** descriptions now compare as normalized *token sets* with short/stop words
dropped, so `{dinner, marina, bites}` matches; a regression test pins row 6.

### 2. A date typo cascaded into four bogus membership flags — and broke the commit

The 2014-03-01 row got the correct `DATE_FAR_PAST` proposal, but the AI ran the
membership-window check on the *raw* date, so Aisha/Rohan/Priya/Dev were all flagged
"not a member in 2014" with `remove_participant` proposals. Approving all proposals
then removed **every participant** and the commit crashed with "no participants left
in split".
**Caught:** the end-to-end script's commit step raised `CommitError` on row 27.
**Changed:** window checks evaluate the row's *proposed corrected* date when a
date-fix proposal exists; a regression test asserts row 27 has no
`MEMBER_BEFORE_JOINING` findings.

### 3. Normalized percentages were rejected by the AI's own validator

For the 110% rows the AI proposed proportional normalization, quantized each percent
to 4 decimals (27.2727 × 3 + 18.1818 = **99.9999**) — and its own `split_percentage`
validator required the sum to be exactly 100, so committing the approved proposal
blew up.
**Caught:** end-to-end commit step, `SplitError: percentages sum to 99.9999`.
**Changed:** percentage allocation is weight-proportional with a 0.01-point tolerance
(documented in code); genuinely wrong sums like the raw 110% are still rejected. A
test covers the normalized-percent path.

### 4. Form-encoded override actions were stored as lists, not values

The anomaly-resolve endpoint did `dict(request.data)`. For JSON bodies that's fine,
but DRF hands form posts a `QueryDict`, whose `dict()` wraps every value in a list —
so a reviewer override arrived at the committer as `{"action": ["set_payer"]}` and
commit failed with *"unknown action `['set_payer']`"*.
**Caught:** by the API-level test that drives the full HTTP journey (it posts form
data, not JSON — luckily a stricter test than the happy path).
**Changed:** flatten via `request.data.items()`; the test now covers the override
path end to end.

### 5. Two anomaly messages were accidentally Python tuples

The AI wrapped long f-string concatenations in parentheses and left a trailing comma,
turning two `message` values into 1-tuples — the review UI would have rendered
`("Rows 24 and 25 look like…",)`.
**Caught:** reading the printed anomaly list from the first real staging run (the
tuple repr was visible in the output).
**Changed:** removed the trailing commas; messages are plain strings.

## What I take from this

The AI was consistently good at scaffolding, Django/DRF idiom, and volume; it was
consistently *risky* exactly where the assignment focuses: silent edge-case behaviour.
None of the five bugs above would have surfaced from reading the code casually — they
surfaced because every change was executed against the real messy file and asserted in
tests. "AI writes, the real data judges" is the loop I'd keep.
