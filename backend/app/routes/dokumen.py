"""Routes upload & ingestion dokumen."""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import DocumentCache, Dokumen, DokumenStatus, Penugasan, Role, User
from app.schemas import DokumenOut
from app.storage import (
    classify_doc_by_filename,
    save_upload,
    sha256_bytes,
    target_subfolder_for,
)

router = APIRouter(prefix="/dokumen", tags=["dokumen"])


@router.post("", response_model=DokumenOut, status_code=status.HTTP_201_CREATED)
async def upload_dokumen(
    penugasan_id: int = Form(...),
    jenis: str | None = Form(None),
    file: UploadFile = File(...),
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DokumenOut:
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

    # Cek cache → set status awal
    cached = (
        await db.execute(select(DocumentCache).where(DocumentCache.sha256 == sha))
    ).scalar_one_or_none()

    d = Dokumen(
        penugasan_id=p.id,
        nama_file=file.filename or "dokumen.bin",
        file_path=str(target),
        jenis=jenis_final,
        sha256=sha,
        size_bytes=len(content),
        status=DokumenStatus.READY if cached else DokumenStatus.UPLOADED,
        ingested_json_path=cached.ingested_json_path if cached else None,
        ingested_at=datetime.utcnow() if cached else None,
    )
    db.add(d)
    await db.flush()
    await db.refresh(d)
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
