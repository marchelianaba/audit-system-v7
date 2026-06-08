"""SQLAlchemy models. Skema database minimal untuk prototype."""
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
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
    USULAN_CACM = "USULAN_CACM"  # draft usulan dari sinyal EWS/CACM, belum diterima PT
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


class CacmRun(Base):
    """Satu periode hasil EWS SIRUP (dari agent tim) yang masuk ke v7.

    Sumber: 'offline' (ingest file/sample), 'webhook' (push HMAC), 'pull' (REST).
    """

    __tablename__ = "cacm_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20), default="offline")
    tanggal_evaluasi: Mapped[str | None] = mapped_column(String(40), nullable=True)
    periode_crawl: Mapped[str | None] = mapped_column(String(40), nullable=True)
    periode_crawl_sebelumnya: Mapped[str | None] = mapped_column(String(40), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {total,merah,kuning,hijau,info}
    rekap: Mapped[list | None] = mapped_column(JSON, nullable=True)    # list rekap per satker
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    findings: Mapped[list["EwsFinding"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EwsFinding(Base):
    """Satu finding EWS (EWS-01..09) per satker dalam satu CacmRun."""

    __tablename__ = "ews_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    cacm_run_id: Mapped[int] = mapped_column(ForeignKey("cacm_runs.id"))
    kode: Mapped[str] = mapped_column(String(20))            # "EWS-01".."EWS-09"
    satker: Mapped[str] = mapped_column(String(200))
    satker_kode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # itjen/ekosdig/wasdig
    status: Mapped[str] = mapped_column(String(20))          # MERAH/KUNING/HIJAU/INFO
    judul: Mapped[str | None] = mapped_column(Text, nullable=True)
    penjelasan: Mapped[str | None] = mapped_column(Text, nullable=True)
    ringkasan: Mapped[str | None] = mapped_column(Text, nullable=True)
    nilai_aktual: Mapped[str | None] = mapped_column(Text, nullable=True)
    jumlah_paket_terdampak: Mapped[int] = mapped_column(default=0)
    total_nilai_terdampak: Mapped[int] = mapped_column(BigInteger, default=0)
    threshold: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulasi: Mapped[str | None] = mapped_column(Text, nullable=True)
    rekomendasi: Mapped[str | None] = mapped_column(Text, nullable=True)
    paket_detail: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # BARU | DIPROMOSIKAN (jadi penugasan) | DIABAIKAN
    tindak_lanjut: Mapped[str] = mapped_column(String(20), default="BARU")
    penugasan_id: Mapped[int | None] = mapped_column(ForeignKey("penugasan.id"), nullable=True)

    run: Mapped["CacmRun"] = relationship(back_populates="findings")


# ============================================================
# CACM Mesin Kriteria Multi-Sumber (Fase 1 — numeric_threshold SIRUP)
# ============================================================
#
# Berjalan paralel dgn EwsFinding existing. EwsFinding = legacy, status dari
# agent. CacmObservasi+CacmFinding = v7-native: raw observasi (tanpa status) +
# hasil eval berdasarkan kriteria YAML (`knowledge/cacm/kriteria/*.yaml`).
# Saat agent baru / data source baru (DIPA/SPSE/Kinerja) ditambah, tabel ini
# tetap dipakai.
# ============================================================


class CacmObservasi(Base):
    """Satu observasi mentah dari ingest channel (SIRUP/DIPA/SPSE/Kinerja).

    Tidak ada status di sini — status dihitung dari kriteria saat evaluate.
    `data` JSONB berisi raw fields per source (mis. paket SIRUP punya keys
    `pagu`, `metode`, `pdn`, `ukm`, `bulan_pemilihan`, dst).
    """

    __tablename__ = "cacm_observasi"

    id: Mapped[int] = mapped_column(primary_key=True)
    sumber: Mapped[str] = mapped_column(String(40))          # 'sirup' | 'dipa' | 'spse' | 'kinerja_*'
    dimensi: Mapped[str] = mapped_column(String(40))         # 'PENGADAAN_RENCANA' | ...
    satker_kode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    satker_nama: Mapped[str] = mapped_column(String(200))
    periode_label: Mapped[str] = mapped_column(String(40))   # mis. '2026-Q1' | '2026-05'
    data: Mapped[dict] = mapped_column(JSON, default=dict)   # raw fields
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    raw_source_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    cacm_run_id: Mapped[int | None] = mapped_column(ForeignKey("cacm_runs.id"), nullable=True, index=True)


class TemuanReview(Base):
    """Status review per-temuan — layer HITL di atas `_KKP/temuan.json`.

    Sistem agen tetap tulis temuan ke `_KKP/temuan.json` lewat `append_temuan`,
    TAPI v7 layer filter berdasarkan status review sebelum render KKP/LHR.
    Status default `PENDING`; auditor (KT/PT/AT) approve via UI.

    `temuan_id` = `id_temuan` di `_KKP/temuan.json` (mis. 'T-001'). Unique
    per (penugasan_id, temuan_id) — 1 review per temuan.
    """

    __tablename__ = "temuan_review"

    id: Mapped[int] = mapped_column(primary_key=True)
    penugasan_id: Mapped[int] = mapped_column(ForeignKey("penugasan.id"), index=True)
    temuan_id: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    # PENDING | APPROVED | REJECTED | EDITED
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Edit-overlay: bila auditor edit field temuan via UI, simpan delta di sini.
    # Saat render KKP, V6 baca temuan.json hasil overlay (kode v7 menerapkan
    # edited_fields ke temuan asli sebelum panggil V6). Schema:
    #   { "judul_temuan": "...", "kondisi": "...", "kriteria": "...", "akibat": "..." }
    # Field yang tidak ada di edited_fields tetap pakai versi agen. Status biasanya
    # auto jadi "EDITED" saat edit pertama; auditor bisa approve/reject setelah edit.
    edited_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CacmFinding(Base):
    """Hasil evaluasi 1 kriteria atas observasi (atau agregat observasi)."""

    __tablename__ = "cacm_finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    kriteria_id: Mapped[str] = mapped_column(String(80), index=True)
    kriteria_revisi: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))          # MERAH/KUNING/HIJAU/INFO
    metric_value: Mapped[float | None] = mapped_column(nullable=True)
    metric_satuan: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metric_display: Mapped[str | None] = mapped_column(String(80), nullable=True)
    satker_kode: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    satker_nama: Mapped[str] = mapped_column(String(200))
    periode_label: Mapped[str] = mapped_column(String(40))
    dimensi: Mapped[str] = mapped_column(String(40))
    bukti_observasi_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    narasi: Mapped[str] = mapped_column(Text)
    tindak_lanjut: Mapped[str] = mapped_column(String(20), default="BARU")
    # BARU | DIPROMOSIKAN | DIABAIKAN — sama enum dgn EwsFinding utk konsistensi
    penugasan_id: Mapped[int | None] = mapped_column(ForeignKey("penugasan.id"), nullable=True)
    cacm_run_id: Mapped[int | None] = mapped_column(ForeignKey("cacm_runs.id"), nullable=True, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


class WikiProposalStatus(str, Enum):
    """Daur hidup usulan catatan vault dari penugasan selesai (W3)."""

    DRAFT = "DRAFT"        # auto-generate dari LHP_DONE; belum di-review
    APPLIED = "APPLIED"    # sudah di-tulis ke vault (opsi B)
    REJECTED = "REJECTED"  # auditor tolak (tidak masuk vault)


class WikiProposal(Base):
    """Usulan catatan vault hasil tulis-balik penugasan (W3).

    1 baris per penugasan. Regenerate menggantikan konten (DRAFT). Setelah APPLIED,
    rebuild = bikin DRAFT baru tanpa mengubah file vault (auditor putuskan apply lagi
    atau tidak). Anti-duplikat di vault dijaga di sisi apply (idempoten — lihat
    `wiki_writeback.apply_to_vault`).
    """

    __tablename__ = "wiki_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    penugasan_id: Mapped[int] = mapped_column(
        ForeignKey("penugasan.id"), unique=True, index=True
    )
    nama_file: Mapped[str] = mapped_column(String(200))  # pengawasan-<kode>.md
    konten_md: Mapped[str] = mapped_column(Text)
    delta_index: Mapped[str | None] = mapped_column(Text, nullable=True)
    delta_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    ringkasan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WikiProposalStatus] = mapped_column(
        String(20), default=WikiProposalStatus.DRAFT
    )
    dibuat_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    diupdate_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
