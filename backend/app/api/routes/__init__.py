"""Aggregates all API routers under a single ``router`` mounted by ``app.main``.

The health check stays unprefixed, unauthenticated at ``/health`` (so
platform health checks and uptime monitors never need credentials -- it
reveals nothing beyond process liveness). Every product endpoint lives
under ``/api/v1`` and is gated by ``require_basic_auth``, which is a no-op
unless ``BASIC_AUTH_USERNAME``/``BASIC_AUTH_PASSWORD`` are configured.
"""
from fastapi import APIRouter, Depends

from app.api.routes.exceptions import router as exceptions_router
from app.api.routes.exports import router as exports_router
from app.api.routes.mappings import router as mappings_router
from app.api.routes.matches import router as matches_router
from app.api.routes.uploads import router as uploads_router
from app.security import require_basic_auth

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


api_v1_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_basic_auth)])
api_v1_router.include_router(uploads_router)
api_v1_router.include_router(mappings_router)
api_v1_router.include_router(matches_router)
api_v1_router.include_router(exceptions_router)
api_v1_router.include_router(exports_router)

router.include_router(api_v1_router)
