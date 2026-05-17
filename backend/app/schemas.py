"""Pydantic schemas untuk request/response API."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import DokumenStatus, PenugasanStatus, Role, Skill


# ===== Auth =====
class LoginRequest(BaseModel):
    email: EmailStr
    nip: str
    role: Role | None = None  # opsional override


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
    skill: Skill
    nomor_st: str | None = None
    tanggal_st: str | None = None


class PenugasanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kode: str
    obyek: str
    skill: Skill
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
