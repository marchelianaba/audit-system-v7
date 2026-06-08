"""Lapisan fallback ekstraksi untuk dokumen yang TIDAK tertangani parser deterministik.

Skema dua-tingkat (lihat docs/diskusi digestion):
  1. ADA PARSER → digest deterministik V6 (gratis, cepat, reproducible) = jalur utama.
  2. TIDAK ADA PARSER / field kurang → fallback LLM murah (Haiku) atas TEKS dokumen.

Asumsi operasional: TIDAK ada dokumen hasil scan (dikondisikan di input). Karena itu
teks SELALU bisa di-extract, sehingga fallback cukup mengirim TEKS (bukan gambar) ke
model murah — hemat token & deterministik-ish. Untuk dokumen yang memuat GAMBAR
pembawa-data (tabel/diagram di-render jadi gambar), modul ini hanya MEN-DETEKSI +
menandai (analyze_images); penanganannya diserahkan ke kebijakan input / review manual.

Modul ini TIDAK menyentuh V6 sama sekali (ekstraksi teks pakai pdfplumber langsung).
Dipakai oleh backend/scripts/digestion_harness.py; bisa dipakai ulang produksi nanti.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

# Model murah default untuk fallback (Haiku = paling murah/cepat). Bisa di-override
# via argumen --llm-model atau env ANTHROPIC_FALLBACK_MODEL.
DEFAULT_LLM_MODEL = os.environ.get("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5-20251001")

# Ambang teks "sparse": rata-rata char/halaman di bawah ini → teks tipis (mungkin
# datanya ada di gambar). Hanya sinyal bantu, bukan vonis.
SPARSE_CHARS_PER_PAGE = 120

# Petunjuk (Indonesian) per nama-field — dipakai membangun prompt fallback supaya
# Haiku tahu persis apa yang diminta. Key = nama field yang dipakai _COVERAGE_KEYS.
FIELD_HINTS: dict[str, str] = {
    "kementerian": "Nama Kementerian/Lembaga (mis. 'Komunikasi dan Digital').",
    "program_nama": "Nama Program (teks setelah label 'Program').",
    "kegiatan_nama": "Nama Kegiatan (teks setelah label 'Kegiatan').",
    "ro": "Nama Rincian Output (RO).",
    "total_biaya": "Total biaya/anggaran dalam rupiah — ANGKA saja tanpa 'Rp'/titik (mis. 2450000000).",
    "dasar_hukum": "Daftar dasar hukum/regulasi yang disebut (array string singkat).",
    "jumlah_komponen": "Jumlah komponen/baris rincian dalam RAB — ANGKA saja.",
    "total_pagu": "Total pagu RAB dalam rupiah — ANGKA saja tanpa 'Rp'/titik.",
    "obyek": "Nama/objek pekerjaan pengadaan.",
    "nilai_hps": "Nilai HPS dalam rupiah — ANGKA saja tanpa 'Rp'/titik.",
    "jangka_waktu": "Jangka waktu/periode pelaksanaan (mis. '6 bulan' atau '12 bulan').",
    "metode_pemilihan": "Metode pemilihan penyedia (mis. 'Tender', 'Penunjukan Langsung', 'e-Purchasing').",
    # ---- Field tambahan PENGADAAN (3 Jun 2026, hybrid agresif) ----
    # Dipakai supaya temuan auditor substantif (mis. 'KAK tidak ada Dasar Hukum',
    # 'Vendor RFI dari alamat sama / terafiliasi', 'Jadwal pengadaan lewat masa
    # berlaku lisensi') punya bahan ekstrak dari fallback Haiku.
    "dasar_hukum_kak": (
        "ARRAY string regulasi yang disebut KAK sebagai dasar hukum pengadaan "
        "(mis. ['UU 11/2008', 'Perpres 16/2018', 'Perpres 12/2021']). Bila KAK "
        "TIDAK punya seksi 'Dasar Hukum' yang eksplisit (hanya footer e-materai/UU "
        "ITE), kembalikan ARRAY KOSONG []. Footer/legalisasi e-materai BUKAN dasar "
        "hukum pengadaan."
    ),
    "ruang_lingkup": (
        "Ringkasan ruang lingkup pekerjaan dari KAK (apa yang di-procure: "
        "barang/jasa, perpanjangan/baru, kuantitas). 1-3 kalimat."
    ),
    "spesifikasi_teknis_ringkas": (
        "Ringkasan spesifikasi teknis dari KAK (mis. 'Lisensi Fortigate FG-601E "
        "UTP 1 tahun, untuk 4 unit'). 1-3 kalimat. Bila tidak terperinci di KAK, "
        "kembalikan null."
    ),
    "jadwal_pengadaan": (
        "ARRAY tahapan jadwal pengadaan dari KAK ({tahap, periode}). "
        "Contoh: [{'tahap': 'Penerimaan RFI', 'periode': '24 Feb – 5 Mar 2026'}]. "
        "Bila hanya total durasi (mis. '10 hari kerja') kembalikan satu entri "
        "tahap='Total durasi'."
    ),
    "sumber_referensi_harga": (
        "ARRAY sumber harga yang dipakai menyusun HPS, dari dokumen HPS atau RFI. "
        "Setiap entri: {nama_sumber, nilai_rupiah, tanggal_atau_nomor}. Contoh: "
        "[{'nama_sumber':'RFI PT Mahameru','nilai_rupiah':643800000,"
        "'tanggal_atau_nomor':'07/SPI/SIS/II/2026 - 27 Feb 2026'}, ...]. Auditor "
        "pakai untuk menilai kewajaran (Perpres 16/2018 Pasal 26 ayat 5: minimal "
        "2 sumber INDEPENDEN)."
    ),
    "nama_vendor_rfi": (
        "ARRAY string nama vendor yang muncul dalam dokumen RFI (Request For "
        "Information / Surat Pemberian Informasi / proposal vendor). Format: "
        "['PT Mahameru Informatika Pratama', 'PT Digital Fatih Indonesia']. "
        "Auditor pakai untuk cek vendor sejenis/terafiliasi."
    ),
    "masa_berlaku_existing": (
        "Bila pengadaan adalah PERPANJANGAN/RENEWAL lisensi yang sudah ada, "
        "kapan lisensi existing habis (format ISO YYYY-MM-DD bila tertera). "
        "Kalau bukan renewal atau tidak tertera, kembalikan null. Auditor pakai "
        "untuk cek apakah jadwal pengadaan lewat batas (risiko service mati)."
    ),
}


# ---------------------------------------------------------------------------
# Ekstraksi teks + analisis gambar (pdfplumber — tanpa poppler/V6)
# ---------------------------------------------------------------------------

def extract_pdf_pages(path: str | Path) -> list[str]:
    """Teks per-halaman PDF. Return [] bila gagal/tidak ada teks.

    URUTAN:
      1. LiteParse (cepat, layout-aware, ~1-3 ms/halaman) — default.
      2. Bila LiteParse tak ada / gagal / hasil kosong → fallback pdfplumber.

    Sengaja TIDAK pakai pdftotext supaya independen dari poppler & V6.
    """
    # 1) Coba LiteParse dulu (deterministik, jauh lebih cepat & rapi)
    try:
        from app.liteparse_extract import extract_pages as _lp_pages, available as _lp_avail
        if _lp_avail():
            pages = _lp_pages(path)
            if any(p.strip() for p in pages):
                return pages
    except Exception:  # noqa: BLE001 — LiteParse opsional; jangan crash konsumer
        pass

    # 2) Fallback pdfplumber
    try:
        import pdfplumber
    except ImportError:
        return []
    pages: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for pg in pdf.pages:
                pages.append(pg.extract_text() or "")
    except Exception:  # noqa: BLE001 — PDF rusak/terenkripsi → anggap tak ada teks
        return []
    return pages


def analyze_images(path: str | Path) -> dict:
    """Hitung gambar tertanam per halaman (pdfplumber `page.images`).

    Bukan OCR — hanya menghitung. Dipakai harness untuk menandai dokumen yang
    mungkin menyembunyikan data di gambar (tabel/diagram → image).

    Return: {total_pages, total_images, pages_with_images, per_page:[...]}.
    """
    res = {"total_pages": 0, "total_images": 0, "pages_with_images": 0, "per_page": []}
    try:
        import pdfplumber
    except ImportError:
        return res
    try:
        with pdfplumber.open(str(path)) as pdf:
            per_page = []
            for pg in pdf.pages:
                n = len(pg.images or [])
                per_page.append(n)
            res["total_pages"] = len(per_page)
            res["per_page"] = per_page
            res["total_images"] = sum(per_page)
            res["pages_with_images"] = sum(1 for n in per_page if n > 0)
    except Exception:  # noqa: BLE001
        return res
    return res


def text_stats(pages: list[str]) -> dict:
    """Statistik teks ringkas untuk deteksi 'sparse' (data mungkin di gambar)."""
    total_chars = sum(len(p or "") for p in pages)
    n = max(1, len(pages))
    per_page = total_chars / n
    return {
        "total_chars": total_chars,
        "chars_per_page": round(per_page, 1),
        "sparse": per_page < SPARSE_CHARS_PER_PAGE,
    }


# ---------------------------------------------------------------------------
# Resolusi API key (standalone-friendly: harness jalan tanpa uvicorn)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def resolve_anthropic_key() -> str | None:
    """Cari ANTHROPIC_API_KEY: env dulu, lalu file .env terdekat (naik ke atas).

    pydantic-settings kadang tidak mengangkat key di konteks script standalone,
    jadi kita baca .env langsung via python-dotenv sebagai fallback.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip() or None
    try:
        from dotenv import dotenv_values
    except ImportError:
        return None
    here = Path(__file__).resolve()
    for parent in [Path.cwd(), *Path.cwd().parents, *here.parents]:
        env_file = parent / ".env"
        if env_file.is_file():
            val = (dotenv_values(env_file).get("ANTHROPIC_API_KEY") or "").strip()
            if val:
                return val
    return None


