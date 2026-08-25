"""Shared fixtures for API-level tests.

Wires FastAPI's ``get_db`` dependency to the transactional ``db_session``
fixture (defined in the top-level ``tests/conftest.py``) so requests made
through the ``TestClient`` run inside the same outer transaction the test
rolls back at teardown -- no state leaks between tests, and no separate
engine/connection is needed.
"""
import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
