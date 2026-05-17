"""Tool wrappers untuk orchestrator V6: run_batch.py per skill."""
from pathlib import Path

from claude_agent_sdk import tool

from app.tools.v6_bridge import run_v6_script, safe_read_json


@tool(
    "run_batch_rka",
    "Jalankan pipeline lengkap V6 reviu-rka-kl (39 rules + digest + cross-check + render). "
    "Output: _KKP/anomalies-master.json, _KKP/tor-{N}.json, _KKP/rab-{N}.json, _LHP/LHR-DRAFT.docx.",
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
    code, out, err = await run_v6_script(
        "scripts/reviu-rka-kl/run_batch.py",
        [
            "--penugasan",
            args["penugasan_folder"],
            "--workers",
            str(args.get("workers", 4)),
            "--judul",
            args.get("judul", "Laporan Hasil Reviu RKA-K/L"),
            "--nomor",
            args.get("nomor", "[DIISI AUDITOR]"),
            "--tanggal",
            args.get("tanggal", "[DIISI AUDITOR]"),
            "--penerima",
            args.get("penerima", "[DIISI AUDITOR]"),
        ],
        timeout=300,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:600]}"}],
            "is_error": True,
        }
    folder = Path(args["penugasan_folder"])
    anomalies = safe_read_json(folder / "_KKP" / "anomalies-master.json")
    total = len(anomalies) if isinstance(anomalies, list) else len(anomalies.get("anomalies", []))
    return {
        "content": [
            {"type": "text", "text": f"OK|anomalies_total={total}|output={folder / '_KKP'}"}
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
        extra = ["--role", "AT", "--no-render"]
    else:
        extra = ["--role", "KT", "--context", args.get("context_path", "")]
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
