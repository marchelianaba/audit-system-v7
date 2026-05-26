"""Pydantic schemas untuk request/response API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models import DokumenStatus, PenugasanStatus, Role
from app.skills_registry import available_slugs, skill_exists


# ===== Auth =====
class LoginRequest(BaseModel):
    """Prototype login — cukup pilih role.

    Backend auto-pick user seed pertama yang `role_default == role`.
    Email + NIP optional (untuk kasus produksi nanti pakai SSO).
    """
    role: Role
    email: EmailStr | None = None
    nip: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    nama_lengkap: str
    nip: str
    role_default: Role


class SessionOut(BaseModel):
    user: UserOut
    role_aktif: Role
    token: str


# ===== Penugasan =====
class PenugasanCreate(BaseModel):
    obyek: str
    # Skill kini folder-driven (lihat skills_registry) — bukan enum tetap.
    # Divalidasi terhadap registry supaya skill baru cukup ditambah sebagai folder.
    skill: str
    nomor_st: str | None = None
    tanggal_st: str | None = None

    @field_validator("skill", mode="before")
    @classmethod
    def _skill_terdaftar(cls, v) -> str:
        # mode="before": v bisa berupa enum Skill (dari cacm.py) atau str (dari API).
        # Ambil .value bila enum supaya tidak jadi "Skill.REVIU_PENGADAAN".
        raw = getattr(v, "value", v)
        slug = str(raw).strip().lower()
        if not skill_exists(slug):
            raise ValueError(
                f"skill '{raw}' tidak terdaftar. Tersedia: {', '.join(available_slugs())}"
            )
        return slug


class PenugasanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kode: str
    obyek: str
    # String bebas (DB menyimpan str) — bisa skill di luar 2 pipeline lama.
    skill: str
    nomor_st: str | None
    tanggal_st: str | None
    status: PenugasanStatus
    folder_path: str
    created_at: datetime
    updated_at: datetime


# ===== Dokumen =====
class DokumenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    penugasan_id: int
    nama_file: str
    jenis: str | None
    sha256: str
    size_bytes: int
    status: DokumenStatus
    ingested_json_path: str | None
    error_message: str | None
    uploaded_at: datetime
    ingested_at: datetime | None


# ===== Agen =====
class AgentStartRequest(BaseModel):
    agent: str
    # "anggota_tim" | "ketua_tim"; QC SAIPI dipanggil otomatis dari kedua agen di atas


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    agent_name: str
    status: str
    tokens_in: int
    tokens_out: int
    started_at: datetime
    ended_at: datetime | None
    error_message: str | None


# ===== QC SAIPI =====
class QcSaipiOut(BaseModel):
    stage: str  # "kkp" | "lhp"
    overall_status: str  # "PASS" | "PASS_WITH_WARNINGS" | "BLOCKED_KRITIS"
    total_kritis: int
    total_peringatan: int
    total_needs_review: int
    total_ok: int
    laporan_path: str | None
