"""Lapisan ekstraksi DETERMINISTIK berbasis LiteParse (run-llama/liteparse).

Motivasi: gantikan/lengkapi pdfplumber + Haiku fallback dengan parser cepat yang:
- 100% local (Apache 2.0 / MIT), tanpa API key
- Mendukung PDF, DOCX, XLSX, PPTX, image (OCR Tesseract bundled)
- Spatial text + bounding box (bisa untuk extraction layout-aware)
- ~1-3 ms/halaman PDF text-based, ~5-20 detik bila perlu OCR

Strategi pakai:
  1. `extract_pages(path)` → list[str] (drop-in replacement `extract_pdf_pages`)
  2. `extract_fields_deterministic(pages, jenis)` → ambil field umum via REGEX
     atas teks LiteParse yang sudah bersih (jauh lebih rapi vs pdfplumber kasar).
  3. Hanya bila field kritis tetap kosong, panggil `llm_extract_fields` (Haiku).

Modul ini TIDAK menyentuh V6 dan TIDAK panggil LLM sama sekali.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

# OCR di-OFF default: dokumen Kominfo digital. Bisa di-toggle via env.
_OCR_DEFAULT = os.environ.get("LITEPARSE_OCR_ENABLED", "0").lower() in ("1", "true", "yes")
_QUIET_DEFAULT = os.environ.get("LITEPARSE_QUIET", "1").lower() in ("1", "true", "yes")


# Ekstensi yang LiteParse handle (PDF native, office via LibreOffice, image via Tesseract).
_LITEPARSE_EXTS = {
    ".pdf",
    ".docx", ".doc", ".odt", ".rtf",
    ".xlsx", ".xls", ".ods", ".csv",
    ".pptx", ".ppt", ".odp",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
    ".txt", ".md",
}


@lru_cache(maxsize=2)
def _get_parser(ocr_enabled: bool, quiet: bool):
    """Lazy-load LiteParse parser; cached so we tidak ulang setup tiap call."""
    try:
        from liteparse import LiteParse
    except ImportError:  # pragma: no cover — package opsional saat dev
        return None
    return LiteParse(ocr_enabled=ocr_enabled, quiet=quiet)


def is_supported(path: str | Path) -> bool:
    """Cek apakah ekstensi file di-support LiteParse."""
    return Path(path).suffix.lower() in _LITEPARSE_EXTS


def available() -> bool:
    """True bila LiteParse terinstall."""
    return _get_parser(_OCR_DEFAULT, _QUIET_DEFAULT) is not None


# ---------------------------------------------------------------------------
# Public API — text extraction
# ---------------------------------------------------------------------------

def extract_pages(
    path: str | Path,
    *,
    ocr: bool | None = None,
    quiet: bool | None = None,
) -> list[str]:
    """Ekstrak teks per-halaman. Return [] bila gagal/tidak support.

    Drop-in replacement untuk `llm_extract.extract_pdf_pages` dengan keunggulan:
    - Lebih cepat (1-3 ms/p PDF tanpa OCR vs 30-80 ms pdfplumber)
    - Layout lebih bersih (kolom angka RAB utuh, bukan tercampur)
    - Multi-format (DOCX/XLSX/PPTX juga di-handle)
    """
    p = Path(path)
    if not p.is_file() or not is_supported(p):
        return []
    parser = _get_parser(
        _OCR_DEFAULT if ocr is None else ocr,
        _QUIET_DEFAULT if quiet is None else quiet,
    )
    if parser is None:
        return []
    try:
        result = parser.parse(str(p))
    except Exception:  # noqa: BLE001 — rusak/encrypted → diam
        return []
    pages: list[str] = []
    for pg in getattr(result, "pages", []) or []:
        pages.append(getattr(pg, "text", "") or "")
    # Bila hanya 1 doc page kosong tapi `result.text` ada (untuk format non-paged),
    # masukkan sebagai satu page.
    if not pages and getattr(result, "text", ""):
        pages = [result.text]
    return pages


def extract_full_text(path: str | Path, **kwargs) -> str:
    """Teks satu blob (semua halaman digabung dengan dua newline)."""
    return "\n\n".join(p for p in extract_pages(path, **kwargs) if p)


# ---------------------------------------------------------------------------
# Public API — field extraction REGEX (deterministik, hardcode)
#
# Berlaku pada teks LiteParse yang relatif bersih. Pattern di-tuning untuk
# dokumen perencanaan/pengadaan pemerintah Indonesia (RKA-K/L, KAK, HPS, RFI).
# Tidak panggil LLM. Hanya extract apa yang label-nya eksplisit.
# ---------------------------------------------------------------------------

# Pola label fleksibel: "Label : nilai" / "Label nilai" (tab/space/newline)
def _grab(text: str, labels: Iterable[str]) -> str | None:
    """Cari nilai setelah salah satu label. Case-insensitive, lintas baris.

    Heuristic: label diikuti `:` atau spasi panjang, ambil hingga newline.
    """
    for lbl in labels:
        pat = re.compile(
            rf"(?im)^\s*{re.escape(lbl)}\s*[:\-]?\s*(.+?)$",
        )
        m = pat.search(text)
        if m:
            v = m.group(1).strip(" \t-:")
            # Buang trailing dot/colon/space
            v = re.sub(r"\s+", " ", v).strip()
            if v and v.lower() not in ("none", "null", "-", "n/a"):
                return v
    return None


def _grab_money(text: str, labels: Iterable[str]) -> int | None:
    """Cari nilai uang setelah label. Return int rupiah, atau None.

    PENTING: regex stop di newline supaya tidak menyerap angka kode/baris
    berikutnya (mis. 'Alokasi Dana: Rp 2,450,000,000\\n5241.QDC.001.051').
    """
    for lbl in labels:
        # Hanya match angka dengan separator titik/koma/spasi DI SATU BARIS.
        pat = re.compile(
            rf"(?im){re.escape(lbl)}\s*[:\-]?\s*Rp\.?\s*([0-9][0-9\.\,]*(?:\s[0-9\.\,]+)*)",
        )
        m = pat.search(text)
        if m:
            n = _parse_rupiah(m.group(1))
            if n is not None and n >= 1000:
                return n
    # Fallback: label tanpa "Rp" — masih satu baris saja.
    for lbl in labels:
        pat = re.compile(
            rf"(?im){re.escape(lbl)}\s*[:\-]?\s*([0-9][0-9\.\,]{{4,}})",
        )
        m = pat.search(text)
        if m:
            n = _parse_rupiah(m.group(1))
            # Filter angka kecil (jumlah unit) DAN angka mustahil-besar (>1 triliun =
            # kemungkinan terkonkat dengan kode rincian seperti '5241.QDC.001').
            if n is not None and 1000 <= n < 1_000_000_000_000:
                return n
    return None


_RP_CLEAN_RE = re.compile(r"[^\d]")


def _parse_rupiah(s: str) -> int | None:
    """'2,450,000,000' / '2.450.000.000' / '2 450 000 000' → 2450000000."""
    if not s:
        return None
    cleaned = _RP_CLEAN_RE.sub("", s)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


# Pola regulasi: "UU 11/2008", "PP No. 60 Tahun 2008", "Perpres 16/2018",
# "Permenpan RB 5/2019". Output dinormalkan ringkas.
_REGULATION_RE = re.compile(
    r"\b("
    r"UU(?:D)?\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?|"
    r"PP\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?|"
    r"Perpres\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?|"
    r"Permen(?:pan(?:\s*RB)?|keu|kominfo|komdigi)?\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?|"
    r"Perka(?:ban)?\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?|"
    r"Kepres\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?|"
    r"Inpres\s*(?:No\.?\s*|Nomor\s*)?\d+(?:\s*[/Tahun]+\s*\d{4})?"
    r")\b",
    re.IGNORECASE,
)


def _norm_regulation(s: str) -> str:
    """'UU No. 11 Tahun 2008' → 'UU 11/2008'."""
    s = re.sub(r"\bNo\.?\s*|Nomor\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*Tahun\s*", "/", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    # Standar singkatan
    s = re.sub(r"^uud?\b", "UU", s, flags=re.IGNORECASE)
    s = re.sub(r"^pp\b", "PP", s, flags=re.IGNORECASE)
    s = re.sub(r"^perpres\b", "Perpres", s, flags=re.IGNORECASE)
    s = re.sub(r"^permen", "Permen", s, flags=re.IGNORECASE)
    return s


def extract_dasar_hukum(text: str, max_items: int = 20) -> list[str]:
    """Tarik regulasi yang disebut di dokumen. Dedup, urutkan stabil."""
    seen: dict[str, None] = {}
    for m in _REGULATION_RE.finditer(text):
        norm = _norm_regulation(m.group(1))
        if norm and norm not in seen:
            seen[norm] = None
            if len(seen) >= max_items:
                break
    return list(seen.keys())


# Pola vendor PT/CV/UD/Yayasan. Hindari false-positive ("PT 1" / "PT.").
_VENDOR_RE = re.compile(
    r"\b(?:PT|CV|UD|Yayasan|Koperasi|Firma|Perum|Persero)\.?\s+"
    r"([A-Z][A-Za-z0-9&.,\-' ]{2,80}?)"
    r"(?=[\.\n,;)]|\s{3,}|$)",
    re.MULTILINE,
)


def extract_vendor_names(text: str, max_items: int = 30) -> list[str]:
    """Tarik nama vendor (PT/CV/...). Dedup case-insensitive."""
    seen: dict[str, str] = {}
    for m in _VENDOR_RE.finditer(text):
        full = re.sub(r"\s+", " ", m.group(0)).strip(".,; ")
        key = full.lower()
        if key not in seen and len(full) > 5:
            seen[key] = full
            if len(seen) >= max_items:
                break
    return list(seen.values())


_DATE_RE = re.compile(
    r"\b(\d{1,2})[\s/\-](Jan(?:uari)?|Feb(?:ruari)?|Mar(?:et)?|Apr(?:il)?|Mei|"
    r"Jun(?:i)?|Jul(?:i)?|Agu(?:stus)?|Sep(?:tember)?|Okt(?:ober)?|"
    r"Nov(?:ember)?|Des(?:ember)?)[\s/\-](\d{4})\b",
    re.IGNORECASE,
)
_MONTH_ID = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "agu": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}


def extract_dates_iso(text: str, max_items: int = 20) -> list[str]:
    """Tarik tanggal Indonesia → ISO YYYY-MM-DD. Dedup berurut."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _DATE_RE.finditer(text):
        d, mon, y = m.group(1), m.group(2)[:3].lower(), m.group(3)
        mm = _MONTH_ID.get(mon)
        if not mm:
            continue
        try:
            iso = f"{int(y):04d}-{mm:02d}-{int(d):02d}"
        except ValueError:
            continue
        if iso not in seen:
            seen.add(iso)
            out.append(iso)
            if len(out) >= max_items:
                break
    return out


