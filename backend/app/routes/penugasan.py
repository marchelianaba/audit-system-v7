"""Routes manajemen penugasan."""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Dokumen, DokumenStatus, Penugasan, PenugasanStatus, Role, TemuanReview, User
from app.schemas import PenugasanCreate, PenugasanOut
from app.storage import (
    INPUT_JENIS,
    compute_penugasan_status,
    context_readiness,
    delete_penugasan_folder,
    gen_kode_penugasan,
    penugasan_folder,
)

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
        skill_label = payload.skill.replace("-", " ").title()
        tanggal_str = (
            payload.tanggal_st.strftime("%d %B %Y") if payload.tanggal_st else "[DIISI AUDITOR]"
        )
        content = f"""# Konteks Penugasan: {payload.obyek}

## Identitas Penugasan

- Kode: {kode}
- Obyek: {payload.obyek}
- Skill / Jenis Pengawasan: {payload.skill}
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
            "skill": payload.skill,
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
                "jenis_pengawasan": payload.skill,
                "nomor_st": payload.nomor_st or "[DIISI AUDITOR]",
                "tanggal_st": payload.tanggal_st.isoformat() if payload.tanggal_st else None,
            },
            "schema_version": "v4.0.0",
            "temuan": [],
        }
        temuan_path.write_text(json.dumps(stub_temuan, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_preload_background(kode: str, obyek: str, skill: str, folder: Path) -> None:
    """Background task: bangun bundle preload-context begitu penugasan dibuat.

    Idempoten — bila file `_PRELOAD/context-bundle.md` sudah ada, skip
    (auditor mungkin sudah rebuild manual). Best-effort: error log saja,
    tidak rethrow supaya tidak menggagalkan create_penugasan.
    """
    try:
        from app import preload_context  # late import (hindari circular)
        target = folder / "_PRELOAD" / "context-bundle.md"
        if target.is_file() and target.stat().st_size > 100:
            return  # sudah ada → skip
        result = preload_context.build_preload_bundle(
            penugasan_kode=kode, obyek=obyek, skill=skill,
        )
        preload_context.save_preload_bundle(folder, result["markdown"])
    except Exception as e:  # noqa: BLE001 — log saja, jangan crash background task
        import logging
        logging.getLogger(__name__).warning(
            "auto-preload gagal untuk %s: %s", kode, e
        )


@router.post("", response_model=PenugasanOut, status_code=status.HTTP_201_CREATED)
async def create_penugasan(
    payload: PenugasanCreate,
    background_tasks: BackgroundTasks,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PenugasanOut:
    """Hanya Pengendali Teknis (PT) yang boleh buat penugasan baru.

    Workflow: PT create → KT setup → AT upload+analisis → KT approve + LHR.

    Side-effect: auto-build `_PRELOAD/context-bundle.md` di background supaya
    saat agen jalan, konteks (pattern wiki + vault + glossary + regulasi +
    riwayat W3) sudah siap dibaca. Tidak blocking — penugasan tetap return
    cepat. Idempoten — auditor bisa rebuild manual nanti via UI.
    """
    user, role = current
    if role != Role.PT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Hanya Pengendali Teknis (PT) yang boleh buat penugasan baru. Role Anda: {role.value}.",
        )

    kode = gen_kode_penugasan(payload.skill)
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

    # Auto-build konteks bundle di background — tidak block response.
    background_tasks.add_task(
        _build_preload_background, kode, payload.obyek, str(payload.skill), folder,
    )

    return PenugasanOut.model_validate(p)


async def _dokumen_status_map(db: AsyncSession, penugasan_ids: list[int]) -> dict[int, list[str]]:
    """Status semua dokumen di-group per penugasan_id (untuk derive status)."""
    out: dict[int, list[str]] = {}
    if not penugasan_ids:
        return out
    rows = (
        await db.execute(
            select(Dokumen.penugasan_id, Dokumen.status).where(
                Dokumen.penugasan_id.in_(penugasan_ids)
            )
        )
    ).all()
    for pid, st in rows:
        out.setdefault(pid, []).append(st if isinstance(st, str) else st.value)
    return out


def _with_derived_status(p: Penugasan, dok_statuses: list[str]) -> PenugasanOut:
    out = PenugasanOut.model_validate(p)
    out.status = compute_penugasan_status(Path(p.folder_path), dok_statuses, stored_status=p.status)
    return out


@router.get("", response_model=list[PenugasanOut])
async def list_penugasan(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PenugasanOut]:
    rows = (await db.execute(select(Penugasan).order_by(Penugasan.created_at.desc()))).scalars().all()
    dok_map = await _dokumen_status_map(db, [r.id for r in rows])
    return [_with_derived_status(r, dok_map.get(r.id, [])) for r in rows]


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
    dok_map = await _dokumen_status_map(db, [p.id])
    return _with_derived_status(p, dok_map.get(p.id, []))


@router.delete("/{penugasan_id}", status_code=status.HTTP_200_OK)
async def delete_penugasan(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Hapus penugasan beserta seluruh file di disk (hard delete). Hanya PT.

    Cascade ORM menghapus dokumen + agent_runs terkait. Folder penugasan di
    disk dihapus permanen.
    """
    user, role = current
    if role != Role.PT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Hanya Pengendali Teknis (PT) yang boleh hapus penugasan. Role Anda: {role.value}.",
        )
    p = await _get_penugasan_or_404(db, penugasan_id)
    folder = Path(p.folder_path)
    kode = p.kode

    await db.delete(p)
    await db.commit()
    delete_penugasan_folder(folder)

    return {"ok": True, "deleted": kode, "folder_removed": str(folder)}


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


