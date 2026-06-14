"""Cek deterministik (tanpa LLM) atas artefak temuan — gratis & cepat.

Dipakai sebagai pelengkap LLM-judge: grounding-presence, kelengkapan unsur,
dan parse hasil QC SAIPI bila ada.
"""
from __future__ import annotations

import json
from pathlib import Path


def grounding_presence(temuan_list: list[dict]) -> dict:
    """Berapa temuan yang punya dokumen_sumber lengkap (file+halaman+kutipan)."""
    total = len(temuan_list)
    grounded = 0
    rincian = []
    for t in temuan_list:
        srcs = t.get("dokumen_sumber") or []
        ok = any(
            (s.get("file") and s.get("kutipan") and s.get("halaman") not in (None, ""))
            for s in srcs
        )
        if ok:
            grounded += 1
        rincian.append({"judul": t.get("judul_temuan"), "ber_bukti": ok, "n_sumber": len(srcs)})
    return {
        "total": total,
        "ber_bukti": grounded,
        "rasio": round(grounded / total, 3) if total else 0.0,
        "rincian": rincian,
    }


def is_audit_skill(skill: str | None) -> bool:
    """`sebab` (penyebab) hanya digali pada penugasan jenis AUDIT.
    Reviu/evaluasi/pemantauan TIDAK sampai menggali akar penyebab — `sebab` kosong itu benar."""
    return bool(skill) and skill.lower().startswith("audit")


def unsur_lengkap(temuan_list: list[dict], skill: str | None = None) -> dict:
    """Kelengkapan unsur temuan, sadar-jenis. Audit → 4 unsur (incl. sebab);
    reviu/evaluasi/pemantauan → 3 unsur (kondisi/kriteria/akibat)."""
    audit = is_audit_skill(skill)
    keys = ("kondisi", "kriteria", "sebab", "akibat") if audit else ("kondisi", "kriteria", "akibat")
    total = len(temuan_list)
    lengkap = sum(1 for t in temuan_list if all((t.get(k) or "").strip() for k in keys))
    return {
        "total": total,
        "lengkap": lengkap,
        "rasio": round(lengkap / total, 3) if total else 0.0,
        "unsur_diwajibkan": list(keys),
        "jenis": "audit" if audit else "non-audit (reviu/evaluasi/pemantauan)",
    }


def pkp_assessment(folder: Path, temuan_list: list[dict] | None = None) -> dict:
    """Jejak mutu PKP: apakah agen merekam penilaian kememadaian PKP per sasaran
    DI DALAM feedback agen (`_FEEDBACK-AGEN/feedback-*.json` field `pkp_assessment`)
    + ketertelusuran temuan (langkah_kerja_terkait).

    Sumber = feedback agen (bahan evaluasi), bukan artefak terpisah — sesuai keputusan
    user 14 Juni: kememadaian PKP cukup masuk ke feedback agen."""
    fb_dir = folder / "_FEEDBACK-AGEN"
    items: list[dict] = []
    ada = False
    if fb_dir.is_dir():
        # ambil feedback anggota_tim TERBARU (nama ber-timestamp → urut nama = urut waktu)
        files = sorted(fb_dir.glob("feedback-anggota_tim-*.json"))
        for p in reversed(files):
            try:
                d = json.loads(p.read_text())
            except Exception:
                continue
            pk = d.get("pkp_assessment") or []
            if pk:
                items = pk
                ada = True
                break
            ada = ada or (p.exists())  # feedback ada walau field kosong
    n_sasaran = len(items)
    n_kurang = sum(1 for i in items if str(i.get("kememadaian", "")).upper() != "MEMADAI")
    n_usul = sum(len(i.get("langkah_tambahan_diusulkan") or []) for i in items)
    # Ketertelusuran temuan: berapa yang menyebut langkah_kerja_terkait
    tl = temuan_list or []
    n_tertelusur = sum(1 for t in tl if str(t.get("langkah_kerja_terkait") or "").strip())
    return {
        "direkam": n_sasaran > 0,
        "sumber": "feedback-agen",
        "n_sasaran_dinilai": n_sasaran,
        "n_kurang_memadai": n_kurang,
        "n_usul_langkah_tambahan": n_usul,
        "temuan_tertelusur": n_tertelusur,
        "temuan_total": len(tl),
    }


def qc_saipi(folder: Path) -> dict | None:
    """Baca hasil QC SAIPI KKP bila ada (_KKP/kkp-qc-result.json)."""
    for name in ("kkp-qc-result.json", "qc-result.json"):
        p = folder / "_KKP" / name
        if p.exists():
            try:
                d = json.loads(p.read_text())
            except Exception:
                return {"file": str(p), "error": "gagal parse"}
            return {
                "file": str(p),
                "ok": d.get("ok") or d.get("OK"),
                "kritis": d.get("kritis") or d.get("KRITIS"),
                "status": d.get("status"),
            }
    return None
