# Invoice-to-Payment Reconciliation Tool

A tool for reconciling invoices against payments: upload invoice and payment
records, automatically match them, review any discrepancies or unmatched
items, and export the reconciled results.

## Getting started

> **Status:** the Docker setup below has been carefully written and
> statically reviewed (config cross-checked against `.env.example`,
> `requirements.txt`, `package.json`, etc.), but Docker was not available in
> the environment it was written in, so it has not actually been run yet.
> Please run `docker compose up --build` yourself as the first real test, and
> see [`docs/docker.md`](docs/docker.md) for exactly what was and wasn't
> verified, and the reasoning behind the less obvious choices (in particular
> `NEXT_PUBLIC_API_URL`).

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

```bash
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
