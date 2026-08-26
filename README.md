# Invoice-to-Payment Reconciliation Tool

A tool for reconciling invoices against payments: upload invoice and payment
records, automatically match them, review any discrepancies or unmatched
items, and export the reconciled results.

It's scoped to one workflow, done properly, rather than a broad platform:
single currency, no authentication/multi-user accounts, and no attempt to
auto-resolve split or partial payments (they're deliberately excluded from
auto-matching and routed to a human instead -- see
[`docs/matching-engine.md`](docs/matching-engine.md)). Within that scope, the
matching engine, the exception-review workflow, and the CSV/summary export
are all real and fully wired end to end.

## Screenshots

*(Not captured in this session -- the six pages are `/` (dashboard),
`/upload/invoices`, `/upload/bank-statement`, `/review`, `/exceptions`, and
`/export`; run the app locally via the quickstart below to see them.)*

## Architecture

Three pieces, each usable independently of the other two:

```
backend/app/
├── matching/       -- the reconciliation engine itself: pure dataclasses and
│                      functions (no DB, no web framework), see below
├── ingestion/       -- CSV column-mapping parser + PDF invoice extraction
├── models/          -- SQLAlchemy models (Invoice, Payment, Match,
│                      ExceptionRecord, SourceMapping, UploadBatch)
├── services/        -- upload/matching/export orchestration between the API
│                      layer, the DB, and the matching engine
├── api/routes/       -- FastAPI routers (uploads, mappings, matches,
│                      exceptions, exports)
└── synthetic/        -- the deterministic test-data generator (see below)

frontend/
├── app/              -- Next.js App Router pages, one per workflow step
├── components/ui/    -- design-token-driven primitives (Button, Card, Badge, ...)
├── components/nav/   -- shared pill navigation
└── lib/              -- typed API client + shared formatting helpers
```

The matching engine (`backend/app/matching/`) is intentionally isolated from
the rest of the backend: it imports nothing from `app.db` or `app.api`, only
plain dataclasses and stdlib/`rapidfuzz`. That's what lets it be unit-tested
directly against a fixed synthetic corpus with no database in the loop --
see [`docs/matching-engine.md`](docs/matching-engine.md) for how it scores
and classifies every invoice/payment pair, with worked numeric examples
drawn from that corpus.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy 2.0 + Alembic, Postgres, `rapidfuzz` for
  fuzzy text matching, `pdfplumber`/`pytesseract` for PDF invoice extraction.
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS v4, no
  external UI kit -- primitives and design tokens are hand-built (see
  `frontend/styles/tokens.ts`).

## The synthetic data generator + `test_scenarios.py` as a regression guardrail

`backend/app/synthetic/scenarios.py` is a deterministic (seeded) generator
that produces `invoices.csv`, `bank_statement.csv`, and `ground_truth.json`
together, as one unit. Each scenario in the ground truth names the exact
invoices/payment rows involved, whether they're expected to match, and why
-- there's a scenario for a clean match, an amount-tolerance edge case on
each side of the boundary, a date-window edge case, several fuzzy-reference
variants (typo'd invoice number, reordered vendor tokens, an abbreviated
vendor name, no usable reference text at all), a true orphan invoice and a
true orphan payment, an ambiguous tie between two identical-looking
invoices, a payment that looks like a partial/split payment, and a
same-day-same-amount collision that the reference text correctly
disambiguates into two separate legitimate matches.

`backend/tests/matching/test_scenarios.py` loads that fixed corpus, runs the
real matching engine over it once, and asserts every scenario resolves the
way the ground truth says it must. Because the corpus is fully deterministic
(same seed → byte-identical CSVs every time) and the assertions are exact,
this test suite is a standing regression guardrail: any future change to the
scoring weights, thresholds, or matching algorithm that breaks one of these
labeled cases fails a specific, named test rather than being caught (or
missed) by eyeballing output. Run it any time via
`docker compose exec backend pytest tests/matching/test_scenarios.py -v`,
or regenerate the corpus itself with
`docker compose exec backend python -m app.synthetic.scenarios` (see
"Generate synthetic data" below).

## Getting started

> **Status:** the Docker setup below has been carefully written and
> statically reviewed (config cross-checked against `.env.example`,
> `requirements.txt`, `package.json`, etc.), but Docker was not available in
> the environment it was written in, so it has not actually been run yet.
> Please run `docker compose up --build` yourself as the first real test, and
> see [`docs/docker.md`](docs/docker.md) for exactly what was and wasn't
> verified, and the reasoning behind the less obvious choices (in particular
> `NEXT_PUBLIC_API_URL`). If `pip install` fails during the backend build,
> `docs/docker.md`'s "Dependency wheels" section names the two pins most
> likely to be the cause (`reportlab`, `pdfplumber`).

### Prerequisites

- Docker and Docker Compose v2 (the `docker compose` CLI, not the standalone
  `docker-compose` binary).

### Run the stack

```bash
cp .env.example .env   # edit values if you want non-default ports/credentials
docker compose up --build
```

This builds and starts three services:

- `postgres` -- Postgres 16, with a persistent named volume for data and a
  second, empty `reconcile_test` database for the test suite.
- `backend` -- runs `alembic upgrade head` (against both the app and test
  databases) and then starts `uvicorn` on `$BACKEND_PORT` (default `8000`).
- `frontend` -- builds the Next.js app and serves it on `$FRONTEND_PORT`
  (default `3000`).

Once it's up:

- Backend health check: `curl http://localhost:8000/health` should return
  `{"status": "ok"}`.
- Frontend: open `http://localhost:3000` in a browser.

### Generate synthetic data

```bash
docker compose exec backend python -m app.synthetic.scenarios
```

Writes `invoices.csv`, `bank_statement.csv`, and `ground_truth.json` into
`backend/data/synthetic/` inside the container (see that module's docstring
for what each file contains and the determinism guarantees).

### Run the backend test suite

Wait for the backend to report healthy first, so both databases have finished
migrating:

```bash
docker compose up -d --wait
docker compose exec backend pytest
```

Runs against the separate `reconcile_test` database (never the application's
own data) -- see `backend/tests/conftest.py` and
[`docs/docker.md`](docs/docker.md) for how that database gets created and
migrated automatically on container start.

### Stopping / resetting

```bash
docker compose down          # stop containers, keep the Postgres volume
docker compose down -v       # stop containers and delete the Postgres volume
```
