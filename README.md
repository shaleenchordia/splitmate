# SplitMate — shared expenses, no magic numbers

A shared-expenses app built for the Spreetail internship assignment: four flatmates,
one messy spreadsheet, and an importer that refuses to guess silently.

**Live app:** _(deployment URL here)_
**Stack:** Django 5 + Django REST Framework + PostgreSQL (SQLite in dev) · React 18 + Vite

## What it does

- **Login** — token-based auth (register / login).
- **Groups with membership windows** — members have `joined_on` / `left_on` dates, so
  "Sam moved in mid-April" is a first-class fact, not a footnote. Guests (Dev, Kabir)
  are members too — they never need app accounts.
- **Expenses** — all four split types found in the sheet: `equal`, `unequal` (exact
  amounts), `percentage`, and `share` (proportional units). Multi-currency with an
  explicit FX rate stored on every expense.
- **Balances** — net per member, and a ledger drill-down showing *every* line behind a
  number (Rohan's requirement). Settle-up suggests the minimal set of who-pays-whom
  transfers (Aisha's requirement) and records payments.
- **The importer** — upload the spreadsheet export (CSV or XLSX) exactly as provided.
  Every data problem is detected, explained, and given a *proposed* action. Nothing
  touches the ledger until a human approves or overrides every review-level finding
  (Meera's requirement). The import report lists every finding and the action taken,
  forever.

## Run it locally

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or: uv venv --python 3.12
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver          # API on :8000
```

Frontend (Node 20+):

```bash
cd frontend
npm install
npm run dev                          # dev server on :5173, proxies /api to :8000
```

Production build (Django serves the SPA):

```bash
cd frontend && npm run build         # outputs to backend/staticfiles/
cd ../backend && python manage.py runserver
# open http://localhost:8000
```

Tests (47, including the full annex file exercised end-to-end):

```bash
cd backend && python manage.py test
```

## Try the assignment data

1. Register, create a group (e.g. *Flat 42*).
2. Add members with their windows — Aisha/Rohan/Priya joined `2026-02-01`;
   Meera joined `2026-02-01`, left `2026-03-31`; Sam joined `2026-04-08`;
   Dev (guest) joined `2026-02-08`.
3. Import tab → upload `data/expenses_export.csv` (or the `.xlsx`) with the USD rate.
4. Review the findings, approve or override each proposal, commit.
5. Balances tab → click any member to trace their number line by line.

(Steps 1–2 are optional: unknown names are proposed as new members during import.
Pre-creating members with windows is what makes the Meera/Sam date checks fire.)

## Repository layout

```
backend/
  accounts/           custom user model + auth endpoints
  expenses/           groups, members, expenses, splits, settlements
    services/splits.py       split allocation (largest remainder, integer paise)
    services/balances.py     net balances, member ledger, settle-up suggestions
  imports/            staged imports
    services/pipeline.py     file parsing + 18 anomaly detectors
    services/committer.py    applies approved actions transactionally
frontend/             React SPA (Vite)
data/                 the assignment export, untouched (xlsx + faithful csv)
scripts/convert_annex.py     machine conversion xlsx -> csv (no hand edits)
docs/                 SCOPE.md, DECISIONS.md, AI_USAGE.md
```

## Key documents

- [docs/SCOPE.md](docs/SCOPE.md) — every data problem found in the CSV, how each is
  handled, and the database schema.
- [docs/DECISIONS.md](docs/DECISIONS.md) — the decision log: options considered and why.
- [docs/AI_USAGE.md](docs/AI_USAGE.md) — AI tools used, key prompts, and concrete cases
  where the AI was wrong and how it was caught.

## AI used

Built with **Claude Code (Claude, Anthropic)** as the primary development collaborator,
directed and reviewed line-by-line by me. Details, prompts, and the AI's mistakes are
in [docs/AI_USAGE.md](docs/AI_USAGE.md).
