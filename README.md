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

## Local development without Docker

The backend test suite and `npm run build` / `npm run lint` run in CI on
every push (`.github/workflows/ci.yml`). To run everything locally:

### Prerequisites

- **Python 3.11+**, in a `venv` (or `pyenv`, system Python — nothing here
  depends on conda).
- **Postgres 16**, running locally on port `5432`.
- **Node.js 20.9+** for the frontend (Next.js 16).

### Backend

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
```

Create the database and its role, and point the app at it. The test suite
reads `TEST_DATABASE_URL` (see `backend/tests/conftest.py`) while the app
reads `DATABASE_URL`; the simplest setup -- and what CI does -- is to point
both at the *same* database, since the test fixtures wrap every test in a
transaction that is rolled back at teardown and so never leave rows behind:

```bash
createuser --createdb reconcile_app          # password: reconcile_dev
createdb -O reconcile_app reconcile

export DATABASE_URL=postgresql://reconcile_app:reconcile_dev@localhost:5432/reconcile
export TEST_DATABASE_URL=$DATABASE_URL
```

If you'd rather keep the two apart (recommended if you plan to keep real
data in the app database), create a second `reconcile_test` database, run
`alembic upgrade head` against each in turn, and set `TEST_DATABASE_URL` to
the test one instead.

Then migrate and run:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The API is now on `http://localhost:8000` (`GET /health` returns
`{"status": "ok"}`). Run the test suite from the same `backend/` directory:

```bash
pytest -q
```

The migrations create the `pgcrypto` extension the schema needs
(`gen_random_uuid()`), so no manual `CREATE EXTENSION` step is required --
but the role does need permission to create it, hence `--createdb` above.

### Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

The app is then on `http://localhost:3000`. `NEXT_PUBLIC_API_URL` is
inlined at build time, so set it for `npm run build` too if you build a
production bundle. To check the frontend the way CI does:

```bash
npm run build
npm run lint
```

### Generating the synthetic corpus locally

```bash
cd backend
python -m app.synthetic.scenarios
```

Rewrites `backend/data/synthetic/`. Those files are committed, and
`backend/tests/ingestion/test_synthetic_generator.py` asserts the committed
copies are byte-identical to a fresh generation at the default seed -- so if
you change `app/synthetic/scenarios.py`, re-run this and commit the result
or that test will fail.

## License

[MIT](LICENSE)
