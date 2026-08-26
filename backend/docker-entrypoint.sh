#!/bin/sh
# Entrypoint for the backend container: migrate, then serve.
#
# `app.config.Settings` reads DATABASE_URL from the process environment
# (pydantic-settings, case-insensitive), and `alembic/env.py` reads it from
# that same Settings object -- so overriding the DATABASE_URL env var for a
# single command (as done below for the test database) is enough to point
# Alembic at a different database without touching any file.
set -e

echo "Running migrations against the application database..."
alembic upgrade head

# `docker compose exec backend pytest` (see docker-compose.yml / README) runs
# tests against a second, separate Postgres database (tests/conftest.py:
# TEST_DATABASE_URL, defaulting to .../reconcile_test) so test runs never
# touch application data. That database is created empty by
# docker/postgres-init/01-create-test-database.sh on first Postgres start,
# but nothing else in the repo ever migrates it. Do that here, once per
# container start, so the test suite has a schema to run against as soon as
# the stack is up -- this only runs when TEST_DATABASE_URL is set (i.e. in
# the compose setup), and is a no-op if that database is already at head.
if [ -n "$TEST_DATABASE_URL" ]; then
    echo "Running migrations against the test database..."
    DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
fi

echo "Starting uvicorn on port ${BACKEND_PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}"
