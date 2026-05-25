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
    app_wiki_path: str = "/wiki"  # knowledge base auditor (pattern temuan, dll)
    # Vault pengetahuan penuh (Obsidian/Karpathy) — read-only referensi. Catatan
    # ada di <app_vault_path>/wiki/. Kosong = fitur baca vault non-aktif.
    app_vault_path: str = ""
    app_cors_origins: str = "http://localhost:3000"

    # CACM / EWS SIRUP (integrasi service agent tim) — C1b
    # Kosong = fitur live (webhook/pull) non-aktif; ingest offline tetap jalan.
    cacm_webhook_secret: str = ""   # verifikasi X-Agent-Signature (HMAC sha256) push agent
    cacm_agent_base_url: str = ""   # mis. http://10.0.0.5:3000 (untuk pull/trigger)
    cacm_agent_api_key: str = ""    # X-API-Key untuk REST agent
    # C2 — otomasi: dari sinyal LIVE (webhook/pull), otomatis buat usulan penugasan.
    # "off" | "merah" (default) | "merah_kuning". Anti-duplikat per satker+kode.
    cacm_auto_promote: str = "merah"

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
    def wiki_path(self) -> Path:
        return Path(self.app_wiki_path)

    @property
    def vault_path(self) -> Path | None:
        """Path vault pengetahuan penuh, atau None bila tidak dikonfigurasi."""
        return Path(self.app_vault_path) if self.app_vault_path.strip() else None

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
