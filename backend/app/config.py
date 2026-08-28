from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, populated from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://reconcile_app:reconcile_dev@localhost:5432/reconcile"
    postgres_user: str = "reconcile_app"
    postgres_password: str = "reconcile_dev"
    postgres_db: str = "reconcile"
    backend_port: int = 8000
    frontend_port: int = 3000
    enable_ocr_fallback: bool = False
    # Set in deployed environments to the real frontend URL (e.g. a Vercel
    # deployment). Falls back to the local dev server when unset.
    frontend_url: Optional[str] = None
    # Uploads larger than this are rejected before being fully read into
    # memory. 10 MB comfortably covers real invoice/statement CSVs and PDFs.
    max_upload_bytes: int = 10 * 1024 * 1024
    # When both are set, every /api/v1/* request must present matching HTTP
    # Basic credentials. Unset locally so local dev stays unauthenticated.
    basic_auth_username: Optional[str] = None
    basic_auth_password: Optional[str] = None

    @property
    def frontend_origin(self) -> str:
        return self.frontend_url or f"http://localhost:{self.frontend_port}"


settings = Settings()
