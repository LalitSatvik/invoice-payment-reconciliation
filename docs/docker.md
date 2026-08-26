# Docker setup: status and how to verify it

The `backend/Dockerfile`, `frontend/Dockerfile`, and root `docker-compose.yml`
have been carefully authored and statically reviewed (dependency versions and
ports cross-checked against `backend/requirements.txt`,
`frontend/package.json`, `.env.example`, `backend/alembic.ini`, etc., and the
YAML validated with a parser), but **none of it has actually been run**.
Docker was not available in the environment this was written in, so
`docker compose up --build` has never been executed against this repo.

Concretely, not verified:

- That the images actually build (dependency resolution, apt package names,
  multi-stage `COPY --from` paths).
- That `alembic upgrade head` succeeds against a freshly-initialized
  container-network Postgres the way it did against a local Postgres in
  earlier tasks.
- That the frontend's build step succeeds inside `node:23-slim` (Tailwind v4
  native binary resolution, in particular).
- That `docker compose exec backend pytest` actually goes green in-container.
- Any port, network, or timing behavior that only shows up at runtime.

**Please run `docker compose up --build` yourself as the first real test of
this setup**, and report back anything that needs adjusting. Likely first
failure points, if any, are the two called out below.

## Why `NEXT_PUBLIC_API_URL` is a host URL, not `http://backend:8000`

`frontend/lib/api-client.ts` reads `process.env.NEXT_PUBLIC_API_URL` at
module load time, and every page/component that calls into it
(`app/page.tsx`, `app/review/page.tsx`, `app/exceptions/page.tsx`,
`app/export/page.tsx`, `app/upload/*/page.tsx`,
`components/mapping/ColumnMappingTable.tsx`) is marked `"use client"`. Next.js
inlines `NEXT_PUBLIC_*` env vars into the client bundle at `next build` time,
so this value ends up shipped as a string literal in JavaScript that runs in
the *user's browser* -- a process outside the Compose network entirely. A
value like `http://backend:8000` would resolve fine from another container
but would fail to resolve from the browser (no DNS entry for `backend` on the
host). So `docker-compose.yml` passes `NEXT_PUBLIC_API_URL` as a **build
arg** to the frontend image (`frontend/Dockerfile` bakes it into the bundle
during `npm run build`), set to `http://localhost:${BACKEND_PORT}` -- the
address the browser reaches the backend at once the backend's port is
published to the host. This mirrors `.env.example`'s own
`NEXT_PUBLIC_API_URL=http://localhost:8000` default.

One implication worth knowing: because the value is baked in at build time,
changing `NEXT_PUBLIC_API_URL` (or `BACKEND_PORT`) later requires
`docker compose build frontend` (or `up --build`) again -- restarting the
container alone will not pick up a new value.

## Why the backend image installs pytest, but the Dockerfile's default doesn't

`backend/Dockerfile` installs only `requirements.txt` by default (no
`ARG INSTALL_DEV`, or `INSTALL_DEV=false`) -- a production build never gets
`pytest`/`httpx`. `docker-compose.yml` passes `--build-arg INSTALL_DEV=true`
for the `backend` service specifically so `docker compose exec backend
pytest` (asked for in the task) has a test runner available. That is a
decision made in `docker-compose.yml`, a local/dev orchestration file, not a
default of the Dockerfile itself.

## The test database

`backend/tests/conftest.py` runs the suite against a *separate* Postgres
database (`TEST_DATABASE_URL`, defaulting to `.../reconcile_test`) so tests
never touch application data -- this predates Task 12 and was previously
satisfied by a developer manually running `createdb reconcile_test` and
`alembic upgrade head` against it locally (see Task 2's report). Docker Compose
has no equivalent manual step, so two pieces were added to make
`docker compose exec backend pytest` self-sufficient:

- `docker/postgres-init/01-create-test-database.sh`, mounted into
  `/docker-entrypoint-initdb.d/`, creates the `reconcile_test` database
  (alongside the `reconcile` database the official Postgres image already
  creates from `POSTGRES_DB`) the first time the `pgdata` volume initializes.
- `backend/docker-entrypoint.sh` runs `alembic upgrade head` twice on
  container start: once against `DATABASE_URL` (the app database), and, if
  `TEST_DATABASE_URL` is set, once more against it (by overriding the
  `DATABASE_URL` env var for that one command, since `app.config.Settings`
  reads it from the environment). Both are idempotent no-ops once already at
  head.

This is a real addition beyond a literal reading of "run `alembic upgrade
head` then start uvicorn" -- without it, `reconcile_test` would exist but
have no tables, and every test would fail on first connection. It has not
been executed, so treat it as the most likely thing to need a second look
once Docker is actually run.

## OCR fallback (`poppler-utils` / `tesseract-ocr`)

`app/ingestion/ocr_fallback.py` shells out to Poppler (via `pdf2image`) and
Tesseract (via `pytesseract`), but only when `Settings.enable_ocr_fallback`
is `True` (default `False`). The backend image installs both `poppler-utils`
and `tesseract-ocr` via `apt-get` so that flipping `ENABLE_OCR_FALLBACK=true`
at runtime works immediately, rather than failing on a missing binary the
first time someone tries it. This costs some image size for a path that is
off by default -- if that trade-off is unwanted, both `apt-get install`
packages can be dropped from `backend/Dockerfile` and the OCR fallback route
should then be expected to raise (not silently degrade) if ever enabled
in-container.

## Dependency wheels

`backend/requirements.txt` was installed with `pip install --no-cache-dir` and
no compiler toolchain (`build-essential`/`gcc`/`libpq-dev`) in the image, on
the reasoning that every pinned version (`psycopg2-binary==2.9.9`,
`pandas==2.0.3`, `Pillow==10.4.0`, `reportlab==4.4.3`, `rapidfuzz==3.9.7`,
`pdfplumber==0.11.5`, `pytesseract==0.3.13`, `pdf2image==1.17.0`) is a
mainstream package that has shipped manylinux wheels for Python 3.8 for
years. This is a static, from-knowledge judgment, not something confirmed by
an actual `pip install` inside a Linux container -- if the build fails on a
missing compiler, that is the fix (add `build-essential` back).
