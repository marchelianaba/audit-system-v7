"""App configuration via environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.llm_extract import DEFAULT_LLM_MODEL


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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Abaikan environment variable yang KOSONG agar `.env`/default tetap menang.

        Footgun pydantic-settings: env var bernilai string kosong (mis. shell yang
        meng-`export ANTHROPIC_API_KEY=`) MENGALAHKAN nilai di `.env` — sehingga key
        nyata di `.env` diam-diam hilang. Di sini kita saring env kosong dari sumber
        environment; env var yang BERISI tetap menang (precedence normal terjaga).
        """

        def env_nonempty() -> dict:
            return {
                k: v
                for k, v in env_settings().items()
                if not (isinstance(v, str) and v.strip() == "")
            }

        return (init_settings, env_nonempty, dotenv_settings, file_secret_settings)

    # Anthropic
    anthropic_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://audit:audit@localhost:5432/audit_v7"

    # App
    app_env: str = "development"
    # Log SETIAP query SQL (SQLAlchemy echo). Default OFF — hidupkan hanya saat
    # debug query; sebelumnya selalu ON di dev → spam log + overhead.
    debug_sql: bool = False
    app_secret_key: str = "dev-secret-please-change"
    app_data_dir: str = "/data"
    app_v6_path: str = "/v6"
    app_wiki_path: str = "/wiki"  # knowledge base auditor (pattern temuan, dll)
    # Folder skill pengawasan (SKILL.md + references) — registry skill v7.
    # Default mengikuti layout repo; di docker di-mount ke /skills.
    app_skills_path: str = "/skills"
    # Folder template laporan standar (LHP skeleton {{...}} per jenis pengawasan
    # di <path>/_skeleton-lhp/template-lhp-[skill].docx). Di docker di-mount ke /templates.
    app_templates_path: str = "/templates"
    # Folder task/alur cowork — memuat *-bertahap.md (definisi gate evaluasi).
    app_tasks_path: str = "/tasks"
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
    # Auto-promote OPT-IN untuk CacmFinding v7-native (Fase 1 CACM commit-3, 8 Juni 2026).
    # Default OFF supaya cut-over aman bertahap. Saat dinyalakan, anti-duplikat
    # via _open_usulan_exists yang sudah dual-jalur (cek EWS + v7 untuk satker+kriteria
    # yg setara). Set "merah" atau "merah_kuning" setelah validasi diff EWS vs v7
    # menunjukkan konsistensi (≥90% match status).
    cacm_v7_auto_promote: str = "off"

    # Token quota per user per jam (safety)
    rate_limit_runs_per_hour: int = 5

    # Fallback ekstraksi LLM saat digest deterministik kehilangan field kunci.
    # ON default sejak 3 Jun 2026 (hybrid agresif) — KAK/HPS pengadaan banyak
    # non-standar; parser regex sering miss field penting (dasar_hukum,
    # ruang_lingkup, sumber_referensi_harga, dll). Tier-1 parser tetap jadi
    # primary (gratis, cepat, reproducible); Haiku hanya dipanggil per dokumen
    # bila field kunci di COVERAGE_KEYS hilang — selektif & hemat token (~$0.003/doc).
    # Set OFF eksplisit di .env bila ingin parser-only (mis. operasi tanpa internet).
    # Butuh ANTHROPIC_API_KEY. Asumsi: tidak ada dokumen scan (teks selalu terbaca).
    digest_llm_fallback: bool = True
    digest_llm_model: str = DEFAULT_LLM_MODEL

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
    def skills_path(self) -> Path:
        return Path(self.app_skills_path)

    @property
    def templates_path(self) -> Path:
        return Path(self.app_templates_path)

    @property
    def tasks_path(self) -> Path:
        return Path(self.app_tasks_path)

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
