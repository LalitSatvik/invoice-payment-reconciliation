from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import settings
from app.security import SecurityHeadersMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="Invoice-to-Payment Reconciliation Tool")

    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(router)

    return app


app = create_app()