# ---------------------------------------------------------------------------
# Fallback ekstraksi LLM (Haiku) atas TEKS dokumen
# ---------------------------------------------------------------------------

def _parse_json_block(text: str) -> dict:
    """Ambil objek JSON dari balasan model (toleran terhadap fence/teks tambahan)."""
    if not text:
        return {}
    t = text.strip()
    # buang code fence ```json ... ```
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass
    # fallback: ambil substring kurung kurawal terluar
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def extract_fields_hybrid(
    pages_text: list[str],
    jenis_label: str,
    fields: list[str],
    *,
    model: str = DEFAULT_LLM_MODEL,
    api_key: str | None = None,
    max_chars: int = 14000,
    max_tokens: int = 700,
) -> dict:
    """Hybrid extractor: REGEX deterministik dulu, LLM Haiku hanya untuk sisa.

    Urutan:
      1. `liteparse_extract.extract_fields_deterministic(pages, jenis)` — tarik
         field yang labelnya eksplisit (kementerian, total_biaya, dasar_hukum, …)
         via regex. Hampir gratis, ~µs.
      2. Hitung field yang DIMINTA tapi belum dapat (sub-set `fields`).
      3. Bila masih ada residual, panggil `llm_extract_fields` Haiku untuk
         residual saja. Bila semua sudah tertangani regex → SKIP LLM.

    Return:
      - {field: value, ...} hasil gabungan
      - `_source` per field bila konsumer butuh trace (opsional, default off)
    """
    # Step 1: regex deterministik
    try:
        from app.liteparse_extract import extract_fields_deterministic
        det = extract_fields_deterministic(pages_text, jenis_label)
    except Exception:  # noqa: BLE001
        det = {}

    # Filter ke field yang DIMINTA saja
    out: dict = {f: det[f] for f in fields if f in det and det[f] not in (None, "", [], {})}

    # Step 2: hitung residual
    residual = [f for f in fields if f not in out]
    if not residual:
        return out

    # Step 3: panggil Haiku untuk residual saja (hemat token + lebih fokus)
    llm_res = llm_extract_fields(
        pages_text, jenis_label, residual,
        model=model, api_key=api_key,
        max_chars=max_chars, max_tokens=max_tokens,
    )
    if llm_res.get("_error"):
        # Tetap return hasil regex saja; serahkan error ke caller via _error
        return {**out, "_error": llm_res["_error"]}
    for f in residual:
        v = llm_res.get(f)
        if v not in (None, "", [], 0):
            out[f] = v
    return out


