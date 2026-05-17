"""App configuration via environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfigurasi sistem.

    Semua nilai di-load dari environment variables. Lihat ../../.env.example.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://audit:audit@localhost:5432/audit_v7"

    # App
    app_env: str = "development"
    app_secret_key: str = "dev-secret-please-change"
    app_data_dir: str = "/data"
    app_v6_path: str = "/v6"
    app_cors_origins: str = "http://localhost:3000"

    # Token quota per user per jam (safety)
    rate_limit_runs_per_hour: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]

    @property
    def data_dir(self) -> Path:
        p = Path(self.app_data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def v6_path(self) -> Path:
        return Path(self.app_v6_path)

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
