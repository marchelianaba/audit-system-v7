"""Routes CACM / EWS SIRUP — C1a (ingest offline) + usulan penugasan.

Menerima hasil evaluasi EWS SIRUP dari agent tim (folder CACM/ews-system-delivery).
Untuk C1a, intake lewat file/sample (POST /cacm/ingest, /ingest-sample). C1b nanti
menambah webhook HMAC + pull REST. Finding MERAH/KUNING bisa dipromosikan PT menjadi
Penugasan berstatus USULAN_CACM (prefilled konteks dari finding).

Format hasil EWS (lihat CACM/.../sample-ews-hasil.json): LIST berisi item rekap
(`{"rekap": {...}}`, 1 per satker) + item finding (punya `kode`, `status`,
MERAH→judul+penjelasan, KUNING/INFO→ringkasan).
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import CacmRun, EwsFinding, Penugasan, PenugasanStatus, Role, Skill, User
from app.routes.penugasan import _scaffold_penugasan_files
from app.schemas import PenugasanCreate
from app.storage import gen_kode_penugasan, penugasan_folder

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/cacm", tags=["cacm"])

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "cacm-sample-ews-hasil.json"
_PROMOTABLE = {"MERAH", "KUNING"}


def _require_pt(role: Role) -> None:
    if role != Role.PT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Hanya Pengendali Teknis (PT) yang boleh aksi ini. Role Anda: {role.value}.",
        )


def _verify_signature(raw: bytes, header: str, secret: str) -> bool:
    """Verifikasi X-Agent-Signature: sha256=<hex hmac-sha256(raw, secret)>.

    Cocok dengan signer agent tim (lihat INTEGRATION_GUIDE.md). Pakai
    compare_digest agar tahan timing attack.
    """
    if not header or not header.startswith("sha256="):
        return False
    provided = header[7:]
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def _normalize(payload: Any) -> tuple[list[dict], list[dict], dict]:
    """Pisahkan (findings, rekap_rows, meta) dari berbagai bentuk payload EWS."""
    meta: dict = {}
    items: list = []
    rekap_rows: list[dict] = []

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
        items = payload.get("hasil") or payload.get("findings") or []
        # rekap bisa terpisah: {meta, rekap:[...]} atau list langsung
        rk = payload.get("rekap")
        if isinstance(rk, dict) and isinstance(rk.get("rekap"), list):
            rekap_rows = rk["rekap"]
        elif isinstance(rk, list):
            rekap_rows = rk

    findings: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if "rekap" in it and isinstance(it["rekap"], dict):
            rekap_rows.append(it["rekap"])
        elif it.get("kode"):
            findings.append(it)
    return findings, rekap_rows, meta


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


async def _ingest(db: AsyncSession, payload: Any, source: str) -> CacmRun:
    findings, rekap_rows, meta = _normalize(payload)
    if not findings:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Tidak ada finding (item dengan 'kode') di payload EWS.",
        )

    counts = {"total": len(findings), "merah": 0, "kuning": 0, "hijau": 0, "info": 0}
    for f in findings:
        st = str(f.get("status", "")).upper()
        key = {"MERAH": "merah", "KUNING": "kuning", "HIJAU": "hijau", "INFO": "info"}.get(st)
        if key:
            counts[key] += 1

    # Webhook payload menaruh runId/completedAt di top-level (bukan di meta).
    top_run_id = payload.get("runId") or payload.get("run_id") if isinstance(payload, dict) else None
    top_tanggal = payload.get("completedAt") or payload.get("startedAt") if isinstance(payload, dict) else None
    if not meta.get("tanggal_evaluasi") and top_tanggal:
        meta["tanggal_evaluasi"] = top_tanggal

    run_id = str(
        meta.get("run_id")
        or meta.get("runId")
        or top_run_id
        or f"{source}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    )
    # Jaga unik
    if (await db.execute(select(CacmRun).where(CacmRun.run_id == run_id))).scalar_one_or_none():
        run_id = f"{run_id}-{datetime.utcnow().strftime('%H%M%S%f')}"

    run = CacmRun(
        run_id=run_id,
        source=source,
        tanggal_evaluasi=meta.get("tanggal_evaluasi"),
        periode_crawl=meta.get("periode_crawl"),
        periode_crawl_sebelumnya=meta.get("periode_crawl_sebelumnya"),
        summary=counts,
        rekap=rekap_rows,
    )
    db.add(run)
    await db.flush()

    for f in findings:
        db.add(EwsFinding(
            cacm_run_id=run.id,
            kode=str(f.get("kode", ""))[:20],
            satker=str(f.get("satker", ""))[:200],
            satker_kode=(str(f.get("satker_kode")) if f.get("satker_kode") else None),
            status=str(f.get("status", ""))[:20],
            judul=f.get("judul"),
            penjelasan=f.get("penjelasan"),
            ringkasan=f.get("ringkasan"),
            nilai_aktual=f.get("nilai_aktual"),
            jumlah_paket_terdampak=_to_int(f.get("jumlah_paket_terdampak")),
            total_nilai_terdampak=_to_int(f.get("total_nilai_terdampak")),
            threshold=f.get("threshold"),
            regulasi=f.get("regulasi"),
            rekomendasi=f.get("rekomendasi"),
            paket_detail=f.get("paket_detail") if isinstance(f.get("paket_detail"), list) else [],
        ))

    await db.commit()
    await db.refresh(run)
    await _maybe_auto_promote(db, run, source)
    return run


def _run_summary_dict(run: CacmRun, n_findings: int) -> dict:
    return {
        "id": run.id,
        "run_id": run.run_id,
        "source": run.source,
        "tanggal_evaluasi": run.tanggal_evaluasi,
        "periode_crawl": run.periode_crawl,
        "summary": run.summary or {},
        "total_findings": n_findings,
        "received_at": run.received_at.isoformat() if run.received_at else None,
    }


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_ews(
    payload: Any = Body(...),
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest hasil EWS SIRUP (isi sample-ews-hasil.json: list rekap+findings)."""
    user, role = current
    _require_pt(role)
    run = await _ingest(db, payload, source="offline")
    return {"ok": True, **_run_summary_dict(run, run.summary.get("total", 0))}


