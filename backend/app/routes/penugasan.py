"""Routes manajemen penugasan."""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Penugasan, PenugasanStatus, Role, User
from app.schemas import PenugasanCreate, PenugasanOut
from app.storage import gen_kode_penugasan, penugasan_folder

router = APIRouter(prefix="/penugasan", tags=["penugasan"])


def _scaffold_penugasan_files(folder: Path, kode: str, payload: PenugasanCreate, ketua_tim_name: str | None) -> None:
    """Tulis stub context.md + sasaran-assignment.json saat penugasan dibuat.

    V6 (qc_saipi.py, render_kkp.py) butuh kedua file ini ada di lokasi standar:
    - {folder}/context.md
    - {folder}/_PKP/sasaran-assignment.json

    Format mengikuti yang dibaca parse_context_meta() di V6.
    """
    # 1. context.md stub (placeholder fields yang nanti diisi Ketua Tim)
    context_md_path = folder / "context.md"
    if not context_md_path.exists():
        skill_label = payload.skill.value.replace("-", " ").title()
        tanggal_str = (
            payload.tanggal_st.strftime("%d %B %Y") if payload.tanggal_st else "[DIISI AUDITOR]"
        )
        content = f"""# Konteks Penugasan: {payload.obyek}

## Identitas Penugasan

- Kode: {kode}
- Obyek: {payload.obyek}
- Skill / Jenis Pengawasan: {payload.skill.value}
- Nomor ST: {payload.nomor_st or "[DIISI AUDITOR]"}
- Tanggal ST: {tanggal_str}

## Periode & Anggaran

- Periode: [DIISI AUDITOR — mis. Januari–Desember 2026]
- Tahun Anggaran: [DIISI AUDITOR — mis. 2026]

## Tujuan

[DIISI AUDITOR — sebutkan tujuan reviu sesuai PKP. Contoh:
"Memberikan keyakinan terbatas atas kewajaran HPS dan kepatuhan proses
pengadaan terhadap Perpres 16/2018 jo. Perpres 12/2021."]

## Tim

| Peran | Nama Lengkap | NIP | Jabfung |
|-------|--------------|-----|---------|
| Ketua Tim | {ketua_tim_name or "[DIISI]"} | [NIP] | [Auditor Madya/Muda/Pertama] |
| Anggota | [DIISI] | [NIP] | [Auditor Pertama] |

## Ringkasan Obyek

[DIISI — 3-5 kalimat gambaran umum obyek yang direviu: nilai pengadaan,
periode pelaksanaan, instansi auditi, dll.]
"""
        context_md_path.write_text(content, encoding="utf-8")

    # 2. _PKP/sasaran-assignment.json stub (kosong, auditor lengkapi)
    sasaran_path = folder / "_PKP" / "sasaran-assignment.json"
    if not sasaran_path.exists():
        sasaran_path.parent.mkdir(parents=True, exist_ok=True)
        stub = {
            "penugasan_id": kode,
            "skill": payload.skill.value,
            "schema_version": "v4.0.0",
            "tanggal_dibuat": datetime.utcnow().isoformat() + "Z",
            "sasaran": [
                # Contoh struktur — dihapus/diganti oleh Ketua Tim:
                # {
                #     "sasaran_id": "S-01",
                #     "deskripsi": "Kewajaran HPS",
                #     "assigned_to": ["Nama Anggota Tim"],
                #     "langkah_kerja": ["..."]
                # }
            ],
        }
        sasaran_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3. temuan.json stub di _KKP/ supaya render_kkp.py tidak crash bila auditor
    #    coba render sebelum ada temuan. Skema mengikuti render_kkp.py.
    temuan_path = folder / "_KKP" / "temuan.json"
    if not temuan_path.exists():
        temuan_path.parent.mkdir(parents=True, exist_ok=True)
        stub_temuan = {
            "penugasan": {
                "kode": kode,
                "obyek": payload.obyek,
                "jenis_pengawasan": payload.skill.value,
                "nomor_st": payload.nomor_st or "[DIISI AUDITOR]",
                "tanggal_st": payload.tanggal_st.isoformat() if payload.tanggal_st else None,
            },
            "schema_version": "v4.0.0",
            "temuan": [],
        }
        temuan_path.write_text(json.dumps(stub_temuan, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("", response_model=PenugasanOut, status_code=status.HTTP_201_CREATED)
async def create_penugasan(
    payload: PenugasanCreate,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PenugasanOut:
    """Hanya Pengendali Teknis (PT) yang boleh buat penugasan baru.

    Workflow: PT create → KT setup → AT upload+analisis → KT approve + LHR.
    """
    user, role = current
    if role != Role.PT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Hanya Pengendali Teknis (PT) yang boleh buat penugasan baru. Role Anda: {role.value}.",
        )

    kode = gen_kode_penugasan(payload.skill.value)
    folder = penugasan_folder(kode)

    # Scaffolding file V6 — context.md template, sasaran-assignment.json kosong, temuan.json envelope.
    # ketua_tim_name dikosongkan dulu (akan di-assign saat KT setup penugasan).
    _scaffold_penugasan_files(
        folder=folder,
        kode=kode,
        payload=payload,
        ketua_tim_name=None,  # PT yang buat, KT yang setup nanti
    )

    p = Penugasan(
        kode=kode,
        obyek=payload.obyek,
        skill=payload.skill,
        nomor_st=payload.nomor_st,
        tanggal_st=payload.tanggal_st,
        status=PenugasanStatus.DRAFT,
        ketua_tim_id=None,  # ditetapkan saat KT setup
        folder_path=str(folder),
    )
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return PenugasanOut.model_validate(p)


@router.get("", response_model=list[PenugasanOut])
async def list_penugasan(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PenugasanOut]:
    rows = (await db.execute(select(Penugasan).order_by(Penugasan.created_at.desc()))).scalars().all()
    return [PenugasanOut.model_validate(r) for r in rows]


@router.get("/{penugasan_id}", response_model=PenugasanOut)
async def get_penugasan(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PenugasanOut:
    p = (
        await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")
    return PenugasanOut.model_validate(p)


# ============================================================
# SETUP PENUGASAN — endpoint untuk Ketua Tim mengelola sasaran-assignment + context
# Hanya role KT/PT/PM yang bisa PUT. Role apapun bisa GET.
# ============================================================


class SasaranItem(BaseModel):
    """Schema 1 sasaran untuk sasaran-assignment.json.

    Sesuai yang dibaca V6 qc_saipi.py: butuh sasaran_id, assigned_to, dan
    optional langkah_kerja. status default AKTIF, diubah ke SELESAI_KKP
    oleh AT setelah temuan ter-input.
    """

    sasaran_id: str = Field(..., min_length=1, description="ID unik, mis. S-PBJ-01")
    deskripsi: str = Field(default="", description="Deskripsi sasaran")
    assigned_to: list[str] = Field(default_factory=list, description="Nama anggota tim")
    langkah_kerja: list[str] = Field(default_factory=list)
    status: str = Field(default="AKTIF")


class SasaranAssignmentPayload(BaseModel):
    sasaran: list[SasaranItem]


def _require_sasaran_setup_role(role: Role) -> None:
    """Hanya KT yang boleh edit sasaran-assignment. PT bisa juga (override)."""
    if role not in (Role.KT, Role.PT):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Role {role.value} tidak boleh edit sasaran-assignment. Hanya KT/PT.",
        )


def _require_context_edit_role(role: Role) -> None:
    """KT setup awal context.md, AT penyempurnaan saat analisis."""
    if role not in (Role.KT, Role.PT, Role.AT):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Role {role.value} tidak boleh edit context.md.",
        )


async def _get_penugasan_or_404(db: AsyncSession, penugasan_id: int) -> Penugasan:
    p = (
        await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")
    return p


@router.get("/{penugasan_id}/sasaran-assignment")
async def get_sasaran_assignment(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Read isi _PKP/sasaran-assignment.json — bisa diakses semua role.

    Auto-enrich status: kalau ada minimal 1 temuan untuk sasaran tertentu
    di _KKP/temuan.json, dan status masih AKTIF, otomatis upgrade ke
    SELESAI_KKP (KT lalu manual ubah ke DISETUJUI_KT setelah review).
    """
    p = await _get_penugasan_or_404(db, penugasan_id)
    folder = Path(p.folder_path)
    sa_path = folder / "_PKP" / "sasaran-assignment.json"

    if not sa_path.exists():
        return {
            "penugasan_id": p.kode,
            "skill": p.skill if isinstance(p.skill, str) else p.skill.value,
            "schema_version": "v4.0.0",
            "sasaran": [],
        }
    try:
        data = json.loads(sa_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "sasaran-assignment.json corrupt — perlu di-perbaiki manual",
        )

    # Auto-detect SELESAI_KKP berdasarkan temuan.json
    temuan_path = folder / "_KKP" / "temuan.json"
    sasaran_with_temuan: set[str] = set()
    if temuan_path.exists():
        try:
            temuan_data = json.loads(temuan_path.read_text(encoding="utf-8"))
            for t in temuan_data.get("temuan", []):
                sid = t.get("sasaran_id")
                if sid:
                    sasaran_with_temuan.add(sid)
        except json.JSONDecodeError:
            pass

    for s in data.get("sasaran", []):
        # Upgrade AKTIF → SELESAI_KKP kalau ada temuan, tapi jangan downgrade DISETUJUI_KT/DITOLAK_KT
        if s.get("status") == "AKTIF" and s.get("sasaran_id") in sasaran_with_temuan:
            s["status"] = "SELESAI_KKP"

    return data


@router.put("/{penugasan_id}/sasaran-assignment")
async def put_sasaran_assignment(
    penugasan_id: int,
    payload: SasaranAssignmentPayload,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overwrite _PKP/sasaran-assignment.json — hanya KT/PT."""
    user, role = current
    _require_sasaran_setup_role(role)
    p = await _get_penugasan_or_404(db, penugasan_id)

    # Validasi: sasaran_id unique
    ids = [s.sasaran_id for s in payload.sasaran]
    if len(ids) != len(set(ids)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"sasaran_id duplikat ditemukan: {ids}",
        )

    folder = Path(p.folder_path)
    path = folder / "_PKP" / "sasaran-assignment.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "penugasan_id": p.kode,
        "skill": p.skill if isinstance(p.skill, str) else p.skill.value,
        "schema_version": "v4.0.0",
        "tanggal_dibuat": datetime.utcnow().isoformat() + "Z",
        "sasaran": [s.model_dump() for s in payload.sasaran],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "total_sasaran": len(payload.sasaran),
        "path": str(path.relative_to(folder)),
    }


@router.get("/{penugasan_id}/context-md")
async def get_context_md(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Read isi context.md — bisa diakses semua role."""
    p = await _get_penugasan_or_404(db, penugasan_id)
    path = Path(p.folder_path) / "context.md"
    if not path.exists():
        return {"content": "", "exists": False}
    return {
        "content": path.read_text(encoding="utf-8"),
        "exists": True,
    }


class ContextMdPayload(BaseModel):
    content: str = Field(..., description="Isi context.md raw markdown")


@router.put("/{penugasan_id}/context-md")
async def put_context_md(
    penugasan_id: int,
    payload: ContextMdPayload,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overwrite context.md — KT/PT setup awal, AT untuk penyempurnaan saat analisis."""
    user, role = current
    _require_context_edit_role(role)
    p = await _get_penugasan_or_404(db, penugasan_id)

    path = Path(p.folder_path) / "context.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.content, encoding="utf-8")

    return {
        "ok": True,
        "size_bytes": len(payload.content.encode("utf-8")),
        "path": "context.md",
    }
