"""Routes upload & ingestion dokumen.

Setelah upload, ingestion otomatis ter-trigger sebagai background task — auditor
tidak perlu klik tombol "Jalankan Ingestion" terpisah. Kalau file sudah ada di
cache (sha256 match), status langsung READY tanpa re-process.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import DocumentCache, Dokumen, DokumenStatus, Penugasan, Role, User
from app.schemas import DokumenOut
from app.storage import (
    classify_doc_by_filename,
    delete_file_quiet,
    reset_downstream,
    save_upload,
    sha256_bytes,
    stage_cached_digest,
    target_subfolder_for,
)

# Hanya digest per-file (TOR/RAB) yang aman di-cache by sha256. PBJ/KAK/HPS dst
# di-digest level folder (gabungan banyak file), jadi tidak boleh dipakai ulang
# lintas penugasan via cache.
_CACHEABLE_JENIS = ("TOR", "RAB")

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dokumen", tags=["dokumen"])


async def _ingest_background(penugasan_id: int) -> None:
    """Wrapper untuk panggil _run_ingestion dari background task.

    Import lazy supaya tidak ada cycle dengan routes.agen (yang juga import
    dari routes.dokumen indirectly via app namespace).
    """
    try:
        from app.routes.agen import _run_ingestion
        await _run_ingestion(penugasan_id)
    except Exception as e:
        log.exception("Background ingestion gagal untuk penugasan_id=%d: %s", penugasan_id, e)


@router.post("", response_model=DokumenOut, status_code=status.HTTP_201_CREATED)
async def upload_dokumen(
    background_tasks: BackgroundTasks,
    penugasan_id: int = Form(...),
    jenis: str | None = Form(None),
    file: UploadFile = File(...),
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DokumenOut:
    """Hanya Anggota Tim (AT) yang boleh upload dokumen analisis.

    KT/PT bisa GET (lihat) tapi tidak POST (upload). Workflow: KT setup
    sasaran dulu, kemudian AT yang upload bukti + analisis.
    """
    user, role = current
    if role != Role.AT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Hanya Anggota Tim (AT) yang boleh upload dokumen. Role Anda: {role.value}.",
        )

    p = (
        await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Max 50 MB per file")

    sha = sha256_bytes(content)
    jenis_final = jenis or classify_doc_by_filename(file.filename or "")
    sub = target_subfolder_for(jenis_final)
    target = Path(p.folder_path) / sub / (file.filename or "dokumen.bin")
    await save_upload(content, target)

    # Cek cache (hanya TOR/RAB) → kalau ada, salin digest ke _INGESTED lokal
    # supaya agen bisa menemukannya, lalu langsung READY tanpa subprocess ulang.
    staged_path: str | None = None
    if jenis_final in _CACHEABLE_JENIS:
        cached = (
            await db.execute(select(DocumentCache).where(DocumentCache.sha256 == sha))
        ).scalar_one_or_none()
        if cached:
            staged_path = stage_cached_digest(
                Path(p.folder_path), jenis_final, cached.ingested_json_path
            )

    # Tentukan status awal:
    # - Cache HIT (digest ter-stage) → READY (skip ingestion)
    # - ST/KP/PKP/OTHER             → langsung READY (tidak butuh digest script)
    # - TOR/RAB/KAK/HPS/RFI/KONTRAK → INGESTING (auto-trigger background)
    if staged_path:
        initial_status = DokumenStatus.READY
    elif jenis_final in ("TOR", "RAB", "KAK", "HPS", "RFI", "KONTRAK"):
        initial_status = DokumenStatus.INGESTING
    else:
        # ST, KP, PKP, OTHER, None — tidak ada V6 digest script untuk ini,
        # tapi tetap tersedia untuk dibaca agen lain
        initial_status = DokumenStatus.READY

    d = Dokumen(
        penugasan_id=p.id,
        nama_file=file.filename or "dokumen.bin",
        file_path=str(target),
        jenis=jenis_final,
        sha256=sha,
        size_bytes=len(content),
        status=initial_status,
        ingested_json_path=staged_path,
        ingested_at=datetime.utcnow() if (staged_path or initial_status == DokumenStatus.READY) else None,
    )
    db.add(d)
    await db.flush()
    await db.refresh(d)

    # Auto-trigger ingestion kalau status INGESTING (V6 digest script perlu jalan)
    if initial_status == DokumenStatus.INGESTING:
        # commit dulu supaya background task lihat doc yang baru
        await db.commit()
        background_tasks.add_task(_ingest_background, p.id)

    return DokumenOut.model_validate(d)


@router.get("", response_model=list[DokumenOut])
async def list_dokumen(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DokumenOut]:
    rows = (
        await db.execute(
            select(Dokumen).where(Dokumen.penugasan_id == penugasan_id).order_by(Dokumen.id)
        )
    ).scalars().all()
    return [DokumenOut.model_validate(r) for r in rows]


@router.delete("/{dokumen_id}", status_code=status.HTTP_200_OK)
async def delete_dokumen(
    dokumen_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hapus 1 dokumen (file + hasil ingest) lalu reset analisis turunan.

    Hanya AT. Karena input berubah, output analisis (KKP/LHP) yang berbasis
    dokumen lama otomatis dibersihkan (auto-cascade) supaya analisis ulang
    menghasilkan yang baru, bukan menumpuk hasil lama.
    """
    user, role = current
    if role != Role.AT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Hanya Anggota Tim (AT) yang boleh hapus dokumen. Role Anda: {role.value}.",
        )

    d = (
        await db.execute(select(Dokumen).where(Dokumen.id == dokumen_id))
    ).scalar_one_or_none()
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokumen tidak ditemukan")

    p = (
        await db.execute(select(Penugasan).where(Penugasan.id == d.penugasan_id))
    ).scalar_one_or_none()

    nama = d.nama_file
    # 1. Hapus file fisik + hasil ingest
    delete_file_quiet(d.file_path)
    delete_file_quiet(d.ingested_json_path)
    # 2. Hapus record DB
    await db.delete(d)
    await db.commit()

    # 3. Auto-cascade: input berubah → output analisis stale → reset KKP/LHP
    reset_info: list[str] = []
    if p:
        reset_info = reset_downstream(Path(p.folder_path), from_stage="analysis")

    return {"ok": True, "deleted": nama, "reset_downstream": reset_info}
