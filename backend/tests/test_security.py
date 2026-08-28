"""Tests for the opt-in HTTP Basic Auth gate on /api/v1/*.

Uses a plain TestClient (not the ``client`` fixture's DB-session override)
since these tests only care about the auth boundary, not persistence.
"""
import base64

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_api_is_open_when_basic_auth_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "basic_auth_username", None)
    monkeypatch.setattr(settings, "basic_auth_password", None)
    with TestClient(app) as client:
        response = client.get("/api/v1/mappings")
    assert response.status_code == 200


def test_api_requires_credentials_when_basic_auth_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "basic_auth_username", "admin")
    monkeypatch.setattr(settings, "basic_auth_password", "s3cret")
    with TestClient(app) as client:
        response = client.get("/api/v1/mappings")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


def test_api_rejects_wrong_credentials(monkeypatch):
    monkeypatch.setattr(settings, "basic_auth_username", "admin")
    monkeypatch.setattr(settings, "basic_auth_password", "s3cret")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/mappings", headers=_auth_header("admin", "wrong")
        )
    assert response.status_code == 401


def test_api_accepts_correct_credentials(monkeypatch):
    monkeypatch.setattr(settings, "basic_auth_username", "admin")
    monkeypatch.setattr(settings, "basic_auth_password", "s3cret")
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/mappings", headers=_auth_header("admin", "s3cret")
        )
    assert response.status_code == 200


def test_health_check_never_requires_credentials(monkeypatch):
    monkeypatch.setattr(settings, "basic_auth_username", "admin")
    monkeypatch.setattr(settings, "basic_auth_password", "s3cret")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