# ============================================================
# SIMWAS sync — terima PKP dari SIMWAS → sasaran-assignment.json
#
# W1.1 versi v7 (asli "agen baca KP/PKP PDF" sudah dibatalkan). Sekarang KT
# isi manual via tab Setup ATAU, untuk masa depan integrasi SIMWAS, frontend
# fetch PKP dari API SIMWAS lalu kirim ke endpoint ini sebagai `pkp_rows`.
# Hari ini dipakai dgn paste JSON manual (source='manual') — lihat fixture
# app/fixtures/simwas-sample-pkp.json. Saat API SIMWAS live, ganti ke
# source='api' (saat ini placeholder 501 sampai kontrak resmi tersedia).
# ============================================================


class SimwasPkpRow(BaseModel):
    """Satu baris PKP dari SIMWAS (1 langkah_kerja per baris pivot).

    Field-nya menebak struktur SIMWAS dari kartu "Detail Pelaksanaan Penugasan"
    tab PKP: kolom (sasaran, langkah_kerja, dilaksanakan_oleh, waktu, No KKP).
    `sasaran_id` opsional — kalau SIMWAS belum punya ID terpisah, kita auto-
    generate (`S-RKA-NN` / `S-PBJ-NN` / `S-NN`).
    """

    sasaran: str = Field(default="", description="Deskripsi sasaran reviu (jadi grouping key). Baris kosong di-skip.")
    langkah_kerja: str | None = Field(default=None, description="1 langkah per baris; di-aggregate per sasaran")
    dilaksanakan_oleh: str | None = Field(default=None, description="Nama anggota tim yg ditugaskan")
    waktu: str | None = Field(default=None, description="Periode kerja — disimpan untuk audit trail, tdk masuk sasaran-assignment")
    no_kkp: str | None = Field(default=None, description="Nomor KKP yg di-track SIMWAS — disimpan untuk audit trail")
    sasaran_id: str | None = Field(default=None, description="Opsional. Kalau SIMWAS punya, dipakai; kalau tidak, auto-generate.")


class SimwasSyncPayload(BaseModel):
    """Body POST /penugasan/{id}/sasaran/sync-from-simwas."""

    source: Literal["manual", "api"] = Field(
        default="manual",
        description="`manual` = paste JSON (testing hari ini). `api` = pull live dari SIMWAS (501 sampai integrasi resmi).",
    )
    strategy: Literal["replace", "append"] = Field(
        default="replace",
        description="`replace` = overwrite sasaran-assignment.json. `append` = tambahkan ke yang sudah ada (anti-dup by sasaran_id).",
    )
    pkp_rows: list[SimwasPkpRow]


