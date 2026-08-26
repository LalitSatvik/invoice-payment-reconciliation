#!/bin/bash
# Runs once, only on first initialization of an empty Postgres data volume
# (official postgres image behavior for anything mounted under
# /docker-entrypoint-initdb.d/). POSTGRES_DB (from .env.example) is already
# created automatically by the base image; this creates the second,
# separate database that backend/tests/conftest.py's TEST_DATABASE_URL
# points at, owned by the same application user, so the test suite never
# shares a database with the running application.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE reconcile_test OWNER $POSTGRES_USER;
EOSQL
