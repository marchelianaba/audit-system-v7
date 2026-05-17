"""Tools untuk Agen Ingestion: classify, deterministic digest, llm fallback, cache."""
from pathlib import Path

from claude_agent_sdk import tool
from sqlalchemy import select

from app.database import SessionLocal
from app.models import DocumentCache
from app.storage import classify_doc_by_filename, penugasan_folder
from app.tools.v6_bridge import run_v6_script, safe_read_json


@tool(
    "classify_doc",
    "Tentukan jenis dokumen (TOR/RAB/KAK/HPS/RFI/KONTRAK/ST/KP/PKP/OTHER) dari nama file.",
    {"nama_file": str},
)
async def classify_doc(args: dict) -> dict:
    nama_file = args["nama_file"]
    jenis = classify_doc_by_filename(nama_file)
    return {"content": [{"type": "text", "text": jenis}]}


@tool(
    "check_cache",
    "Cek apakah dokumen dengan SHA-256 ini sudah pernah di-ingest sebelumnya.",
    {"sha256": str},
)
async def check_cache(args: dict) -> dict:
    async with SessionLocal() as db:
        row = (
            await db.execute(select(DocumentCache).where(DocumentCache.sha256 == args["sha256"]))
        ).scalar_one_or_none()
        if row:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"HIT|jenis={row.jenis}|path={row.ingested_json_path}|extracted_by={row.extracted_by}",
                    }
                ]
            }
    return {"content": [{"type": "text", "text": "MISS"}]}


@tool(
    "save_cache",
    "Simpan hasil ekstraksi ke cache hash-based.",
    {"sha256": str, "jenis": str, "ingested_json_path": str, "extracted_by": str},
)
async def save_cache(args: dict) -> dict:
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(DocumentCache).where(DocumentCache.sha256 == args["sha256"]))
        ).scalar_one_or_none()
        if existing:
            return {"content": [{"type": "text", "text": "ALREADY_CACHED"}]}
        row = DocumentCache(
            sha256=args["sha256"],
            jenis=args["jenis"],
            ingested_json_path=args["ingested_json_path"],
            extracted_by=args["extracted_by"],
        )
        db.add(row)
        await db.commit()
    return {"content": [{"type": "text", "text": "SAVED"}]}


@tool(
    "digest_tor",
    "Ekstrak TOR (PDF) ke JSON dengan script V6 scripts/reviu-rka-kl/digest_tor.py.",
    {"penugasan_kode": str, "pdf_path": str, "output_path": str},
)
async def digest_tor(args: dict) -> dict:
    code, out, err = await run_v6_script(
        "scripts/reviu-rka-kl/digest_tor.py",
        [args["pdf_path"], "--no-raw", "-o", args["output_path"]],
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:500]}"}],
            "is_error": True,
        }
    data = safe_read_json(Path(args["output_path"]))
    summary = f"OK|RO={data.get('kode_ro', '?')}|judul={data.get('judul', '?')[:80]}"
    return {"content": [{"type": "text", "text": summary}]}


@tool(
    "digest_rab",
    "Ekstrak RAB (PDF/Excel) ke JSON dengan script V6 scripts/reviu-rka-kl/digest_rab.py.",
    {"penugasan_kode": str, "file_path": str, "output_path": str},
)
async def digest_rab(args: dict) -> dict:
    code, out, err = await run_v6_script(
        "scripts/reviu-rka-kl/digest_rab.py",
        [args["file_path"], "-o", args["output_path"]],
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:500]}"}],
            "is_error": True,
        }
    data = safe_read_json(Path(args["output_path"]))
    summary = (
        f"OK|line_items={len(data.get('line_items', []))}|total={data.get('total_rupiah', '?')}"
    )
    return {"content": [{"type": "text", "text": summary}]}


@tool(
    "digest_pengadaan",
    "Ekstrak dokumen pengadaan (KAK/HPS/RFI/Kontrak) dengan scripts/audit-pengadaan/digest_pengadaan.py. "
    "Folder penugasan dipindai semuanya.",
    {"penugasan_kode": str, "penugasan_folder": str, "output_path": str},
)
async def digest_pengadaan(args: dict) -> dict:
    code, out, err = await run_v6_script(
        "scripts/audit-pengadaan/digest_pengadaan.py",
        [args["penugasan_folder"], "-o", args["output_path"]],
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:500]}"}],
            "is_error": True,
        }
    data = safe_read_json(Path(args["output_path"]))
    summary = f"OK|dokumen_terdeteksi={len(data.get('dokumen', []))}"
    return {"content": [{"type": "text", "text": summary}]}


@tool(
    "extract_generic_llm",
    "Fallback ekstraksi untuk dokumen non-baku (PDF tanpa pipeline khusus). "
    "Panggil Claude Haiku dengan structured output untuk hasilkan JSON generic.",
    {"file_path": str, "output_path": str, "jenis": str},
)
async def extract_generic_llm(args: dict) -> dict:
    # Stub: di prototype awal, kita panggil pdfplumber → ringkasan teks → simpan
    # JSON generic. Versi lengkap memanggil Anthropic API dengan JSON Schema mode.
    from pdfplumber import open as open_pdf

    path = Path(args["file_path"])
    output = Path(args["output_path"])

    if not path.exists():
        return {
            "content": [{"type": "text", "text": f"FAILED|file tidak ada: {path}"}],
            "is_error": True,
        }

    try:
        text_chunks = []
        with open_pdf(str(path)) as pdf:
            for i, page in enumerate(pdf.pages[:30]):  # max 30 halaman untuk hemat
                t = page.extract_text() or ""
                if t.strip():
                    text_chunks.append({"halaman": i + 1, "teks": t.strip()})

        generic = {
            "jenis": args["jenis"],
            "nama_file": path.name,
            "total_halaman_diparse": len(text_chunks),
            "halaman": text_chunks,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(__import__("json").dumps(generic, ensure_ascii=False, indent=2))
        return {"content": [{"type": "text", "text": f"OK|halaman={len(text_chunks)}"}]}
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"FAILED|err={str(e)[:300]}"}],
            "is_error": True,
        }


INGESTION_TOOLS = [
    classify_doc,
    check_cache,
    save_cache,
    digest_tor,
    digest_rab,
    digest_pengadaan,
    extract_generic_llm,
]
