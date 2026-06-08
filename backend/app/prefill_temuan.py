"""Pre-fill DRAFT temuan deterministik dari anomalies pipeline V6.

Konteks: pipeline V6 sudah menghasilkan `anomalies-master.json` per RO dengan
`draft_catatan: {kondisi, kriteria, akibat, rekomendasi}` untuk setiap anomali.
Sebelumnya, agen AT membaca anomalies satu per satu lalu MENGGUBAH narasi dari
nol — boros token + hasilnya kadang tidak konsisten antar penugasan.

Modul ini mengubah anomali rule-based → draft temuan yang STRUKTURNYA siap
ditulis ke `_KKP/temuan.json`. Agen AT cukup melakukan VERIFIKASI substantif:
  - tolak anomali yang ternyata false-positive (lihat PDF halaman terkait)
  - poles narasi (lengkapi, perbaiki bahasa)
  - tambah dokumen_sumber dengan kutipan/halaman yang tepat
  - tetapkan sasaran_id

Output kompatibel `schema_version v4.0.0` (sama dengan temuan.json existing).
Field `status: DRAFT` + `pre_filled: true` agar bisa dibedakan dari yang ditulis
agen langsung.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Severity dari V6 → kategori temuan. Sesuaikan dengan terminologi APIP/SAIPI.
_SEVERITY_TO_KATEGORI = {
    "KRITIS": "kritis",
    "PERINGATAN": "signifikan",
    "INFO": "catatan",
}


# Aspek V6 RKA-K/L → suggested sasaran (mapping kasar, agen AT verifikasi).
# A=Konteks, B=Identitas, C=Output, D=Dasar Hukum, E=Komponen, F=Lainnya.
_ASPEK_TO_SASARAN_HINT = {
    "A": "S-01",
    "B": "S-01",
    "C": "S-02",
    "D": "S-01",
    "E": "S-02",
    "F": "S-03",
}


def _safe_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _suggest_dokumen_sumber(anomali: dict, ro_nama: str | None) -> list[dict]:
    """Tarik petunjuk dokumen sumber dari `bukti` anomali bila ada."""
    bukti = anomali.get("bukti") or {}
    out: list[dict] = []
    # Pola umum: bukti punya `file`, `halaman`, `kutipan` atau `referensi`
    if isinstance(bukti, dict):
        f = bukti.get("file") or bukti.get("dokumen")
        if f:
            out.append({
                "file": f,
                "halaman": bukti.get("halaman") or bukti.get("hal"),
                "kutipan": (bukti.get("kutipan") or "")[:400] or None,
            })
    # Bila tidak ada, kasih placeholder dengan RO nama supaya auditor isi
    if not out and ro_nama:
        out.append({
            "file": "[isi: file PDF sumber]",
            "halaman": None,
            "kutipan": f"[isi: kutipan terkait '{ro_nama}']",
        })
    return out


def _build_judul(anomali: dict) -> str:
    """Susun judul temuan dari judul anomali V6."""
    raw = (anomali.get("judul") or "").strip()
    if not raw:
        deskripsi = (anomali.get("deskripsi") or "").strip()
        raw = deskripsi[:80] + ("…" if len(deskripsi) > 80 else "")
    # Capitalize first letter
    return raw[:1].upper() + raw[1:] if raw else "Draft Temuan (perlu judul)"


def _id_temuan(idx: int, severity: str) -> str:
    """ID temuan: T-XYZ. Severity-bias: KRITIS dapat nomor lebih kecil."""
    return f"T-{idx:03d}"


def anomali_to_temuan(
    anomali: dict,
    *,
    idx: int,
    anggota_tim_nama: str | None = None,
) -> dict | None:
    """Konversi satu anomali V6 → draft temuan v4.0.0.

    Return None bila anomali tidak punya `draft_catatan` (tidak bisa dikonversi).
    """
    draft = anomali.get("draft_catatan") or {}
    if not isinstance(draft, dict):
        return None
    kondisi = (draft.get("kondisi") or anomali.get("deskripsi") or "").strip()
    if not kondisi:
        return None

    severity = (anomali.get("severity") or "INFO").upper()
    aspek = (anomali.get("aspek") or "").upper()
    ro_nama = anomali.get("ro_nama")

    temuan = {
        "sasaran_id": _ASPEK_TO_SASARAN_HINT.get(aspek, "S-01"),
        "kondisi": kondisi,
        "kriteria": (draft.get("kriteria") or "").strip() or None,
        "akibat": (draft.get("akibat") or "").strip() or None,
        "sebab": (draft.get("sebab") or "").strip() or None,
        "dokumen_sumber": _suggest_dokumen_sumber(anomali, ro_nama),
        "judul_temuan": _build_judul(anomali),
        "anggota_tim": {"nama_lengkap": anggota_tim_nama} if anggota_tim_nama else None,
        "tanggal_input": datetime.now(timezone.utc).isoformat(),
        "status": "DRAFT",  # agen WAJIB verifikasi dulu
        "catatan_ketua_tim": None,
        "integral": None,
        "id_temuan": _id_temuan(idx, severity),
        # Metadata trace: dari mana draft ini berasal
        "pre_filled": {
            "source": "anomali_v6",
            "rule_id": anomali.get("rule_id"),
            "severity": severity,
            "aspek": aspek,
            "kategori_saran": _SEVERITY_TO_KATEGORI.get(severity, "catatan"),
            "rekomendasi_awal": (draft.get("rekomendasi") or "").strip() or None,
            "ro_id": anomali.get("ro_id"),
            "ro_nama": ro_nama,
        },
    }
    return temuan


def build_draft_temuan(
    penugasan_folder: str | Path,
    *,
    anggota_tim_nama: str | None = None,
    severity_min: str = "INFO",
) -> dict:
    """Bangun struktur `temuan.json` DRAFT dari anomalies V6.

    Args:
        penugasan_folder: folder root penugasan (yang ada `_KKP/`).
        anggota_tim_nama: nama AT untuk diisikan ke setiap draft (opsional).
        severity_min: filter — hanya anomali ≥ severity ini di-konversi.
            Urutan: KRITIS > PERINGATAN > INFO. Default INFO = semua.

    Return:
        {
            "schema_version": "v4.0.0",
            "temuan": [...draft...],
            "_meta": {
                "generated_from": "anomalies-master.json",
                "generated_at": "...",
                "anomali_total": N,
                "anomali_dikonversi": M,
                "anomali_skip": [{"rule_id": "...", "reason": "..."}, ...]
            }
        }
    """
    folder = Path(penugasan_folder)
    anomali_path = folder / "_KKP" / "anomalies-master.json"
    data = _safe_json(anomali_path)
    if not isinstance(data, dict):
        return {
            "schema_version": "v4.0.0",
            "temuan": [],
            "_meta": {
                "error": f"anomalies-master.json tidak ditemukan/parsable di {anomali_path}",
            },
        }

    anomalies = data.get("anomalies") or []
    if not isinstance(anomalies, list):
        anomalies = []

    severity_rank = {"INFO": 0, "PERINGATAN": 1, "KRITIS": 2}
    min_rank = severity_rank.get(severity_min.upper(), 0)

    draft_list: list[dict] = []
    skipped: list[dict] = []
    idx = 1
    for a in anomalies:
        sev = (a.get("severity") or "INFO").upper()
        if severity_rank.get(sev, 0) < min_rank:
            skipped.append({"rule_id": a.get("rule_id"), "reason": f"severity {sev} < {severity_min}"})
            continue
        t = anomali_to_temuan(a, idx=idx, anggota_tim_nama=anggota_tim_nama)
        if t is None:
            skipped.append({"rule_id": a.get("rule_id"), "reason": "tidak ada draft_catatan/kondisi"})
            continue
        draft_list.append(t)
        idx += 1

    return {
        "schema_version": "v4.0.0",
        "temuan": draft_list,
        "_meta": {
            "generated_from": "anomalies-master.json",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "anomali_total": len(anomalies),
            "anomali_dikonversi": len(draft_list),
            "anomali_skip": skipped,
            "severity_min": severity_min.upper(),
        },
    }


def write_draft_temuan(
    penugasan_folder: str | Path,
    *,
    overwrite: bool = False,
    output_name: str = "temuan-draft.json",
    **kwargs,
) -> tuple[Path, dict]:
    """Tulis draft temuan ke `_KKP/<output_name>`.

    Sengaja TIDAK menimpa `temuan.json` — agen AT yang memutuskan kapan promote
    draft → final. Return (path, struktur_yg_ditulis).

    Bila file sudah ada dan `overwrite=False` → tidak nulis ulang.
    """
    folder = Path(penugasan_folder)
    kkp = folder / "_KKP"
    kkp.mkdir(parents=True, exist_ok=True)
    path = kkp / output_name

    if path.exists() and not overwrite:
        existing = _safe_json(path) or {}
        return path, existing

    data = build_draft_temuan(folder, **kwargs)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, data
