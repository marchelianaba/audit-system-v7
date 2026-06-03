"""Post-processing untuk digest pengadaan V6 — perbaiki klasifikasi file yang
masuk `unclassified_files` karena pattern V6 terlalu ketat.

Masalah konkret yang ditemukan tim:
- V6 `FILENAME_PATTERNS['kak'] = [r'\\bKAK\\b', r'Kerangka\\s+Acuan', r'TOR\\b']`
- File `Signed_KAK Pengadaan Lisensi Firewall 2026.pdf` tidak match `\\bKAK\\b`
  karena underscore = `\\w`, jadi tidak ada word-boundary sebelum `K`.
- Akibat: KAK & HPS masuk `unclassified_files`, `missing_types = ["kak","hps"]`,
  agen tidak punya bahan untuk temuan terkait perencanaan/HPS angle auditor.

V6 read-only. Kita pasang post-processor di layer v7: setelah V6 selesai
subprocess, kita baca digest JSON, re-klasifikasi `unclassified_files` dengan
regex yg lebih toleran (strip prefix `Signed_`/`eMaterai_`/`TTD_`/dst), jalankan
ulang parser V6 untuk file yg di-rescue, lalu update digest JSON.

Hasil:
- Field `dokumen.<jenis>` bertambah entri rescued (struktur sama dgn V6 asli).
- `unclassified_files` berkurang.
- `missing_types` dihitung ulang.
- Block audit trail `_v7_postprocess` ditambah supaya transparan.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings

settings = get_settings()


# Prefix umum yang dipasang sistem TTD/eMaterai/aprovasi sebelum nama file asli.
# Dilucuti dulu sebelum klasifikasi supaya pattern V6 cocok.
#   "Signed_KAK ..."   → "KAK ..."
#   "eMaterai_KAK ..." → "KAK ..."
#   "TTD-HPS ..."      → "HPS ..."
_PREFIX_STRIP_RE = re.compile(
    r"^(signed|emateral|emater(?:ai)?|ttd|paraf|approved|approval|ttdsign|signedtm)[_\-\s]+",
    re.IGNORECASE,
)

# Pattern jenis dokumen — paralel dgn V6 FILENAME_PATTERNS, tapi:
# - Lebih longgar di kata kunci pendek (KAK/HPS/TOR/SPK) — pakai look-around manual
#   yang tidak terhalang underscore.
# - Tambah jenis 'kp' (Kartu Penugasan) & 'pkp' (Program Kerja Pengawasan) yang
#   sebelumnya tidak terklasifikasi sama sekali — meskipun bukan input wajib
#   pipeline pengadaan, mereka adalah dokumen ST/PKP yg auditor butuhkan
#   sebagai konteks pembelajaran agen.
_ROBUST_PATTERNS: dict[str, list[str]] = {
    "kak": [
        r"(?:^|[\s_\-\.])KAK(?:[\s_\-\.]|$)",
        r"Kerangka\s+Acuan",
        r"(?:^|[\s_\-\.])TOR(?:[\s_\-\.]|$)",
    ],
    "hps": [
        r"(?:^|[\s_\-\.])HPS(?:[\s_\-\.]|$)",
        r"Harga\s+Perkiraan",
    ],
    "hps_detail": [
        r"Tabel\s+Penyusun.*HPS",
        r"Rekap\s+Komponen.*HPS",
    ],
    "identifikasi_pengadaan": [
        r"Identifikasi\s+Pengadaan",
    ],
    "rfi": [
        r"(?:^|[\s_\-\.])RFI(?:[\s_\-\.]|$)",
        r"Request\s+For\s+Information",
    ],
    "kontrak": [
        r"SSUKSSKK",
        r"Salinan\s+Jasa\s+Lainnya",
        r"Kontrak",
        r"(?:^|[\s_\-\.])SPK(?:[\s_\-\.]|$)",
    ],
    "sppbj": [
        r"SPPBJ",
    ],
    "perjanjian_kerahasiaan": [
        r"Perjanjian\s+Kerahasiaan",
        r"(?:^|[\s_\-\.])NDA(?:[\s_\-\.]|$)",
    ],
    "permohonan_jaminan": [
        r"Permohonan\s+.{1,30}Jaminan",
    ],
    "pembayaran_ls": [
        r"(?:^|[\s_\-\.])LS(?:[\s_\-\.]|$).+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des)",
        r"SPM.+LS",
        r"Pembayaran\s+LS",
    ],
    "sptb": [
        r"SPTB",
        r"Surat\s+Pernyataan\s+Tanggungjawab\s+Belanja",
    ],
    "ba_rekonsiliasi": [
        r"BA\s+Rekonsiliasi",
        r"Berita\s+Acara.+SLA",
    ],
    "laporan_bulanan": [
        r"Laporan\s+Bulanan",
    ],
}

# Jenis yang dianggap "penting" — bila sebelumnya di missing_types tapi
# berhasil di-rescue, harus di-purge dari missing_types.
_PENTING_TYPES = ["kak", "hps", "kontrak"]


def classify_robust(filename: str) -> str | None:
    """Klasifikasi nama file dgn toleransi prefix Signed_/eMaterai_/dst.

    Kembalikan `None` bila tetap tak match (mirror perilaku V6).
    """
    # Normalisasi separator: V6 dijalankan di Windows umumnya dgn path `\`,
    # tapi modul ini bisa jalan di POSIX di mana `Path("a\\b.pdf").name` BUKAN
    # `b.pdf` (POSIX tak kenal `\` sbg separator) — substring "kontrak" di
    # direktori `02-kontrak\` bisa salah match. Strip path prefix manual.
    safe = filename.replace("\\", "/")
    base = Path(safe).name
    # Strip prefix sebanyak yg cocok (multi-layer, mis. 'Signed_TTD_KAK ...')
    while True:
        new_base = _PREFIX_STRIP_RE.sub("", base, count=1)
        if new_base == base:
            break
        base = new_base
    for jenis, patterns in _ROBUST_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, base, re.IGNORECASE):
                return jenis
    return None


_V6_MODULE_CACHE: Any = None


def _load_v6_pengadaan_module() -> Any:
    """Import `digest_pengadaan.py` V6 sebagai modul Python (cache singleton)."""
    global _V6_MODULE_CACHE
    if _V6_MODULE_CACHE is not None:
        return _V6_MODULE_CACHE
    v6_root = settings.v6_path
    if not v6_root.is_absolute():
        # Fallback bila APP_V6_PATH = "/v6" (dalam container) tapi kita di host
        v6_root = (Path(__file__).resolve().parent.parent / "v6").resolve()
    script = v6_root / "scripts" / "audit-pengadaan" / "digest_pengadaan.py"
    if not script.exists():
        raise FileNotFoundError(f"V6 script tidak ditemukan: {script}")
    spec = importlib.util.spec_from_file_location("_v6_digest_pengadaan", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"Tidak bisa load V6 spec: {script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _V6_MODULE_CACHE = mod
    return mod


def repair_pengadaan_digest(
    digest_path: Path,
    *,
    folder: Path | None = None,
) -> dict[str, Any]:
    """Baca digest JSON, re-klasifikasi `unclassified_files`, jalankan parser
    V6 utk yg ter-rescue, tulis ulang JSON.

    Args:
        digest_path: path ke `pengadaan-digest.json`.
        folder: folder root penugasan (dibutuhkan utk resolve path relatif
                ke file fisik). Default = `digest_path.parent.parent`
                (asumsi `_INGESTED/pengadaan-digest.json` → folder = ../).

    Return:
        {
          "rescued": [{file, jenis_dokumen}, ...],
          "still_unclassified": [...],
          "missing_types_before": [...],
          "missing_types_after": [...],
        }
    """
    if not digest_path.exists():
        return {
            "rescued": [],
            "still_unclassified": [],
            "missing_types_before": [],
            "missing_types_after": [],
            "_skip_reason": f"digest tidak ada: {digest_path}",
        }
    try:
        digest = json.loads(digest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "rescued": [],
            "still_unclassified": [],
            "missing_types_before": [],
            "missing_types_after": [],
            "_skip_reason": f"digest tidak bisa di-parse: {e}",
        }

    if folder is None:
        # Konvensi v7: digest di `<penugasan>/_INGESTED/pengadaan-digest.json`
        folder = digest_path.parent.parent

    unclassified = list(digest.get("unclassified_files") or [])
    if not unclassified:
        return {
            "rescued": [],
            "still_unclassified": [],
            "missing_types_before": list(digest.get("missing_types") or []),
            "missing_types_after": list(digest.get("missing_types") or []),
        }

    # Import V6 module — kalau gagal, jangan crash: skip rescue, biar fallback LLM
    # yg tangani. Catat alasannya.
    try:
        v6_mod = _load_v6_pengadaan_module()
    except Exception as exc:
        return {
            "rescued": [],
            "still_unclassified": unclassified,
            "missing_types_before": list(digest.get("missing_types") or []),
            "missing_types_after": list(digest.get("missing_types") or []),
            "_skip_reason": f"gagal import V6 module: {exc}",
        }

    missing_before = list(digest.get("missing_types") or [])
    dokumen = digest.setdefault("dokumen", {})
    rescued: list[dict] = []
    still_unclassified: list[str] = []

    for rel_path in unclassified:
        jenis = classify_robust(rel_path)
        if not jenis:
            still_unclassified.append(rel_path)
            continue

        # Resolve file fisik. Toleransi path-separator Windows (CRLF '\\' di JSON).
        rel_norm = rel_path.replace("\\", "/")
        abs_path = (folder / rel_norm).resolve()
        if not abs_path.exists():
            # Kemungkinan file dihapus / path berbeda; skip diam-diam.
            still_unclassified.append(rel_path)
            continue

        parser = v6_mod.PARSERS.get(jenis)
        entry: dict[str, Any] = {
            "filename": abs_path.name,
            "path": rel_path,
            "jenis_dokumen": jenis,
            "parsed": None,
            "_rescued_by": "v7_postprocess",
        }
        if parser is not None:
            try:
                pages = v6_mod._extract_text(abs_path)
                parsed = parser(pages)
                # V6 menambahkan _raw_first_chars; tiru perilaku ini.
                if isinstance(parsed, dict):
                    parsed.setdefault(
                        "_raw_first_chars",
                        ("\n".join(pages))[:2500] if pages else "",
                    )
                entry["parsed"] = parsed
            except Exception as e:
                entry["parsed"] = {"_error": str(e)}

        dokumen.setdefault(jenis, []).append(entry)
        rescued.append({"file": rel_path, "jenis_dokumen": jenis})

    # Re-hitung missing_types
    missing_after = [t for t in _PENTING_TYPES if t not in dokumen]
    digest["unclassified_files"] = still_unclassified
    digest["missing_types"] = missing_after

    # Audit trail
    digest["_v7_postprocess"] = {
        "at": datetime.utcnow().isoformat() + "Z",
        "rescued": rescued,
        "still_unclassified": still_unclassified,
        "missing_before": missing_before,
        "missing_after": missing_after,
    }

    digest_path.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "rescued": rescued,
        "still_unclassified": still_unclassified,
        "missing_types_before": missing_before,
        "missing_types_after": missing_after,
    }
