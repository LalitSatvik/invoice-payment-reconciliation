"""Deployment-time hardening: optional HTTP Basic Auth and security headers.

Both are opt-in via environment variables so local development stays
frictionless -- they only activate when explicitly configured, which is the
expected state for a deployed instance of this single-tenant, no-accounts
tool.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings

_basic_auth = HTTPBasic(auto_error=False)


def require_basic_auth(
    credentials: HTTPBasicCredentials = Depends(_basic_auth),
) -> None:
    """FastAPI dependency enforcing HTTP Basic Auth when it's configured.

    A no-op when ``basic_auth_username``/``basic_auth_password`` aren't set,
    so local development and any deployment that intentionally leaves the
    API open never see a login prompt.
    """
    if settings.basic_auth_username is None or settings.basic_auth_password is None:
        return

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # constant-time comparisons: a timing side-channel here would leak the
    # correct username/password one byte at a time.
    username_ok = hmac.compare_digest(credentials.username, settings.basic_auth_username)
    password_ok = hmac.compare_digest(credentials.password, settings.basic_auth_password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds a small set of defense-in-depth response headers.

    None of these substitute for real authentication or a CDN's own
    protections (Render/Vercel already terminate TLS and can add their own
    headers) -- they close off a few cheap, well-known attack surfaces
    (clickjacking, MIME sniffing) that cost nothing to prevent.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        # Harmless to set even behind a TLS-terminating proxy; only takes
        # effect over an actual HTTPS connection.
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


__all__ = ["require_basic_auth", "SecurityHeadersMiddleware"]
