"""Aggregates all API routers under a single ``router`` mounted by ``app.main``.

The health check stays unprefixed at ``/health``; every product endpoint
added in later tasks lives under the ``/api/v1`` base path.
"""
from fastapi import APIRouter

from app.api.routes.mappings import router as mappings_router
from app.api.routes.uploads import router as uploads_router

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


router.include_router(uploads_router, prefix="/api/v1")
router.include_router(mappings_router, prefix="/api/v1")