@router.post("/ingest-sample", status_code=status.HTTP_201_CREATED)
async def ingest_sample(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest fixture contoh (untuk demo C1a tanpa deploy agent)."""
    user, role = current
    _require_pt(role)
    if not _FIXTURE.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Fixture tidak ada: {_FIXTURE.name}")
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    run = await _ingest(db, payload, source="offline")
    return {"ok": True, "sample": True, **_run_summary_dict(run, run.summary.get("total", 0))}


@router.get("/runs")
async def list_runs(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(select(CacmRun).order_by(CacmRun.received_at.desc()))
    ).scalars().all()
    out = []
    for r in rows:
        n = len(
            (await db.execute(select(EwsFinding).where(EwsFinding.cacm_run_id == r.id)))
            .scalars().all()
        )
        out.append(_run_summary_dict(r, n))
    return {"total": len(out), "runs": out}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    run = (await db.execute(select(CacmRun).where(CacmRun.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run tidak ditemukan")
    findings = (
        await db.execute(
            select(EwsFinding).where(EwsFinding.cacm_run_id == run.id).order_by(EwsFinding.id)
        )
    ).scalars().all()
    return {
        **_run_summary_dict(run, len(findings)),
        "rekap": run.rekap or [],
        "findings": [
            {
                "id": f.id,
                "kode": f.kode,
                "satker": f.satker,
                "satker_kode": f.satker_kode,
                "status": f.status,
                "judul": f.judul,
                "penjelasan": f.penjelasan,
                "ringkasan": f.ringkasan,
                "nilai_aktual": f.nilai_aktual,
                "jumlah_paket_terdampak": f.jumlah_paket_terdampak,
                "total_nilai_terdampak": f.total_nilai_terdampak,
                "threshold": f.threshold,
                "regulasi": f.regulasi,
                "rekomendasi": f.rekomendasi,
                "paket_detail": f.paket_detail or [],
                "tindak_lanjut": f.tindak_lanjut,
                "penugasan_id": f.penugasan_id,
                "promotable": f.status.upper() in _PROMOTABLE,
            }
            for f in findings
        ],
    }


async def _create_usulan_from_finding(db: AsyncSession, f: EwsFinding) -> Penugasan:
    """Buat Penugasan USULAN_CACM prefilled dari 1 finding. TIDAK commit & TIDAK
    set field finding — caller yang mengatur f.tindak_lanjut/penugasan_id + commit.
    Dipakai oleh promote manual (PT) maupun auto-promote (C2)."""
    judul_singkat = (f.judul or f.ringkasan or f.kode)[:120]
    obyek = f"Reviu Pengadaan {f.satker} — {f.kode}: {judul_singkat}"[:400]

    kode_pen = gen_kode_penugasan("reviu-pengadaan")
    folder = penugasan_folder(kode_pen)
    payload = PenugasanCreate(obyek=obyek, skill=Skill.REVIU_PENGADAAN, nomor_st=None, tanggal_st=None)
    _scaffold_penugasan_files(folder=folder, kode=kode_pen, payload=payload, ketua_tim_name=None)

    paket_lines = "\n".join(
        f"  - {p.get('nama') or p.get('nama_paket','')} — Rp {(_to_int(p.get('pagu'))):,} "
        f"({p.get('metode','')}, {p.get('jenis','')})"
        for p in (f.paket_detail or [])[:15]
    )
    ews_section = (
        f"\n\n## Sinyal CACM / EWS SIRUP (sumber usulan penugasan)\n\n"
        f"- Kode EWS: {f.kode} ({f.status})\n"
        f"- Satker: {f.satker}\n"
        f"- Nilai aktual: {f.nilai_aktual or '-'}\n"
        f"- Paket terdampak: {f.jumlah_paket_terdampak} | Total nilai: Rp {f.total_nilai_terdampak:,}\n"
        f"- Threshold: {f.threshold or '-'}\n"
        f"- Regulasi: {f.regulasi or '-'}\n"
        f"- Rekomendasi awal EWS: {f.rekomendasi or '-'}\n\n"
        f"Penjelasan:\n{f.penjelasan or f.ringkasan or '-'}\n"
        + (f"\nPaket terdampak:\n{paket_lines}\n" if paket_lines else "")
        + "\n> Sumber: SIRUP (data RUP/perencanaan). HPS/pemenang/kontrak ada di SPSE — verifikasi lanjutan.\n"
    )
    ctx_path = folder / "context.md"
    try:
        existing = ctx_path.read_text(encoding="utf-8") if ctx_path.exists() else ""
        ctx_path.write_text(existing + ews_section, encoding="utf-8")
    except OSError:
        pass

    p = Penugasan(
        kode=kode_pen,
        obyek=obyek,
        skill=Skill.REVIU_PENGADAAN,
        nomor_st=None,
        tanggal_st=None,
        status=PenugasanStatus.USULAN_CACM,
        ketua_tim_id=None,
        folder_path=str(folder),
    )
    db.add(p)
    await db.flush()
    return p


async def _open_usulan_exists(db: AsyncSession, satker_kode: str | None, kode: str) -> bool:
    """True bila sudah ada usulan TERBUKA (penugasan USULAN_CACM) untuk
    satker+kode EWS yang sama — anti-spam saat sinyal berulang tiap run."""
    if not satker_kode:
        return False
    pen_ids = (
        await db.execute(
            select(EwsFinding.penugasan_id).where(
                EwsFinding.satker_kode == satker_kode,
                EwsFinding.kode == kode,
                EwsFinding.tindak_lanjut == "DIPROMOSIKAN",
                EwsFinding.penugasan_id.is_not(None),
            )
        )
    ).scalars().all()
    if not pen_ids:
        return False
    open_pens = (
        await db.execute(
            select(Penugasan.id).where(
                Penugasan.id.in_(pen_ids),
                Penugasan.status == PenugasanStatus.USULAN_CACM,
            )
        )
    ).scalars().all()
    return len(open_pens) > 0


async def _maybe_auto_promote(db: AsyncSession, run: CacmRun, source: str) -> int:
    """C2 — otomasi: untuk sinyal LIVE (webhook/pull), otomatis buat usulan
    penugasan dari finding sesuai CACM_AUTO_PROMOTE, dengan anti-duplikat.
    Offline ingest (demo/manual) tidak di-auto-promote."""
    mode = (settings.cacm_auto_promote or "").strip().lower()
    if source not in ("webhook", "pull") or mode not in ("merah", "merah_kuning"):
        return 0
    statuses = {"MERAH"} if mode == "merah" else {"MERAH", "KUNING"}
    findings = (
        await db.execute(
            select(EwsFinding).where(
                EwsFinding.cacm_run_id == run.id,
                EwsFinding.tindak_lanjut == "BARU",
            )
        )
    ).scalars().all()
    count = 0
    for f in findings:
        if f.status.upper() not in statuses:
            continue
        if await _open_usulan_exists(db, f.satker_kode, f.kode):
            continue
        p = await _create_usulan_from_finding(db, f)
        f.tindak_lanjut = "DIPROMOSIKAN"
        f.penugasan_id = p.id
        count += 1
    if count:
        await db.commit()
        log.info("CACM auto-promote: %d usulan dibuat dari run %s (%s)", count, run.run_id, source)
    return count


@router.post("/findings/{finding_id}/promote", status_code=status.HTTP_201_CREATED)
async def promote_finding(
    finding_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Jadikan finding EWS sebagai Penugasan baru (status USULAN_CACM, prefilled)."""
    user, role = current
    _require_pt(role)

    f = (await db.execute(select(EwsFinding).where(EwsFinding.id == finding_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding tidak ditemukan")
    if f.tindak_lanjut == "DIPROMOSIKAN" and f.penugasan_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Finding sudah dipromosikan jadi penugasan #{f.penugasan_id}.",
        )
    if f.status.upper() not in _PROMOTABLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Status {f.status} tidak dapat dipromosikan (hanya MERAH/KUNING).",
        )

    p = await _create_usulan_from_finding(db, f)
    f.tindak_lanjut = "DIPROMOSIKAN"
    f.penugasan_id = p.id
    await db.commit()
    return {"ok": True, "penugasan_id": p.id, "kode": p.kode, "obyek": p.obyek}


@router.get("/usulan/pending")
async def pending_usulan(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Jumlah + daftar usulan CACM yang menunggu review PT (status USULAN_CACM).
    Dipakai frontend untuk badge notifikasi."""
    rows = (
        await db.execute(
            select(Penugasan)
            .where(Penugasan.status == PenugasanStatus.USULAN_CACM)
            .order_by(Penugasan.created_at.desc())
        )
    ).scalars().all()
    return {
        "count": len(rows),
        "items": [{"id": p.id, "kode": p.kode, "obyek": p.obyek} for p in rows],
    }


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(
    finding_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user, role = current
    _require_pt(role)
    f = (await db.execute(select(EwsFinding).where(EwsFinding.id == finding_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding tidak ditemukan")
    f.tindak_lanjut = "DIABAIKAN"
    await db.commit()
    return {"ok": True, "finding_id": finding_id, "tindak_lanjut": "DIABAIKAN"}


@router.post("/usulan/{penugasan_id}/accept")
async def accept_usulan(
    penugasan_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Terima usulan CACM → ubah status penugasan dari USULAN_CACM ke DRAFT
    sehingga masuk alur penugasan normal (KT setup, AT upload, dst)."""
    user, role = current
    _require_pt(role)
    p = (await db.execute(select(Penugasan).where(Penugasan.id == penugasan_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Penugasan tidak ditemukan")
    if p.status != PenugasanStatus.USULAN_CACM:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Penugasan bukan usulan CACM (status: {p.status}).",
        )
    p.status = PenugasanStatus.DRAFT
    await db.commit()
    return {"ok": True, "penugasan_id": penugasan_id, "status": "DRAFT"}


# ============================================================
# C1b — integrasi LIVE dengan agent EWS tim (webhook push + pull REST)
# ============================================================


@router.post("/ews-webhook")
async def ews_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Terima push hasil run dari agent EWS tim. Autentikasi mesin via HMAC
    `X-Agent-Signature` (BUKAN Bearer token — ini server-to-server).

    Retry policy agent: 4xx = permanent (tidak retry), 5xx = retry. Maka
    signature salah → 401 (permanent), error internal → biarkan 5xx.
    """
    secret = settings.cacm_webhook_secret
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Webhook belum dikonfigurasi (set CACM_WEBHOOK_SECRET).",
        )
    raw = await request.body()
    if not _verify_signature(raw, request.headers.get("X-Agent-Signature", ""), secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Body bukan JSON valid")

    if payload.get("event") == "run.failed" or payload.get("status") == "failed":
        return {"received": True, "note": "run.failed diabaikan"}

    run = await _ingest(db, payload, source="webhook")
    return {"received": True, "run_id": run.run_id, "findings": (run.summary or {}).get("total", 0)}


@router.post("/sync")
async def sync_from_agent(
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pull run terbaru dari agent EWS via REST (fallback/backfill push)."""
    user, role = current
    _require_pt(role)
    base = settings.cacm_agent_base_url.rstrip("/")
    key = settings.cacm_agent_api_key
    if not base or not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent belum dikonfigurasi (set CACM_AGENT_BASE_URL + CACM_AGENT_API_KEY).",
        )
    headers = {"X-API-Key": key}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{base}/api/v1/runs", headers=headers)
            r.raise_for_status()
            runs_resp = r.json()
            run_list = (
                runs_resp.get("items") or runs_resp.get("runs") or runs_resp.get("data")
                if isinstance(runs_resp, dict) else runs_resp
            ) or []
            if not run_list:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Agent tidak punya run.")
            latest_id = run_list[0].get("id") or run_list[0].get("runId")
            rr = await client.get(f"{base}/api/v1/runs/{latest_id}/result", headers=headers)
            rr.raise_for_status()
            result = rr.json()
            # result bisa berupa list findings, atau {findings, rekap, runId, ...}
            if isinstance(result, list):
                result = {"runId": str(latest_id), "findings": result}
            elif isinstance(result, dict):
                result.setdefault("runId", str(latest_id))
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Gagal ambil data agent: {e}")

    run = await _ingest(db, result, source="pull")
    return {"ok": True, **_run_summary_dict(run, (run.summary or {}).get("total", 0))}


@router.post("/trigger")
async def trigger_agent_run(
    current: tuple[User, Role] = Depends(get_current_user),
) -> dict:
    """Minta agent menjalankan run baru (manual). Hasil masuk via webhook/sync."""
    user, role = current
    _require_pt(role)
    base = settings.cacm_agent_base_url.rstrip("/")
    key = settings.cacm_agent_api_key
    if not base or not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Agent belum dikonfigurasi (set CACM_AGENT_BASE_URL + CACM_AGENT_API_KEY).",
        )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{base}/api/v1/runs", headers={"X-API-Key": key})
            r.raise_for_status()
            return {"ok": True, "agent_response": r.json()}
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Gagal trigger agent: {e}")
