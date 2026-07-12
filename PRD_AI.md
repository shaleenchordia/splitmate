# PRD — SplitMate AI: Intelligent Assistance for Shared Expenses

**Author:** Shaleen Chordia · **Status:** v1 shipped locally · **Date:** 2026-07-12
**Doc type:** Product Requirements Document (compressed to the scale of this product — a group-expense app built solo; sections that would be theater at this scale are stated in one line rather than padded.)

---

## 1. Executive Summary

SplitMate already wins on **trust**: integer-paise money math, four split types, and a staged CSV import pipeline where 18 rule-based detectors propose fixes and a human approves every one. What it lacks is **speed of input** and **meaning of output**. This release adds an AI layer with three features — **Smart Add** (natural-language + receipt-photo expense entry), **Import Copilot** (plain-English batch briefing + per-anomaly recommendations), and **Insights** (auto-categorization + AI digest) — plus a full UI redesign (light/dark themes) and complete CRUD coverage in the UI.

**Core product principle: AI proposes, humans commit.** No AI output ever writes to the ledger directly; every proposal lands in an editable form or review card. This extends the app's existing trust architecture instead of fighting it.

**Key engineering decision:** every AI feature has a deterministic offline fallback, so the app is fully functional with zero API keys, zero new dependencies (Gemini is called via stdlib HTTP), and zero new database tables.

## 2. Problem Statement

| Pain | Evidence in product | Cost today |
|---|---|---|
| Manual expense entry is a 10-field form | ExpenseForm: description, date, payer, amount, currency, FX, split type, per-person inputs | ~45–60s per expense; friction → expenses logged late or never → disputes |
| Import review is expert work | 18 anomaly codes (`PERCENT_SUM_INVALID`, `MEMBER_AFTER_DEPARTURE`…) each demand a decision | A 30-row messy file ≈ 10–15 decisions read in "detector language" |
| The ledger answers "how much" but never "so what" | No categories, trends, or summaries anywhere | Users export to Excel to learn anything |

## 3. Goals & Non-Goals

**Goals:** (1) cut time-to-logged-expense by >70%; (2) cut import review time in half without reducing human control; (3) make the ledger self-explaining; (4) make the UI feel like a 2026 product (reference: SubManager-style stat cards, segmented controls, dark mode).

**Non-goals (v1):** payments/UPI integration, mobile app, multi-tenant orgs/pricing, AI auto-commit of anything, model fine-tuning.

## 4. Success Metrics

