"""SQLAlchemy models. Skema database minimal untuk prototype."""
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(str, Enum):
    AT = "AT"  # Anggota Tim
    KT = "KT"  # Ketua Tim
    PT = "PT"  # Pengendali Teknis
    PM = "PM"  # Pengendali Mutu


class Skill(str, Enum):
    REVIU_RKA_KL = "reviu-rka-kl"
    REVIU_PENGADAAN = "reviu-pengadaan"


class PenugasanStatus(str, Enum):
    DRAFT = "DRAFT"
    INGESTING = "INGESTING"
    KKP_IN_PROGRESS = "KKP_IN_PROGRESS"
    KKP_QC = "KKP_QC"
    KKP_DONE = "KKP_DONE"
    LHP_IN_PROGRESS = "LHP_IN_PROGRESS"
    LHP_QC = "LHP_QC"
    LHP_DONE = "LHP_DONE"


class DokumenStatus(str, Enum):
    UPLOADED = "UPLOADED"
    INGESTING = "INGESTING"
    READY = "READY"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nama_lengkap: Mapped[str] = mapped_column(String(200))
    nip: Mapped[str] = mapped_column(String(18))
    role_default: Mapped[Role] = mapped_column(String(4), default=Role.AT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Penugasan(Base):
    __tablename__ = "penugasan"

    id: Mapped[int] = mapped_column(primary_key=True)
    kode: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    obyek: Mapped[str] = mapped_column(String(400))
    skill: Mapped[Skill] = mapped_column(String(40))
    nomor_st: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tanggal_st: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[PenugasanStatus] = mapped_column(String(40), default=PenugasanStatus.DRAFT)
    ketua_tim_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    folder_path: Mapped[str] = mapped_column(String(400))
    context_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    dokumen: Mapped[list["Dokumen"]] = relationship(
        back_populates="penugasan", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="penugasan", cascade="all, delete-orphan"
    )


class Dokumen(Base):
    __tablename__ = "dokumen"

    id: Mapped[int] = mapped_column(primary_key=True)
    penugasan_id: Mapped[int] = mapped_column(ForeignKey("penugasan.id"))
    nama_file: Mapped[str] = mapped_column(String(400))
    file_path: Mapped[str] = mapped_column(String(600))
    jenis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # TOR, RAB, KAK, HPS, RFI, KONTRAK, ST, KP, PKP, OTHER
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(default=0)
    status: Mapped[DokumenStatus] = mapped_column(String(20), default=DokumenStatus.UPLOADED)
    ingested_json_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    penugasan: Mapped["Penugasan"] = relationship(back_populates="dokumen")


class DocumentCache(Base):
    """Cache hash-based untuk ingestion. Sekali sebuah PDF di-extract, file
    yang sama (apapun nama atau penugasan-nya) tidak perlu di-extract lagi."""

    __tablename__ = "document_cache"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    jenis: Mapped[str] = mapped_column(String(40))
    ingested_json_path: Mapped[str] = mapped_column(String(600))
    extracted_by: Mapped[str] = mapped_column(String(40))  # "deterministic" | "haiku-fallback"
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    """Setiap eksekusi agen di-log lengkap untuk audit trail."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    penugasan_id: Mapped[int] = mapped_column(ForeignKey("penugasan.id"))
    agent_name: Mapped[str] = mapped_column(String(40))
    # "ingestion" | "anggota_tim" | "qc_saipi_kkp" | "qc_saipi_lhp" | "ketua_tim"
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    # "running" | "completed" | "failed" | "blocked_kritis"
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    penugasan: Mapped["Penugasan"] = relationship(back_populates="agent_runs")