def llm_extract_fields(
    pages_text: list[str],
    jenis_label: str,
    fields: list[str],
    *,
    model: str = DEFAULT_LLM_MODEL,
    api_key: str | None = None,
    max_chars: int = 14000,
    max_tokens: int = 700,
) -> dict:
    """Minta model murah mengekstrak `fields` dari TEKS dokumen → dict {field: value|None}.

    Hanya dipanggil saat parser deterministik gagal/kurang (fallback). Mengirim teks
    (di-cap `max_chars`) — bukan gambar — supaya hemat & cepat.

    Return:
      - sukses: {field: value_or_None, ...} (hanya key yang diminta)
      - gagal:  {"_error": "<alasan>"}
    """
    text = "\n\n".join(p for p in pages_text if p).strip()
    if not text:
        return {"_error": "tidak ada teks (mungkin dokumen gambar/scan — di luar cakupan)"}

    key = api_key or resolve_anthropic_key()
    if not key:
        return {"_error": "ANTHROPIC_API_KEY tidak tersedia"}

    try:
        import anthropic
    except ImportError:
        return {"_error": "paket anthropic tidak terinstall"}

    # potong teks: utamakan awal dokumen (identitas/biaya umumnya di depan)
    snippet = text[:max_chars]

    field_lines = "\n".join(
        f'  - "{f}": {FIELD_HINTS.get(f, "isi field ini bila ada di dokumen.")}'
        for f in fields
    )
    system = (
        "Anda pengekstrak data dokumen perencanaan/pengadaan pemerintah Indonesia. "
        "Tugas: dari TEKS dokumen, ambil nilai field yang diminta. "
        "Jawab HANYA satu objek JSON valid, tanpa penjelasan, tanpa markdown. "
        "Jika sebuah field tidak ditemukan, isi null. Untuk field nilai uang, "
        "kembalikan angka saja (tanpa 'Rp', tanpa titik pemisah ribuan)."
    )
    prompt = (
        f"Jenis dokumen: {jenis_label}\n"
        f"Ekstrak field berikut menjadi JSON dengan key persis seperti ini:\n"
        f"{field_lines}\n\n"
        f"=== TEKS DOKUMEN (dipotong) ===\n{snippet}"
    )

    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        )
    except Exception as e:  # noqa: BLE001 — API/jaringan/model error → jangan crash harness
        return {"_error": f"panggilan LLM gagal: {str(e)[:160]}"}

    parsed = _parse_json_block(raw)
    if not parsed:
        return {"_error": "balasan LLM bukan JSON valid"}

    # ambil hanya field yang diminta; normalkan "" → None
    out: dict = {}
    for f in fields:
        v = parsed.get(f)
        if isinstance(v, str) and not v.strip():
            v = None
        out[f] = v
    return out