def extract_fields_deterministic(
    pages_text: list[str] | str,
    jenis: str,
) -> dict:
    """Deterministic field extraction berbasis regex atas teks LiteParse.

    `jenis` mempengaruhi field mana yang dicari (TOR/RAB/KAK/HPS/RFI/Kontrak).
    Field yang tidak ditemukan → None. Yang ketemu → string/int/list.

    Tujuan: maksimal coverage SEBELUM jatuh ke Haiku. Setiap field yang
    bisa kita yakini hardcode (label eksplisit) → kita ambil di sini.
    """
    text = pages_text if isinstance(pages_text, str) else "\n\n".join(p for p in pages_text if p)
    if not text:
        return {}

    jenis_lower = (jenis or "").lower()
    out: dict = {}

    # --- Identitas dokumen RKA-K/L (TOR + RAB punya header serupa) ---
    out["kementerian"] = _grab(text, [
        "Kementerian Negara/Lembaga", "Kementerian/Lembaga", "Kementerian",
    ])
    out["program_nama"] = _grab(text, ["Program"])
    out["kegiatan_nama"] = _grab(text, ["Kegiatan"])
    out["ro"] = _grab(text, [
        "Rincian Output", "Rincian Output (RO)", "Klasifikasi Rincian Output",
    ])

    # --- Nilai uang ---
    out["total_biaya"] = _grab_money(text, [
        "Total Biaya", "Total Anggaran", "Alokasi Dana", "Pagu Anggaran",
        "Jumlah Biaya",
    ])
    out["total_pagu"] = _grab_money(text, [
        "Total Pagu", "Pagu RAB", "Jumlah Pagu", "Total Belanja",
    ])
    out["nilai_hps"] = _grab_money(text, [
        "Nilai HPS", "Harga Perkiraan Sendiri", "HPS",
    ])

    # --- Dasar hukum (general regulasi) ---
    regs = extract_dasar_hukum(text)
    if regs:
        out["dasar_hukum"] = regs

    # --- KAK-specific ---
    if "kak" in jenis_lower or "kerangka acuan" in text.lower()[:500]:
        # Untuk KAK: hanya hitung sebagai dasar_hukum_kak bila SEKSI eksplisit "Dasar Hukum" ada
        if re.search(r"(?im)^\s*[A-Z\d.]*\s*Dasar\s+Hukum\b", text):
            out["dasar_hukum_kak"] = regs or []
        else:
            out["dasar_hukum_kak"] = []  # tegas-kan tidak ada seksi
        out["ruang_lingkup"] = _grab(text, [
            "Ruang Lingkup", "Lingkup Pekerjaan", "Lingkup Kegiatan",
        ])
        out["jangka_waktu"] = _grab(text, [
            "Jangka Waktu", "Waktu Pelaksanaan", "Periode Pelaksanaan",
            "Durasi", "Lama Pelaksanaan",
        ])
        out["metode_pemilihan"] = _grab(text, [
            "Metode Pemilihan", "Metode Pengadaan", "Cara Pengadaan",
        ])

    # --- HPS-specific ---
    if "hps" in jenis_lower:
        # Sumber referensi harga: kumpulkan kalimat yang sebut "RFI"/"penawaran" + vendor + nominal
        # Sederhana: kumpulkan vendor + nominal RFI/penawaran di dekat-dekatnya.
        sources: list[dict] = []
        for m in re.finditer(
            r"(PT|CV|UD)\.?\s+([A-Z][\w&., '\-]{2,60})[\s\S]{0,80}?Rp\.?\s*([\d.,]+)",
            text,
        ):
            nama = f"{m.group(1)} {m.group(2)}".strip()
            nilai = _parse_rupiah(m.group(3))
            if nilai and nilai > 1000:
                sources.append({
                    "nama_sumber": nama,
                    "nilai_rupiah": nilai,
                    "tanggal_atau_nomor": None,
                })
                if len(sources) >= 10:
                    break
        if sources:
            out["sumber_referensi_harga"] = sources

    # --- RFI-specific ---
    if "rfi" in jenis_lower:
        vendors = extract_vendor_names(text)
        if vendors:
            out["nama_vendor_rfi"] = vendors

    # --- Kontrak/renewal: tanggal expire ---
    if any(k in text.lower() for k in ("renewal", "perpanjangan", "habis berlaku", "masa berlaku")):
        dates = extract_dates_iso(text)
        if dates:
            # Ambil tanggal pertama yang berada dalam range masuk akal (2025-2030)
            for d in dates:
                if "2024" <= d[:4] <= "2030":
                    out["masa_berlaku_existing"] = d
                    break

    # --- RAB: hitung jumlah komponen (baris angka uang) ---
    if "rab" in jenis_lower:
        # Heuristik: tiap baris yang punya ≥2 angka uang besar dianggap satu komponen.
        n = 0
        for line in text.splitlines():
            money_hits = re.findall(r"[\d.,]{7,}", line)
            big = [x for x in money_hits if _parse_rupiah(x) and _parse_rupiah(x) >= 10_000]
            if len(big) >= 2:
                n += 1
        if n > 0:
            out["jumlah_komponen"] = n

    # Drop key kosong supaya gampang cek coverage
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


# ---------------------------------------------------------------------------
# Image counter (sinyal bantu dokumen mungkin scan/gambar)
# ---------------------------------------------------------------------------

def analyze_images(path: str | Path) -> dict:
    """Hitung gambar tertanam per halaman.

    LiteParse tidak expose ini langsung; jatuhkan ke pdfplumber bila PDF.
    """
    res = {"total_pages": 0, "total_images": 0, "pages_with_images": 0, "per_page": []}
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return res
    try:
        import pdfplumber
    except ImportError:
        return res
    try:
        with pdfplumber.open(str(p)) as pdf:
            per_page = [len(pg.images or []) for pg in pdf.pages]
            res["total_pages"] = len(per_page)
            res["per_page"] = per_page
            res["total_images"] = sum(per_page)
            res["pages_with_images"] = sum(1 for n in per_page if n > 0)
    except Exception:  # noqa: BLE001
        pass
    return res