def _generate_sasaran_id(prefix: str | None, counter: int) -> str:
    """Skill-aware ID: reviu-rka-kl → S-RKA-NN; reviu-pengadaan → S-PBJ-NN; lain → S-NN."""
    if prefix:
        return f"S-{prefix}-{counter:02d}"
    return f"S-{counter:02d}"


def _skill_prefix(skill_value: str) -> str | None:
    mapping = {
        "reviu-rka-kl": "RKA",
        "reviu-pengadaan": "PBJ",
        "audit-kinerja": "KIN",
        "audit-pengadaan": "PBJ",
        "pemantauan-pengadaan": "PBJ",
        "pemantauan-tindak-lanjut": "TL",
        "evaluasi-spip": "SPIP",
        "evaluasi-sakip": "SAKIP",
        "evaluasi-manajemen-risiko": "MR",
        "evaluasi-reformasi-birokrasi": "RB",
        "kepatuhan-saipi": "SAIPI",
        "konsultasi-pengadaan": "KONS",
    }
    return mapping.get(skill_value)


def pkp_rows_to_sasaran(
    rows: list[SimwasPkpRow],
    skill_value: str,
    existing_ids: set[str] | None = None,
) -> list[SasaranItem]:
    """Group flat PKP rows → SasaranItem records.

    Deterministik (no LLM). Aturan:
    - Grouping key = `sasaran_id` (kalau ada) else `sasaran` (deskripsi).
    - `langkah_kerja` di-dedup per sasaran (order-preserving).
    - `assigned_to` di-dedup per sasaran (order-preserving).
    - `sasaran_id` di-auto-generate per skill bila kosong; counter melompati
      `existing_ids` (penting untuk strategy='append' supaya tidak tabrakan
      dengan ID yang sudah ada di sasaran-assignment.json).
    - Status default `AKTIF`.
    - Baris dengan `sasaran` kosong di-skip (anti-junk).
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        key = (row.sasaran_id or row.sasaran or "").strip()
        if not key:
            continue
        if key not in groups:
            groups[key] = {
                "sasaran_id": (row.sasaran_id or "").strip() or None,
                "deskripsi": (row.sasaran or "").strip(),
                "assigned_to": [],
                "langkah_kerja": [],
            }
            order.append(key)
        g = groups[key]
        lk = (row.langkah_kerja or "").strip()
        if lk and lk not in g["langkah_kerja"]:
            g["langkah_kerja"].append(lk)
        ao = (row.dilaksanakan_oleh or "").strip()
        if ao and ao not in g["assigned_to"]:
            g["assigned_to"].append(ao)

    prefix = _skill_prefix(skill_value)
    used_ids: set[str] = set(existing_ids or set())
    result: list[SasaranItem] = []
    counter = 1
    for key in order:
        g = groups[key]
        sid = g["sasaran_id"]
        if not sid:
            while True:
                candidate = _generate_sasaran_id(prefix, counter)
                counter += 1
                if candidate not in used_ids:
                    sid = candidate
                    break
        used_ids.add(sid)
        result.append(
            SasaranItem(
                sasaran_id=sid,
                deskripsi=g["deskripsi"],
                assigned_to=g["assigned_to"],
                langkah_kerja=g["langkah_kerja"],
                status="AKTIF",
            )
        )
    return result


@router.post("/{penugasan_id}/sasaran/sync-from-simwas")
async def sync_sasaran_from_simwas(
    penugasan_id: int,
    payload: SimwasSyncPayload,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Konversi PKP SIMWAS → `_PKP/sasaran-assignment.json`.

    PT/KT only. Default `source='manual'` (paste JSON; sah untuk test &
    bootstrap hari ini). `source='api'` masih 501 sampai kontrak REST/SSO
    SIMWAS resmi tersedia — saat itu frontend akan fetch PKP dari SIMWAS
    lalu mengirim ke endpoint ini dengan source='api' + token sesi.
    """
    user, role = current
    _require_sasaran_setup_role(role)

    if payload.source == "api":
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "Pull live dari API SIMWAS belum aktif. Gunakan source='manual' "
            "(paste payload PKP). Akan hidup setelah kontrak API + SSO SIMWAS resmi.",
        )

    if not payload.pkp_rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "pkp_rows kosong — tidak ada yang di-sync.")

    p = await _get_penugasan_or_404(db, penugasan_id)
    skill_value = p.skill if isinstance(p.skill, str) else p.skill.value

    folder = Path(p.folder_path)
    path = folder / "_PKP" / "sasaran-assignment.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Pre-load existing IDs supaya converter melompati saat append (anti-tabrakan
    # auto-gen counter dgn ID yang sudah ada).
    existing_sasaran: list[dict] = []
    existing_ids: set[str] = set()
    if payload.strategy == "append" and path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_sasaran = existing.get("sasaran") or []
            existing_ids = {
                str(s.get("sasaran_id")) for s in existing_sasaran
                if isinstance(s, dict) and s.get("sasaran_id")
            }
        except (json.JSONDecodeError, OSError):
            existing_sasaran = []
            existing_ids = set()

    converted = pkp_rows_to_sasaran(payload.pkp_rows, skill_value, existing_ids=existing_ids)
    if not converted:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tidak ada sasaran valid setelah grouping — periksa field 'sasaran' di pkp_rows.",
        )

    if payload.strategy == "append":
        # Anti-dup berdasar sasaran_id explicit (yang muncul di PKP rows dgn ID).
        # Converter sudah memastikan auto-gen tidak tabrakan dgn existing_ids,
        # jadi yang bisa duplicate hanyalah sasaran_id eksplisit.
        final_sasaran = list(existing_sasaran)
        added_ids: list[str] = []
        for s in converted:
            if s.sasaran_id in existing_ids:
                continue
            final_sasaran.append(s.model_dump())
            added_ids.append(s.sasaran_id)
    else:
        final_sasaran = [s.model_dump() for s in converted]
        added_ids = [s.sasaran_id for s in converted]

    data = {
        "penugasan_id": p.kode,
        "skill": skill_value,
        "schema_version": "v4.0.0",
        "tanggal_dibuat": datetime.utcnow().isoformat() + "Z",
        "sasaran": final_sasaran,
        "sumber_import": f"simwas-{payload.source}",
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "source": payload.source,
        "strategy": payload.strategy,
        "total_input_rows": len(payload.pkp_rows),
        "total_sasaran": len(final_sasaran),
        "added_sasaran": added_ids,
        "added_count": len(added_ids),
        "skipped_duplicate": len(converted) - len(added_ids) if payload.strategy == "append" else 0,
    }


