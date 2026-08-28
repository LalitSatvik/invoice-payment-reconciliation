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

    @property
    def frontend_origin(self) -> str:
        return self.frontend_url or f"http://localhost:{self.frontend_port}"


settings = Settings()