- **North Star:** % of expenses entered via Smart Add or receipt scan (proxy for "AI is doing the typing"). Target 40%+ after 2 weeks of group use.
- Median time from "open Expenses tab" → expense saved: < 15s via Smart Add.
- Import: median decisions/minute during review, before vs after Copilot briefing.
- Insights tab weekly open rate per active group.
- Guardrail: % of AI proposals edited before save (if ~0% we're over-trusted; if >60% the parser is bad — both are signals).

## 5. Personas & Jobs To Be Done

- **Aisha (organizer, demo user):** "When the group dinner ends, I want to log who owes what in one line, so I don't spend Sunday reconciling."
- **Rohan (skeptic):** "When a number looks wrong, I want to see exactly why, so I can trust the settle-up." (Already served by ledger drill-down; AI must never dilute this — hence proposals-only.)
- **Meera (importer):** "When I upload our messy spreadsheet, I want to understand what's wrong in plain English, so I can decide fast and correctly."
- **Sam (part-time member):** joined/left windows already flag his edge cases; Copilot explains them in human terms.

## 6. Prioritization (MoSCoW × RICE)

| Feature | MoSCoW | Reach | Impact | Confidence | Effort | RICE | Verdict |
|---|---|---|---|---|---|---|---|
| Smart Add (NL → form) | Must | every user, every expense | 3 | 90% | 2d | ★ highest | **Shipped** |
| Import Copilot | Must | every import | 3 | 80% | 1.5d | high | **Shipped** |
| Insights + digest | Should | weekly per group | 2 | 90% | 1d | high | **Shipped** |
| Receipt scan (vision) | Should | subset of expenses | 2 | 70% | 0.5d (rides Smart Add) | med-high | **Shipped** (needs key) |
| UI redesign + dark mode | Should | everyone | 2 | 100% | 1.5d | high | **Shipped** |
| Full CRUD in UI (groups rename/delete, settlement edit/delete, member delete) | Must | everyone | 2 | 100% | 0.5d | high | **Shipped** |
| "Ask your ledger" chat (NL Q&A over balances) | Could | power users | 2 | 60% | 2d | med | Next |
| Category learning from user corrections | Could | — | 1 | 50% | 2d | low | Later |
| AI auto-commit of import batches | Won't | — | — | — | — | — | Violates trust principle |

Kano read: Smart Add is a **delighter** that becomes expected; Insights is **performance**; CRUD completeness and dark mode are **hygiene** — their absence reads as a broken product, which is why they shipped in the same release.

## 7. Functional Requirements (shipped behavior)

### F1 — Smart Add
- **User story:** As a member, I type "Dinner at Truffles 1200, Aisha paid, split with Rohan and Priya" and get a prefilled expense form to confirm.
- **Acceptance criteria:** parses amount+currency (₹/$/€/words), payer ("paid by X" / "X paid"), participants (lists, "everyone"), split types (equal / "Aisha 60%" / "Rohan 2 shares"), relative dates ("yesterday"); unknown names produce warnings, never silent guesses; form opens prefilled with an "AI prefilled — check every field" banner; nothing saves without the user clicking save.
- **Business rules:** payer defaults into the split; no amount → warning + empty field; engine label (Gemini model vs "offline parser") always visible.
- **Error states:** Gemini failure silently degrades to the offline parser (same response shape, `source: "local"`); empty text → 400.
- **Edge cases covered by unit tests:** currency symbols, % sums, share units, unknown members, missing amount, `on 5/3` dates.

### F2 — Receipt scan
- Photo → Gemini Vision → same proposal contract as F1. Reads final charged total, merchant, printed date. Requires `GEMINI_API_KEY`; button disabled with explanatory tooltip otherwise. 8 MB limit; 502 with readable message on model failure.

### F3 — Import Copilot
- **User story:** As the reviewer of a staged batch, I click "AI briefing" and get 2–4 sentences on what's actually in the batch, plus a per-anomaly chip: *"safe to approve"* or *"worth a closer look"* with a one-sentence rationale referencing the row's content.
- **Business rules:** recommendations attach only to **open review-severity** anomalies (cap 25/request); resolved items never re-judged; verdict vocabulary is deliberately two-valued — the AI flags *where human judgment is genuinely needed* (duplicates, departed members) rather than pretending to decide. Fallback briefing is generated deterministically from anomaly counts/codes.
- **Dependency:** existing `ImportAnomaly` data model — zero schema change.

### F4 — Insights
- Deterministic keyword categorizer (8 categories) + monthly totals/counts + top payers, computed server-side from the ledger; Gemini writes the digest paragraph when available, template digest otherwise. Stat cards (Total / count / avg per month), category bars, trend chart, payer leaderboard. Empty state for zero expenses.
- **Deliberate trade-off:** categorization is heuristic-always (fast, free, explainable, testable); AI is used only for narrative. Revisit if category accuracy complaints appear.

### F5 — CRUD completeness (UI)
Group rename (inline) + delete (confirm, cascades); settlement edit (payer/payee/amount/date/note) + delete; member delete (API already refuses when history exists — surfaced as readable error suggesting a leave date). All endpoints already existed via DRF ModelViewSets; this closes the UI gap.

## 8. Non-Functional Requirements

- **Privacy:** only the minimum context leaves the machine (member names, the typed text/receipt, anomaly rows, aggregate stats). No auth tokens, no full ledger dumps. Documented in AI_USAGE.md.
- **Resilience:** 45s timeout; every Gemini failure degrades, never errors the feature (except receipt scan, which has no offline equivalent).
- **Cost:** gemini-2.5-flash, JSON-schema constrained outputs, ≤1 call per user action, no background calls. Rough ceiling at assignment scale: pennies/day.
- **Zero new deps:** stdlib `urllib` client keeps the Vercel bundle and `requirements.txt` unchanged.
- **Latency:** offline paths <10ms; Gemini paths 1–4s with busy states in UI.

## 9. Technical Architecture (as built, and why)

```
React 18 + Vite SPA ──/api──▶ Django 5 + DRF (token auth)
                                 │
                    ┌────────────┼────────────────┐
                 expenses     imports          ai (NEW)
                 (ledger)   (staged review)      │
                                          ┌──────┴──────┐
                                       gemini.py     local.py
                                       (stdlib HTTP,  (regex parser,
                                       responseSchema, categorizer,
                                       vision inline)  briefing builder)
```

- **New `ai` Django app, no models:** AI is stateless glue over existing domain data → no migrations, no new failure domain, trivially removable.
- **`responseSchema` JSON mode** rather than prompt-and-pray parsing: malformed output becomes the API's problem, not ours.
- **Fallback-first contract:** both engines emit the identical proposal shape with a `source` tag; the frontend renders one code path and labels the engine. This is also what makes the feature demoable before the key exists.
- **Key management:** `GEMINI_API_KEY` via env; `backend/.env` (gitignored, `.env.example` provided) auto-loaded by settings for local dev. Same env var works on Vercel later.

## 10. Data Model

**No changes.** All AI features read existing entities (`Group`, `GroupMember`, `Expense`, `ExpenseSplit`, `Settlement`, `ImportBatch`, `ImportRow`, `ImportAnomaly`) and write nothing. This is a feature, not an omission: proposals live in client state until a human saves them through the existing validated endpoints.

## 11. API Design (shipped)

| Endpoint | Method | Body | Returns |
|---|---|---|---|
| `/api/ai/status/` | GET | — | `{gemini: bool, model}` |
| `/api/groups/{id}/ai/parse-expense/` | POST | `{text}` | `{source, expense{…, paid_by_id, participants[{name, member_id, …}]}, warnings[]}` |
| `/api/groups/{id}/ai/scan-receipt/` | POST | multipart `image` | same contract; 503 without key |
| `/api/groups/{id}/imports/{bid}/ai-review/` | POST | — | `{source, briefing, recommendations[{anomaly_id, verdict, rationale}]}` |
| `/api/groups/{id}/ai/insights/` | GET | — | `{total_minor, categories[], months[], top_payers[], digest, source}` |

Auth: existing DRF token + group-membership check (`get_group_for`) on every route. Errors: consistent `{detail}` bodies. Rate limiting: not needed at assignment scale; DRF throttle classes are the one-liner when it is.

## 12. UX Notes (shipped)

- **Design system:** CSS-variable theming, light/dark with pre-paint script (no flash), Inter, segmented pill tabs, stat cards with icon rows (reference: SubManager), soft-shadow cards, deterministic-hue avatars, inline SVG icon set (no dependency).
- **Violet is the AI color** — every AI surface (Smart add panel, briefing, suggestion chips, prefill banner) shares it, so users always know when they're looking at a machine's opinion. Teal stays the brand; ink buttons are the primary action.
- Empty states for expenses/groups/insights; busy states for all AI calls; every AI element labels its engine.

## 13. Rollout & QA

- **Now:** running locally (SQLite). All 58 backend tests green (47 pre-existing + 11 new covering the offline parser, categorizer, briefing).
- **Verification path:** exercise Smart Add offline → confirm form prefill; upload assignment CSV → AI briefing (offline mode) → approve/commit unchanged; Insights renders from committed data. With key: repeat Smart Add/scan/briefing on Gemini and compare.
- **Deploy:** ship to Vercel by setting `GEMINI_API_KEY` in project env — no other prod change. Rollback = remove the env var (features degrade, nothing breaks) or revert the release (no migrations to unwind).
- **UAT checklist:** demo login `aisha`; verify all four split types via Smart Add phrasing; verify a settlement edit/delete reflows balances; verify group delete confirm; verify dark mode persists across reload.

## 14. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM mis-parses an amount/name and user saves without reading | Medium | Confirm-before-save is mandatory; warnings surfaced; edited-before-save metric watches for over-trust |
| Gemini latency/outage during live demo | Medium | Offline fallbacks are first-class and demoable; engine label sets expectations |
| Prompt injection via CSV notes into Copilot | Low | Copilot output is advisory text only — it cannot execute actions; resolution stays on allowlisted `ALLOWED_ACTIONS` |
| Heuristic categories look wrong for niche spends | Medium | Categories are explainable keywords; "Other" is honest; correction-learning is the roadmapped fix |

## 15. Future Enhancements

1. "Ask your ledger" — grounded NL Q&A over balances ("who owes what and why?").
2. Category corrections that persist per group and teach the categorizer.
3. Recurring-expense detection from the ledger (rent, wifi) with one-tap logging.
4. Import Copilot autopilot mode: pre-stage AI-recommended resolutions as *drafts*, still human-committed.
5. Monthly digest email/WhatsApp share card.