# ============================================================
# Setup template — saran sasaran dari penugasan lalu, skeleton pattern,
# & catatan W3 writeback. Tujuan: KT tidak mulai dari nol.
# ============================================================


@router.get("/{penugasan_id}/sasaran/templates")
async def get_sasaran_templates(
    penugasan_id: int,
    source: str = "all",  # all | historis | patterns | writeback
    _current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Saran template setup penugasan dari 3 sumber paralel.

    - `historis`: penugasan v7 dgn skill sama, di-rank by similarity obyek
      (Jaccard atas token kata, stopword ID dibuang).
    - `patterns`: sasaran skeleton dari kategori pattern wiki — 1 sasaran per
      kategori, langkah_kerja merefer ID pattern dominan.
    - `writeback`: catatan `pengawasan-*.md` di vault llm-wiki (W3) yg related;
      ini KONTEKS, bukan sasaran (writeback tidak menyimpan sasaran eksplisit).

    `source='all'` (default) kembalikan ketiganya. Auditor PT/KT yg setup di
    UI memilih sumber + 1 entry, lalu pre-fill sasaran-assignment.json.
    """
    from app import knowledge_browse

    p = await _get_penugasan_or_404(db, penugasan_id)
    skill_value = p.skill if isinstance(p.skill, str) else p.skill.value
    obyek = p.obyek or ""

    result: dict[str, Any] = {
        "skill": skill_value,
        "obyek": obyek,
    }

    if source in ("all", "historis"):
        # Tarik semua penugasan lain (exclude self) untuk di-scan
        rows = (
            await db.execute(
                select(
                    Penugasan.kode,
                    Penugasan.obyek,
                    Penugasan.skill,
                    Penugasan.folder_path,
                    Penugasan.status,
                ).where(Penugasan.id != penugasan_id)
            )
        ).all()
        candidates = [
            {
                "kode": r[0],
                "obyek": r[1],
                "skill": r[2] if isinstance(r[2], str) else getattr(r[2], "value", str(r[2])),
                "folder_path": r[3],
                "status": r[4] if isinstance(r[4], str) else getattr(r[4], "value", str(r[4])),
            }
            for r in rows
        ]
        result["historis"] = knowledge_browse.suggest_templates_from_history(
            skill=skill_value,
            obyek=obyek,
            candidates=candidates,
            top_n=5,
        )

    if source in ("all", "patterns"):
        result["patterns"] = knowledge_browse.suggest_skeleton_from_patterns(skill_value)

    if source in ("all", "writeback"):
        result["writeback"] = knowledge_browse.suggest_context_from_writeback(
            skill=skill_value,
            obyek=obyek,
            top_n=5,
        )

    return result


@router.get("/{penugasan_id}/context-readiness")
async def get_context_readiness(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Prasyarat tombol Generate Context: sasaran (KT) + bahan analisis (AT).

    Bahan = dokumen ter-digest (RKA/PBJ) atau kriteria/objek (criteria-driven).
    """
    p = await _get_penugasan_or_404(db, penugasan_id)
    input_jenis = (
        await db.execute(
            select(Dokumen.jenis).where(
                Dokumen.penugasan_id == p.id,
                Dokumen.status == DokumenStatus.READY,
            )
        )
    ).scalars().all()
    has_input = any((j or "").upper() in INPUT_JENIS for j in input_jenis)
    return context_readiness(Path(p.folder_path), skill=p.skill, has_input_docs=has_input)


@router.get("/{penugasan_id}/gates")
async def get_gates(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Status evaluasi bertahap (gate-based). Untuk skill non-bertahap → gated=false.

    Mengembalikan daftar gate (dari registry) + progress (penilaian-progress.json)
    bila sudah diinisialisasi. Dipakai panel Gate di UI.
    """
    from app import gate_registry as greg
    from app.tools.gate_tools import read_progress

    p = await _get_penugasan_or_404(db, penugasan_id)
    skill = p.skill if isinstance(p.skill, str) else p.skill.value
    if not greg.skill_has_gates(skill):
        return {"gated": False, "skill": skill, "gates": [], "progress": None}
    return {
        "gated": True,
        "skill": skill,
        "gates": greg.list_gates(skill),
        "progress": read_progress(Path(p.folder_path)),
    }


@router.post("/{penugasan_id}/gates/{gate_id}/decision")
async def decide_gate(
    penugasan_id: int,
    gate_id: str,
    body: dict = Body(...),
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Keputusan auditor atas satu gate evaluasi bertahap: LANJUT / KOREKSI / ULANG.

    Auto-init progress bila belum ada. Hanya untuk skill bertahap (SPIP/SAKIP/RB).
    """
    from app import gate_registry as greg
    from app.tools.gate_tools import init_progress, read_progress, record_result

    user, role = current
    if role == Role.PM:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PM tidak menjalankan keputusan gate.")
    p = await _get_penugasan_or_404(db, penugasan_id)
    skill = p.skill if isinstance(p.skill, str) else p.skill.value
    if not greg.skill_has_gates(skill):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Skill '{skill}' bukan evaluasi bertahap.")

    folder = Path(p.folder_path)
    if read_progress(folder) is None:
        init_progress(folder, skill)
    res = record_result(folder, gate_id, str(body.get("decision", "")), str(body.get("catatan", "")))
    if "error" in res:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res["error"])
    return {"ok": True, "progress": res}


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


# ============================================================
# Preload Context Bundle (Prioritas 1 — peningkatan kualitas)
# Bangun konteks 4-sumber sebelum agen jalan supaya agen mulai dgn tangan penuh.
# ============================================================


@router.post("/{penugasan_id}/preload-context")
async def build_preload_context(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bangun/rebuild bundle konteks pra-loaded utk satu penugasan.

    Sumber: vault llm-wiki + pattern wiki + konteks pendukung + riwayat W3.
    Bundle disimpan sbg `_PRELOAD/context-bundle.md`. Agen baca via tool
    `read_preload_context`.
    """
    from app import preload_context

    _, role = current
    if role not in (Role.PT, Role.KT, Role.AT):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Build konteks pra-loaded hanya untuk PT/KT/AT. Role: {role.value}.",
        )
    p = await _get_penugasan_or_404(db, penugasan_id)
    skill_value = p.skill if isinstance(p.skill, str) else p.skill.value
    result = preload_context.build_preload_bundle(
        penugasan_kode=p.kode,
        obyek=p.obyek or "",
        skill=skill_value,
    )
    folder = Path(p.folder_path)
    target = preload_context.save_preload_bundle(folder, result["markdown"])
    return {
        "ok": True,
        "path": str(target.relative_to(folder)),
        "stats": result["stats"],
    }


@router.get("/{penugasan_id}/preload-context/status")
async def get_preload_context_status(
    penugasan_id: int,
    _current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cek apakah bundle sudah dibangun + statistik singkat."""
    p = await _get_penugasan_or_404(db, penugasan_id)
    folder = Path(p.folder_path)
    bundle = folder / "_PRELOAD" / "context-bundle.md"
    if not bundle.exists():
        return {"exists": False}
    stat = bundle.stat()
    text = bundle.read_text(encoding="utf-8")
    return {
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
        "char_count": len(text),
        "preview_head": text[:500],
    }


# ============================================================
# Per-Temuan Review (Prioritas 2 — HITL per-temuan)
# Auditor approve/reject tiap temuan sebelum render KKP final.
# ============================================================


def _load_temuan_json(folder: Path) -> list[dict]:
    """Baca `_KKP/temuan.json` → list temuan dict. Return [] kalau tidak ada."""
    p = folder / "_KKP" / "temuan.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out = data.get("temuan") if isinstance(data, dict) else []
    return out if isinstance(out, list) else []


@router.get("/{penugasan_id}/temuan-review")
async def list_temuan_review(
    penugasan_id: int,
    _current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List semua temuan + status review (semua role bisa baca)."""
    p = await _get_penugasan_or_404(db, penugasan_id)
    folder = Path(p.folder_path)
    temuan_list = _load_temuan_json(folder)

    # Ambil semua review row utk penugasan ini
    rows = (
        await db.execute(select(TemuanReview).where(TemuanReview.penugasan_id == penugasan_id))
    ).scalars().all()
    by_temuan_id: dict[str, TemuanReview] = {r.temuan_id: r for r in rows}

    items: list[dict] = []
    for t in temuan_list:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id_temuan") or "").strip()
        if not tid:
            continue
        rev = by_temuan_id.get(tid)
        # Apply overlay edit kalau ada — tampilkan versi terkini ke UI
        edited = rev.edited_fields if rev and rev.edited_fields else {}
        judul = edited.get("judul_temuan") or t.get("judul_temuan") or ""
        kondisi = edited.get("kondisi") or t.get("kondisi") or ""
        kriteria = edited.get("kriteria") or t.get("kriteria") or ""
        akibat = edited.get("akibat") or t.get("akibat") or ""
        items.append({
            "id_temuan": tid,
            "judul": judul,
            "sasaran_id": t.get("sasaran_id") or "",
            "kondisi": kondisi[:400],
            "kriteria": kriteria[:400],
            "akibat": akibat[:400],
            "anggota": ((t.get("anggota_tim") or {}).get("nama_lengkap") or "") if isinstance(t.get("anggota_tim"), dict) else "",
            "dokumen_sumber_count": len(t.get("dokumen_sumber") or []) if isinstance(t.get("dokumen_sumber"), list) else 0,
            "status": rev.status if rev else "PENDING",
            "note": rev.note if rev else None,
            "reviewed_at": rev.reviewed_at.isoformat() + "Z" if rev and rev.reviewed_at else None,
            "reviewed_by_user_id": rev.reviewed_by_user_id if rev else None,
            "has_edits": bool(edited),
            "edited_fields": edited or None,  # full edit overlay (UI bisa pakai untuk diff/preview)
        })

    counts = {"PENDING": 0, "APPROVED": 0, "REJECTED": 0, "EDITED": 0}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    return {"total": len(items), "counts": counts, "items": items}


class TemuanReviewAction(BaseModel):
    note: str | None = None


@router.post("/{penugasan_id}/temuan-review/{temuan_id}/approve")
async def approve_temuan(
    penugasan_id: int,
    temuan_id: str,
    payload: TemuanReviewAction = Body(default_factory=TemuanReviewAction),
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Setujui temuan — masuk ke KKP/LHR final. AT/KT/PT boleh."""
    user, role = current
    if role not in (Role.AT, Role.KT, Role.PT, Role.PM):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role {role.value} tidak bisa approve.")
    await _get_penugasan_or_404(db, penugasan_id)
    return await _upsert_review(db, penugasan_id, temuan_id, "APPROVED", payload.note, user.id)


@router.post("/{penugasan_id}/temuan-review/{temuan_id}/reject")
async def reject_temuan(
    penugasan_id: int,
    temuan_id: str,
    payload: TemuanReviewAction = Body(default_factory=TemuanReviewAction),
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Tolak temuan — tidak masuk KKP/LHR. KT/PT/PM only."""
    user, role = current
    if role not in (Role.KT, Role.PT, Role.PM):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Tolak temuan hanya untuk KT/PT/PM. Role: {role.value}.",
        )
    await _get_penugasan_or_404(db, penugasan_id)
    return await _upsert_review(db, penugasan_id, temuan_id, "REJECTED", payload.note, user.id)


class TemuanEditPayload(BaseModel):
    """Field temuan yang bisa diedit auditor via UI.

    Semua optional — hanya field yang dikirim yang di-overlay. Field lain
    tetap pakai versi agen di temuan.json.
    """
    judul_temuan: str | None = None
    kondisi: str | None = None
    kriteria: str | None = None
    akibat: str | None = None
    note: str | None = None  # catatan kenapa diedit


@router.put("/{penugasan_id}/temuan-review/{temuan_id}/edit")
async def edit_temuan(
    penugasan_id: int,
    temuan_id: str,
    payload: TemuanEditPayload,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Edit field temuan via overlay (judul/kondisi/kriteria/akibat). KT/PT/PM only.

    Strategi: temuan.json (sumber kebenaran V6) TIDAK diubah. Edit disimpan di
    `TemuanReview.edited_fields` (JSONB). Saat render KKP, v7 overlay edited_fields
    ke temuan asli sebelum panggil V6.

    Status auto-set ke "EDITED" (tetap masuk render bersama APPROVED). Auditor bisa
    re-approve/reject kapan saja setelah edit.

    Field yang KOSONG di payload → tidak ubah overlay (tidak hapus edit lama).
    Untuk hapus edit field tertentu, kirim string kosong eksplisit "".
    """
    user, role = current
    if role not in (Role.KT, Role.PT, Role.PM):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Edit temuan hanya untuk KT/PT/PM. Role: {role.value}.",
        )
    await _get_penugasan_or_404(db, penugasan_id)

    # Verifikasi temuan ada di temuan.json
    p = await _get_penugasan_or_404(db, penugasan_id)
    folder = Path(p.folder_path)
    temuan_list = _load_temuan_json(folder)
    found = next(
        (t for t in temuan_list if isinstance(t, dict) and str(t.get("id_temuan") or "").strip() == temuan_id),
        None,
    )
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Temuan {temuan_id} tidak ditemukan di temuan.json.",
        )

    # Upsert review row
    existing = (
        await db.execute(
            select(TemuanReview).where(
                TemuanReview.penugasan_id == penugasan_id,
                TemuanReview.temuan_id == temuan_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = TemuanReview(
            penugasan_id=penugasan_id,
            temuan_id=temuan_id,
            status="EDITED",
            edited_fields={},
        )
        db.add(existing)
        await db.flush()

    # Merge edits (existing edited_fields + new payload)
    edits: dict = dict(existing.edited_fields or {})
    payload_dict = payload.model_dump(exclude_none=True, exclude={"note"})
    for k, v in payload_dict.items():
        # String "" → hapus overlay key (revert ke versi agen)
        if v == "":
            edits.pop(k, None)
        else:
            edits[k] = v

    existing.edited_fields = edits or None
    existing.status = "EDITED" if edits else "PENDING"
    if payload.note is not None:
        existing.note = payload.note
    existing.reviewed_by_user_id = user.id
    existing.reviewed_at = datetime.utcnow()
    await db.commit()

    return {
        "ok": True,
        "id_temuan": temuan_id,
        "status": existing.status,
        "edited_fields": existing.edited_fields,
        "has_edits": bool(existing.edited_fields),
        "reviewed_at": existing.reviewed_at.isoformat() + "Z" if existing.reviewed_at else None,
    }


@router.post("/{penugasan_id}/temuan-review/bulk-approve")
async def bulk_approve_temuan(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Setujui SEMUA temuan PENDING sekaligus — efisiensi auditor senior."""
    user, role = current
    if role not in (Role.KT, Role.PT, Role.PM):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Bulk approve hanya untuk KT/PT/PM. Role: {role.value}.",
        )
    p = await _get_penugasan_or_404(db, penugasan_id)
    folder = Path(p.folder_path)
    temuan_list = _load_temuan_json(folder)
    rows = (
        await db.execute(select(TemuanReview).where(TemuanReview.penugasan_id == penugasan_id))
    ).scalars().all()
    by_temuan_id = {r.temuan_id: r for r in rows}

    n_approved = 0
    for t in temuan_list:
        tid = str(t.get("id_temuan") or "").strip()
        if not tid:
            continue
        existing = by_temuan_id.get(tid)
        if existing and existing.status == "APPROVED":
            continue  # already approved
        if existing:
            existing.status = "APPROVED"
            existing.reviewed_by_user_id = user.id
            existing.reviewed_at = datetime.utcnow()
        else:
            db.add(TemuanReview(
                penugasan_id=penugasan_id,
                temuan_id=tid,
                status="APPROVED",
                reviewed_by_user_id=user.id,
                reviewed_at=datetime.utcnow(),
            ))
        n_approved += 1
    await db.commit()
    return {"ok": True, "approved_count": n_approved, "total_temuan": len(temuan_list)}


async def _upsert_review(
    db: AsyncSession,
    penugasan_id: int,
    temuan_id: str,
    status_new: str,
    note: str | None,
    user_id: int,
) -> dict[str, Any]:
    """Upsert TemuanReview row + commit."""
    existing = (
        await db.execute(
            select(TemuanReview).where(
                TemuanReview.penugasan_id == penugasan_id,
                TemuanReview.temuan_id == temuan_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.status = status_new
        existing.note = note
        existing.reviewed_by_user_id = user_id
        existing.reviewed_at = datetime.utcnow()
    else:
        existing = TemuanReview(
            penugasan_id=penugasan_id,
            temuan_id=temuan_id,
            status=status_new,
            note=note,
            reviewed_by_user_id=user_id,
            reviewed_at=datetime.utcnow(),
        )
        db.add(existing)
    await db.commit()
    return {
        "ok": True,
        "id_temuan": temuan_id,
        "status": status_new,
        "reviewed_at": existing.reviewed_at.isoformat() + "Z" if existing.reviewed_at else None,
    }
