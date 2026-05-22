"""Tool wrappers untuk orchestrator V6: run_batch.py per skill."""
import shutil
from pathlib import Path

from claude_agent_sdk import tool

from app.storage import classify_doc_by_filename
from app.tools.v6_bridge import run_v6_script, safe_read_json

# Subfolder tempat app menyimpan TOR/RAB (lihat storage.target_subfolder_for).
_RKA_SRC_SUBFOLDER = "03-perencanaan"


def _stage_rka_inputs(folder: Path) -> tuple[Path, Path, list[str]]:
    """Stage TOR/RAB PDF ke struktur yang dicari V6 run_batch.py.

    App menyimpan TOR/RAB di `03-perencanaan/` dengan nama asli, sedangkan
    auto-pair V6 mensyaratkan `input/objek/{TOR,RAB}/[N] ....pdf` (prefix angka
    = RO id) dan hanya membaca `.pdf`. Helper ini menjembatani gap itu:

    - scan `03-perencanaan/` (fallback ke root penugasan) untuk file TOR/RAB,
    - pasangkan TOR↔RAB berdasarkan urutan nama (TOR ke-i ↔ RAB ke-i = RO i),
    - copy ke `input/objek/TOR/[i] nama.pdf` dan `input/objek/RAB/[i] nama.pdf`,
    - lewati file non-PDF (mis. RAB .xlsx) karena digest V6 hanya menerima PDF.

    Return (tor_dir, rab_dir, warnings).
    """
    warnings: list[str] = []
    tor_files: list[Path] = []
    rab_files: list[Path] = []
    seen: set[str] = set()

    for src in (folder / _RKA_SRC_SUBFOLDER, folder):
        if not src.is_dir():
            continue
        for p in sorted(src.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_file() or p.name in seen:
                continue
            jenis = classify_doc_by_filename(p.name)
            if jenis not in ("TOR", "RAB"):
                continue
            seen.add(p.name)
            if p.suffix.lower() != ".pdf":
                warnings.append(
                    f"{jenis} '{p.name}' bukan PDF — digest V6 RKA hanya menerima PDF "
                    f"format cetak RKA-K/L, file dilewati."
                )
                continue
            (tor_files if jenis == "TOR" else rab_files).append(p)

    tor_dir = folder / "input" / "objek" / "TOR"
    rab_dir = folder / "input" / "objek" / "RAB"
    for d in (tor_dir, rab_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    for i, p in enumerate(tor_files, start=1):
        shutil.copy2(p, tor_dir / f"[{i}] {p.name}")
    for i, p in enumerate(rab_files, start=1):
        shutil.copy2(p, rab_dir / f"[{i}] {p.name}")

    n_pair = min(len(tor_files), len(rab_files))
    if len(tor_files) != len(rab_files):
        warnings.append(
            f"Jumlah TOR ({len(tor_files)}) ≠ RAB ({len(rab_files)}) — hanya "
            f"{n_pair} RO ber-pasangan yang akan diproses (sisanya di-skip auto-pair)."
        )
    if n_pair == 0:
        warnings.append(
            "Tidak ada pasangan TOR↔RAB PDF. Pastikan TOR dan RAB (PDF format "
            "RKA-K/L) sudah di-upload ke kategori perencanaan."
        )

    return tor_dir, rab_dir, warnings


@tool(
    "run_batch_rka",
    "Jalankan pipeline V6 reviu-rka-kl (digest + cross-check anomali). "
    "Otomatis staging TOR/RAB dari folder upload ke struktur yang dibutuhkan V6. "
    "Pipeline ini TIDAK merender LHR (jalan dengan --no-render): LHR adalah hasil "
    "kompilasi temuan.json yang sudah diapprove KT, dirender terpisah oleh KT via "
    "render_lhr_rka — BUKAN dari anomali mentah. "
    "Output: _KKP/anomalies-master.json, _KKP/tor-{N}.json, _KKP/rab-{N}.json.",
    {
        "penugasan_folder": str,
        "workers": int,
        "judul": str,
        "nomor": str,
        "tanggal": str,
        "penerima": str,
    },
)
async def run_batch_rka(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    tor_dir, rab_dir, warns = _stage_rka_inputs(folder)
    warn_txt = ("|warnings=" + "; ".join(warns)) if warns else ""

    if not any(tor_dir.glob("*.pdf")) or not any(rab_dir.glob("*.pdf")):
        return {
            "content": [{
                "type": "text",
                "text": f"FAILED|tidak ada pasangan TOR↔RAB PDF untuk diproses{warn_txt}",
            }],
            "is_error": True,
        }

    code, out, err = await run_v6_script(
        "scripts/reviu-rka-kl/run_batch.py",
        [
            "--penugasan",
            str(folder),
            "--tor-dir",
            "input/objek/TOR",
            "--rab-dir",
            "input/objek/RAB",
            "--workers",
            str(args.get("workers", 4)),
            # LHR di-render terpisah oleh KT dari temuan.json yang diapprove,
            # bukan dari anomali mentah pipeline. Skip Phase 4 render di sini.
            "--no-render",
        ],
        timeout=300,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:600]}{warn_txt}"}],
            "is_error": True,
        }
    anomalies = safe_read_json(folder / "_KKP" / "anomalies-master.json")
    total = len(anomalies) if isinstance(anomalies, list) else len(anomalies.get("anomalies", []))
    return {
        "content": [
            {"type": "text", "text": f"OK|anomalies_total={total}|output={folder / '_KKP'}{warn_txt}"}
        ]
    }


@tool(
    "run_batch_pbj",
    "Jalankan pipeline lengkap V6 reviu-pengadaan dengan role gating. "
    "AT → output KKP, KT → output LHR. Skript reuse digest_pengadaan dari audit-pengadaan.",
    {"penugasan_folder": str, "role": str, "context_path": str},
)
async def run_batch_pbj(args: dict) -> dict:
    extra: list[str] = []
    role = args.get("role", "AT").upper()
    if role == "AT":
        extra = ["--role", "AT"]
    else:
        extra = ["--role", "KT"]
    code, out, err = await run_v6_script(
        "scripts/reviu-pengadaan/run_batch.py",
        ["--penugasan", args["penugasan_folder"], *extra],
        timeout=300,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:600]}"}],
            "is_error": True,
        }
    folder = Path(args["penugasan_folder"])
    anomalies = safe_read_json(folder / "_KKP" / "anomalies.json")
    total = len(anomalies) if isinstance(anomalies, list) else len(anomalies.get("anomalies", []))
    return {
        "content": [
            {"type": "text", "text": f"OK|role={role}|anomalies_total={total}|output={folder / '_KKP'}"}
        ]
    }


@tool(
    "read_pdf_page",
    "Baca teks satu halaman PDF — dipakai agen untuk verifikasi false positive anomali.",
    {"pdf_path": str, "halaman": int},
)
async def read_pdf_page(args: dict) -> dict:
    from pdfplumber import open as open_pdf

    p = Path(args["pdf_path"])
    if not p.exists():
        return {
            "content": [{"type": "text", "text": f"FAILED|file tidak ada: {p}"}],
            "is_error": True,
        }
    try:
        with open_pdf(str(p)) as pdf:
            idx = max(0, args["halaman"] - 1)
            if idx >= len(pdf.pages):
                return {
                    "content": [
                        {"type": "text", "text": f"FAILED|halaman {args['halaman']} di luar rentang"}
                    ],
                    "is_error": True,
                }
            text = pdf.pages[idx].extract_text() or ""
        return {"content": [{"type": "text", "text": text[:4000]}]}
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"FAILED|{str(e)[:200]}"}],
            "is_error": True,
        }


PIPELINE_TOOLS = [run_batch_rka, run_batch_pbj, read_pdf_page]
