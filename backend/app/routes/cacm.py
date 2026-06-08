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
from app.cacm_evaluator import (
    EvaluasiHasil,
    evaluate_all_for_dimensi,
    get_kriteria,
    list_kriteria,
    load_registry,
)
from app.config import get_settings
from app.database import get_db
from app.models import (
    CacmFinding,
    CacmObservasi,
    CacmRun,
    EwsFinding,
    Penugasan,
    PenugasanStatus,
    Role,
    Skill,
    User,
)
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
    # Wire-up Fase 1: paralel-eval v7-native dgn kriteria YAML.
    # Best-effort — kegagalan tidak menggagalkan ingest (EwsFinding tetap dipakai
    # UI legacy). Hasil tersimpan di CacmObservasi + CacmFinding utk validasi.
    try:
        await _run_v7_native_eval(db, run, findings)
    except Exception as exc:  # noqa: BLE001
        log.warning("v7-native eval gagal utk run %s: %s", run.run_id, exc)
    await _maybe_auto_promote(db, run, source)
    # Auto-promote v7-native (opt-in, env CACM_V7_AUTO_PROMOTE).
    # Best-effort — gagal di sini tidak menggagalkan ingest.
    try:
        await _maybe_auto_promote_v7(db, run, source)
    except Exception as exc:  # noqa: BLE001
        log.warning("v7-native auto-promote gagal utk run %s: %s", run.run_id, exc)
    return run


# ============================================================
# V7-native evaluator wire-up (Fase 1 CACM)
# ============================================================

def _periode_label_from_run(run: CacmRun) -> str:
    """Label periode singkat utk CacmObservasi/Finding (cth: '2026-05' atau '2026-Q2')."""
    src = run.tanggal_evaluasi or run.periode_crawl or ""
    if isinstance(src, str) and len(src) >= 7:
        return src[:7]  # YYYY-MM
    return datetime.utcnow().strftime("%Y-%m")


async def _run_v7_native_eval(db: AsyncSession, run: CacmRun, findings: list[dict]) -> None:
    """Jalankan evaluator v7-native: dump paket_detail ke CacmObservasi,
    group by satker, eval semua kriteria PENGADAAN_RENCANA, tulis CacmFinding.

    Tidak mengubah EwsFinding existing. Idempoten per run: dipanggil sekali per
    ingest. Re-evaluate manual lewat POST /cacm/runs/{run_id}/re-evaluate.
    """
    load_registry()  # cache kriteria
    periode = _periode_label_from_run(run)

    # Dump observasi: 1 row per paket di paket_detail, group by satker
    obs_by_satker: dict[tuple[str | None, str], list[CacmObservasi]] = {}
    for f in findings:
        satker_nama = str(f.get("satker", "")).strip() or "(tanpa satker)"
        satker_kode = (str(f.get("satker_kode")) if f.get("satker_kode") else None) or None
        pakets = f.get("paket_detail") if isinstance(f.get("paket_detail"), list) else []
        for p in pakets:
            if not isinstance(p, dict):
                continue
            o = CacmObservasi(
                sumber="sirup",
                dimensi="PENGADAAN_RENCANA",
                satker_kode=satker_kode,
                satker_nama=satker_nama,
                periode_label=periode,
                data=p,
                raw_source_id=str(p.get("kode_paket") or p.get("nama_paket") or "")[:120] or None,
                cacm_run_id=run.id,
            )
            db.add(o)
            obs_by_satker.setdefault((satker_kode, satker_nama), []).append(o)

    if not obs_by_satker:
        return

    await db.flush()  # supaya CacmObservasi punya ID utk bukti_observasi_ids

    # Untuk tiap satker, eval semua kriteria PENGADAAN_RENCANA
    for (satker_kode, satker_nama), obs_list in obs_by_satker.items():
        rows = [{"data": o.data, "_id": o.id} for o in obs_list]
        bukti_ids = [o.id for o in obs_list]
        hasils: list[EvaluasiHasil] = evaluate_all_for_dimensi("PENGADAAN_RENCANA", rows)
        for h in hasils:
            db.add(CacmFinding(
                kriteria_id=h.kriteria_id,
                kriteria_revisi=h.kriteria_revisi,
                status=h.status,
                metric_value=(float(h.value) if isinstance(h.value, (int, float)) and h.value == h.value else None),
                metric_satuan=h.satuan,
                metric_display=h.value_display,
                satker_kode=satker_kode,
                satker_nama=satker_nama,
                periode_label=periode,
                dimensi="PENGADAAN_RENCANA",
                bukti_observasi_ids=bukti_ids[:50],
                evidence=h.evidence,
                narasi=h.narasi,
                tindak_lanjut="BARU",
                cacm_run_id=run.id,
            ))

    await db.commit()


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


