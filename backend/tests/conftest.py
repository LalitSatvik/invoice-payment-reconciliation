import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

# A real Postgres test database is required (not sqlite) because these tests
# exercise Postgres-specific behavior: UUID/JSONB columns, native enum types,
# and the pgcrypto-backed gen_random_uuid() default.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://reconcile_app:reconcile_dev@localhost:5432/reconcile_test",
)


@pytest.fixture(scope="session")
def engine():
    return create_engine(TEST_DATABASE_URL, future=True)


@pytest.fixture()
def db_session(engine):
    """A Session bound to a connection whose outer transaction is always
    rolled back at teardown, so each test starts from (and leaves behind) an
    empty database regardless of commits made during the test.
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, future=True)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