async def _create_usulan_from_finding(
    db: AsyncSession,
    f: "EwsFinding | CacmFinding",
) -> Penugasan:
    """Buat Penugasan USULAN_CACM prefilled dari 1 finding (EWS legacy ATAU
    v7-native CacmFinding). TIDAK commit & TIDAK set field finding — caller
    yang mengatur f.tindak_lanjut/penugasan_id + commit.

    Dispatch by type — keduanya menulis section "Sinyal CACM / EWS SIRUP"
    ke context.md dengan field yang berbeda di belakang layar.
    """
    if isinstance(f, CacmFinding):
        return await _create_usulan_from_cacm_finding(db, f)
    return await _create_usulan_from_ews_finding(db, f)


async def _create_usulan_from_ews_finding(db: AsyncSession, f: EwsFinding) -> Penugasan:
    """Original implementation (EwsFinding legacy). Field langsung tersedia."""
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


async def _create_usulan_from_cacm_finding(db: AsyncSession, f: CacmFinding) -> Penugasan:
    """V7-native variant — load paket dari CacmObservasi via bukti_observasi_ids,
    regulasi dari YAML kriteria via load_registry. Output context.md "Sinyal CACM"
    format yang sama dengan EWS legacy supaya agen AT/KT tidak perlu cek beda.
    """
    # Judul singkat dari kriteria_id + status
    kriteria_id = f.kriteria_id
    judul_singkat = f"{kriteria_id}: {(f.narasi or 'finding v7-native').split('.')[0]}"[:120]
    obyek = f"Reviu Pengadaan {f.satker_nama} — {kriteria_id}: {judul_singkat}"[:400]

    kode_pen = gen_kode_penugasan("reviu-pengadaan")
    folder = penugasan_folder(kode_pen)
    payload = PenugasanCreate(obyek=obyek, skill=Skill.REVIU_PENGADAAN, nomor_st=None, tanggal_st=None)
    _scaffold_penugasan_files(folder=folder, kode=kode_pen, payload=payload, ketua_tim_name=None)

    # Load paket dari CacmObservasi via bukti_observasi_ids
    paket_lines = ""
    n_paket = 0
    total_pagu = 0
    if f.bukti_observasi_ids:
        obs_rows = (
            await db.execute(
                select(CacmObservasi).where(CacmObservasi.id.in_(f.bukti_observasi_ids))
            )
        ).scalars().all()
        n_paket = len(obs_rows)
        paket_items: list[str] = []
        for o in obs_rows[:15]:
            d = o.data or {}
            nama = d.get("nama") or d.get("nama_paket", "")
            pagu = _to_int(d.get("pagu"))
            total_pagu += pagu or 0
            paket_items.append(
                f"  - {nama} — Rp {pagu:,} ({d.get('metode','')}, {d.get('jenis','')})"
            )
        paket_lines = "\n".join(paket_items)
        # Hitung total pagu seluruh observasi (bukan hanya 15)
        for o in obs_rows:
            d = o.data or {}
            total_pagu += _to_int(d.get("pagu")) or 0

    # Load regulasi & threshold display dari YAML kriteria
    regulasi_str = "-"
    threshold_str = "-"
    try:
        from app.cacm_evaluator import load_registry
        reg = load_registry()
        k = reg.get(kriteria_id)
        if k:
            regulasi_str = k.regulasi or "-"
            # Threshold display: ambil dari first MERAH (paling kritis)
            thr_lines: list[str] = []
            for thr in (k.thresholds or []):
                thr_lines.append(f"{thr.status}: {thr.condition}")
            threshold_str = " | ".join(thr_lines) or "-"
    except Exception:  # noqa: BLE001 — graceful
        pass

    cacm_section = (
        f"\n\n## Sinyal CACM / v7-native (sumber usulan penugasan)\n\n"
        f"- Kriteria v7: {kriteria_id} (rev {f.kriteria_revisi}) — status: {f.status}\n"
        f"- Satker: {f.satker_nama}\n"
        f"- Metrik: {f.metric_display or '-'}\n"
        f"- Paket terdampak: {n_paket}"
        + (f" | Total pagu: Rp {total_pagu:,}\n" if total_pagu else "\n")
        + f"- Threshold YAML: {threshold_str}\n"
        + f"- Regulasi: {regulasi_str}\n"
        + f"- Dimensi: {f.dimensi}\n\n"
        + f"Narasi evaluator:\n{f.narasi or '-'}\n"
        + (f"\nPaket terdampak (top 15):\n{paket_lines}\n" if paket_lines else "")
        + "\n> Sumber: CACM v7-native (kriteria YAML deterministik). Bukti: "
        + f"{len(f.bukti_observasi_ids or [])} observasi.\n"
    )
    ctx_path = folder / "context.md"
    try:
        existing = ctx_path.read_text(encoding="utf-8") if ctx_path.exists() else ""
        ctx_path.write_text(existing + cacm_section, encoding="utf-8")
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
    satker+kode EWS yang sama — anti-spam saat sinyal berulang tiap run.

    Cek dilakukan via DUA jalur (EwsFinding dan CacmFinding), supaya
    auto-promote EWS legacy tidak duplicate usulan yang sudah dibuat oleh
    auto-promote v7-native (atau sebaliknya). Mapping kode ↔ kriteria_id
    via `app/cacm_mapping.py`.
    """
    if not satker_kode:
        return False

    # Jalur 1: cek di EwsFinding (kode EWS langsung)
    pen_ids_ews = (
        await db.execute(
            select(EwsFinding.penugasan_id).where(
                EwsFinding.satker_kode == satker_kode,
                EwsFinding.kode == kode,
                EwsFinding.tindak_lanjut == "DIPROMOSIKAN",
                EwsFinding.penugasan_id.is_not(None),
            )
        )
    ).scalars().all()

    # Jalur 2: cek di CacmFinding (cari kriteria_id v7 yg setara dgn kode EWS)
    from app.cacm_mapping import v7_kriteria_for_ews, ews_kode_for_v7
    pen_ids_v7: list[int] = []
    # `kode` bisa berupa EWS-XX atau PBJ-... (kriteria_id v7). Normalisasi keduanya.
    v7_id = v7_kriteria_for_ews(kode) or kode  # kalau kode adalah EWS, map; kalau sudah v7, pakai langsung
    if v7_id:
        pen_ids_v7 = (
            await db.execute(
                select(CacmFinding.penugasan_id).where(
                    CacmFinding.satker_kode == satker_kode,
                    CacmFinding.kriteria_id == v7_id,
                    CacmFinding.tindak_lanjut == "DIPROMOSIKAN",
                    CacmFinding.penugasan_id.is_not(None),
                )
            )
        ).scalars().all()

    pen_ids = list(set(pen_ids_ews) | set(pen_ids_v7))
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


async def _maybe_auto_promote_v7(db: AsyncSession, run: CacmRun, source: str) -> int:
    """Auto-promote OPT-IN untuk CacmFinding v7-native. Mirror logic
    `_maybe_auto_promote` (EWS legacy) tapi pakai env terpisah:

        CACM_V7_AUTO_PROMOTE=off|merah|merah_kuning  (default: off)

    Tidak menggantikan auto-promote EWS legacy. Anti-duplikat via
    `_open_usulan_exists` yang sudah extended ke dua jalur (Sec #7b).
    """
    mode = (getattr(settings, "cacm_v7_auto_promote", None) or "off").strip().lower()
    if source not in ("webhook", "pull") or mode not in ("merah", "merah_kuning"):
        return 0
    statuses = {"MERAH"} if mode == "merah" else {"MERAH", "KUNING"}
    findings = (
        await db.execute(
            select(CacmFinding).where(
                CacmFinding.cacm_run_id == run.id,
                CacmFinding.tindak_lanjut == "BARU",
            )
        )
    ).scalars().all()
    count = 0
    for f in findings:
        if (f.status or "").upper() not in statuses:
            continue
        # Cek anti-duplikat (lewat kriteria_id v7 — dedupe extend handle dua arah)
        if await _open_usulan_exists(db, f.satker_kode, f.kriteria_id):
            continue
        p = await _create_usulan_from_finding(db, f)
        f.tindak_lanjut = "DIPROMOSIKAN"
        f.penugasan_id = p.id
        count += 1
    if count:
        await db.commit()
        log.info("CACM v7-native auto-promote: %d usulan dibuat dari run %s (%s)", count, run.run_id, source)
    return count


@router.post("/cacm-findings/{finding_id}/promote", status_code=status.HTTP_201_CREATED)
async def promote_cacm_finding(
    finding_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Jadikan CacmFinding v7-native sebagai Penugasan baru (USULAN_CACM).
    Paralel dengan POST /cacm/findings/{id}/promote (EWS legacy). PT only.
    """
    user, role = current
    _require_pt(role)

    f = (await db.execute(select(CacmFinding).where(CacmFinding.id == finding_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CacmFinding tidak ditemukan")
    if f.tindak_lanjut == "DIPROMOSIKAN" and f.penugasan_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Finding sudah dipromosikan jadi penugasan #{f.penugasan_id}.",
        )
    if (f.status or "").upper() not in _PROMOTABLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Status {f.status} tidak dapat dipromosikan (hanya MERAH/KUNING).",
        )
    # Anti-duplikat (cek juga jalur EWS legacy untuk satker+kriteria yg sama)
    if await _open_usulan_exists(db, f.satker_kode, f.kriteria_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Sudah ada usulan terbuka untuk satker={f.satker_kode} kriteria={f.kriteria_id} "
            f"(mungkin dari jalur EWS legacy).",
        )

    p = await _create_usulan_from_finding(db, f)
    f.tindak_lanjut = "DIPROMOSIKAN"
    f.penugasan_id = p.id
    await db.commit()
    return {
        "ok": True,
        "penugasan_id": p.id,
        "penugasan_kode": p.kode,
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
    }


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


# ============================================================
# Kriteria Library + Re-evaluate (Fase 1 CACM)
# ============================================================


def _kriteria_to_dict(model) -> dict:
    """Serialisasi pydantic KriteriaModel utk respon HTTP."""
    return {
        "id": model.id,
        "revisi": model.revisi,
        "nama": model.nama,
        "tipe": model.tipe,
        "dimensi": model.dimensi,
        "sumber_data": model.sumber_data,
        "satker_terapkan": model.satker_terapkan,
        "regulasi": model.regulasi,
        "metric": {
            "expression": model.metric.expression,
            "satuan": model.metric.satuan,
            "format_display": model.metric.format_display,
        },
        "thresholds": [
            {"status": t.status, "condition": t.condition, "catatan": t.catatan}
            for t in model.thresholds
        ],
        "evidence_fields": model.evidence_fields,
        "promote": (
            {
                "skill": model.promote.skill,
                "pattern_ids_hint": model.promote.pattern_ids_hint,
                "prefilled_obyek_tpl": model.promote.prefilled_obyek_tpl,
                "prefilled_dasar_permintaan": model.promote.prefilled_dasar_permintaan,
            }
            if model.promote
            else None
        ),
        "catatan_revisi": model.catatan_revisi,
    }


@router.get("/kriteria/library")
async def kriteria_library(
    dimensi: str | None = None,
    current: tuple[User, Role] = Depends(get_current_user),
) -> dict:
    """List kriteria CACM v7-native dari `knowledge/cacm/kriteria/*.yaml`.

    Semua role boleh baca (mirror Pattern Library di /knowledge).
    """
    items = list_kriteria(dimensi=dimensi or None)
    dimensions = sorted({m.dimensi for m in list_kriteria()})
    return {
        "total": len(items),
        "dimensi_available": dimensions,
        "items": [_kriteria_to_dict(m) for m in items],
    }


@router.get("/kriteria/{kriteria_id}")
async def kriteria_detail(
    kriteria_id: str,
    current: tuple[User, Role] = Depends(get_current_user),
) -> dict:
    """Detail 1 kriteria — full schema utk preview & cross-check."""
    m = get_kriteria(kriteria_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Kriteria '{kriteria_id}' tidak ada di registry.")
    return _kriteria_to_dict(m)


@router.get("/runs/{run_id}/findings/v7-native")
async def runs_v7_native_findings(
    run_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List CacmFinding v7-native utk satu run (paralel dgn /runs/{id} legacy)."""
    rows = (
        await db.execute(
            select(CacmFinding)
            .where(CacmFinding.cacm_run_id == run_id)
            .order_by(CacmFinding.satker_nama, CacmFinding.kriteria_id)
        )
    ).scalars().all()
    return {
        "total": len(rows),
        "findings": [
            {
                "id": r.id,
                "kriteria_id": r.kriteria_id,
                "kriteria_revisi": r.kriteria_revisi,
                "status": r.status,
                "metric_value": r.metric_value,
                "metric_display": r.metric_display,
                "metric_satuan": r.metric_satuan,
                "satker_kode": r.satker_kode,
                "satker_nama": r.satker_nama,
                "periode_label": r.periode_label,
                "dimensi": r.dimensi,
                "narasi": r.narasi,
                "evidence": r.evidence or {},
                "bukti_observasi_ids": r.bukti_observasi_ids or [],
                "tindak_lanjut": r.tindak_lanjut,
                "penugasan_id": r.penugasan_id,
                "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
            }
            for r in rows
        ],
    }


@router.get("/runs/{run_id}/findings/diff")
async def runs_findings_diff(
    run_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Diff EwsFinding (legacy) vs CacmFinding (v7-native) untuk satu run.

    Pair berdasarkan (satker_nama, kriteria) — mapping kode EWS ↔ kriteria_id
    di `app/cacm_mapping.py`. Output:
      - `matched`: pair (ews_status, v7_status) + flag `is_match`.
      - `v7_only`: CacmFinding tanpa pasangan EWS (kriteria_id baru/tupoksi/unitcost).
      - `ews_only`: EwsFinding tanpa pasangan v7 (mis. evaluator gagal/YAML hilang).
      - Ringkasan counter.

    Tujuan: validasi cut-over sebelum auto-promote v7-native dinyalakan.
    """
    from app.cacm_mapping import (
        EWS_TO_V7, V7_TO_EWS, V7_ONLY, ews_kode_for_v7, v7_kriteria_for_ews,
        is_v7_only,
    )

    ews_rows = (
        await db.execute(
            select(EwsFinding)
            .where(EwsFinding.cacm_run_id == run_id)
            .order_by(EwsFinding.satker, EwsFinding.kode)
        )
    ).scalars().all()
    v7_rows = (
        await db.execute(
            select(CacmFinding)
            .where(CacmFinding.cacm_run_id == run_id)
            .order_by(CacmFinding.satker_nama, CacmFinding.kriteria_id)
        )
    ).scalars().all()

    # Index keduanya by (satker_nama_norm, kode_norm) — pakai EWS kode sbg
    # kunci kanonik (v7 kriteria_id di-map balik via V7_TO_EWS).
    def _norm_satker(s: str | None) -> str:
        return (s or "").strip().lower()

    ews_idx: dict[tuple[str, str], EwsFinding] = {}
    for e in ews_rows:
        key = (_norm_satker(e.satker), e.kode)
        ews_idx[key] = e

    v7_idx: dict[tuple[str, str], CacmFinding] = {}
    v7_only_rows: list[CacmFinding] = []
    for c in v7_rows:
        kode_ews = V7_TO_EWS.get(c.kriteria_id)
        if kode_ews is None:
            v7_only_rows.append(c)
            continue
        key = (_norm_satker(c.satker_nama), kode_ews)
        v7_idx[key] = c

    matched: list[dict] = []
    matched_keys: set = set()
    for key, e in ews_idx.items():
        c = v7_idx.get(key)
        if c is None:
            continue  # ews_only — diisi di loop berikut
        matched_keys.add(key)
        is_match = (e.status or "").upper() == (c.status or "").upper()
        matched.append({
            "satker_nama": e.satker,
            "satker_kode": e.satker_kode,
            "ews_kode": e.kode,
            "v7_kriteria_id": c.kriteria_id,
            "ews_status": e.status,
            "v7_status": c.status,
            "is_match": is_match,
            "ews_finding_id": e.id,
            "v7_finding_id": c.id,
            "ews_nilai": e.nilai_aktual,
            "v7_metric_display": c.metric_display,
            "ews_judul": e.judul or e.ringkasan,
            "v7_narasi": (c.narasi or "")[:200],
        })

    ews_only: list[dict] = []
    for key, e in ews_idx.items():
        if key in matched_keys:
            continue
        # Pasangan v7 tidak ditemukan untuk EWS ini
        ews_only.append({
            "satker_nama": e.satker,
            "satker_kode": e.satker_kode,
            "ews_kode": e.kode,
            "expected_v7_kriteria_id": EWS_TO_V7.get(e.kode),
            "ews_status": e.status,
            "ews_finding_id": e.id,
            "ews_nilai": e.nilai_aktual,
            "ews_judul": e.judul or e.ringkasan,
            "reason": "v7-native belum dievaluasi (mungkin YAML kriteria tidak ada / evaluator gagal)"
                if EWS_TO_V7.get(e.kode) is not None
                else "EWS legacy tanpa pasangan v7 (kode EWS tidak ada di EWS_TO_V7 mapping)",
        })

    v7_only: list[dict] = [
        {
            "satker_nama": c.satker_nama,
            "satker_kode": c.satker_kode,
            "v7_kriteria_id": c.kriteria_id,
            "v7_status": c.status,
            "v7_finding_id": c.id,
            "v7_metric_display": c.metric_display,
            "v7_narasi": (c.narasi or "")[:200],
            "reason": "Kriteria v7 baru tanpa pasangan EWS legacy (kelas semantic/benchmark)"
                if c.kriteria_id in V7_ONLY
                else "Kriteria v7 tanpa pasangan di EWS_TO_V7 mapping (perlu update mapping?)",
        }
        for c in v7_only_rows
    ]

    n_match = sum(1 for m in matched if m["is_match"])
    n_mismatch = len(matched) - n_match

    return {
        "run_id": run_id,
        "summary": {
            "n_ews_total": len(ews_rows),
            "n_v7_total": len(v7_rows),
            "n_matched_pairs": len(matched),
            "n_match_status": n_match,
            "n_mismatch": n_mismatch,
            "n_v7_only": len(v7_only),
            "n_ews_only": len(ews_only),
        },
        "matched": matched,
        "v7_only": v7_only,
        "ews_only": ews_only,
    }


@router.post("/runs/{run_id}/re-evaluate")
async def runs_re_evaluate(
    run_id: int,
    current: tuple[User, Role] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-evaluate v7-native utk satu run — PT/PM only.

    Hapus CacmObservasi + CacmFinding lama untuk run ini, lalu ulangi dump +
    eval pakai kriteria YAML terbaru. Useful saat auditor revisi threshold
    (revisi YAML) dan ingin melihat dampak ke run historis.
    """
    user, role = current
    _require_pt(role)
    load_registry(force_reload=True)  # reload supaya pickup revisi YAML

    run = (await db.execute(select(CacmRun).where(CacmRun.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run tidak ditemukan")

    # Hapus CacmObservasi + Finding lama
    old_obs = (
        await db.execute(select(CacmObservasi).where(CacmObservasi.cacm_run_id == run_id))
    ).scalars().all()
    old_fnd = (
        await db.execute(select(CacmFinding).where(CacmFinding.cacm_run_id == run_id))
    ).scalars().all()
    for o in old_obs:
        await db.delete(o)
    for f in old_fnd:
        await db.delete(f)
    await db.flush()

    # Reconstruct findings list dari EwsFinding (paket_detail) — supaya re-eval
    # pakai data raw yang sama dgn ingest awal.
    legacy = (
        await db.execute(select(EwsFinding).where(EwsFinding.cacm_run_id == run_id))
    ).scalars().all()
    findings_payload = [
        {
            "satker": f.satker,
            "satker_kode": f.satker_kode,
            "paket_detail": f.paket_detail or [],
        }
        for f in legacy
    ]
    if not findings_payload:
        await db.commit()
        return {"ok": True, "run_id": run_id, "rebuilt": 0, "note": "Tidak ada EwsFinding utk run ini."}

    await _run_v7_native_eval(db, run, findings_payload)

    n_new = len(
        (await db.execute(select(CacmFinding).where(CacmFinding.cacm_run_id == run_id))).scalars().all()
    )
    return {
        "ok": True,
        "run_id": run_id,
        "removed_observasi": len(old_obs),
        "removed_findings_old": len(old_fnd),
        "new_findings": n_new,
    }
