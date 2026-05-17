"""Tools untuk Agen QC SAIPI: wrapper qc_saipi.py V6."""
from pathlib import Path

from claude_agent_sdk import tool

from app.tools.v6_bridge import run_v6_script, safe_read_json


@tool(
    "run_qc_saipi",
    "Jalankan scripts/qc_saipi.py V6 untuk gate kepatuhan SAIPI. "
    "stage='kkp' cek standar 1100/1200/2200/2300. stage='lhp' cek + 2400.",
    {"penugasan_folder": str, "stage": str},
)
async def run_qc_saipi(args: dict) -> dict:
    stage = args["stage"]
    code, out, err = await run_v6_script(
        "scripts/qc_saipi.py",
        ["--penugasan", args["penugasan_folder"], "--stage", stage],
        timeout=120,
    )
    folder = Path(args["penugasan_folder"])
    checklist = safe_read_json(folder / "_QA-SAIPI" / f"checklist-{stage}.json")

    # Hitung breakdown severity
    items = checklist.get("items", []) if isinstance(checklist, dict) else []
    total_kritis = sum(1 for i in items if i.get("severity") == "KRITIS")
    total_peringatan = sum(1 for i in items if i.get("severity") == "PERINGATAN")
    total_needs_review = sum(1 for i in items if i.get("severity") == "NEEDS_REVIEW")
    total_ok = sum(1 for i in items if i.get("severity") == "OK")

    if total_kritis > 0:
        status = "BLOCKED_KRITIS"
    elif total_peringatan > 0 or total_needs_review > 0:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    laporan_path = str(folder / "_QA-SAIPI" / f"laporan-qa-{stage}.md")

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"stage={stage}|status={status}|exit_code={code}|"
                    f"kritis={total_kritis}|peringatan={total_peringatan}|"
                    f"needs_review={total_needs_review}|ok={total_ok}|"
                    f"laporan={laporan_path}"
                ),
            }
        ]
    }


@tool(
    "read_laporan_qa",
    "Baca isi laporan-qa-{stage}.md untuk dijadikan ringkasan ke pengguna.",
    {"penugasan_folder": str, "stage": str},
)
async def read_laporan_qa(args: dict) -> dict:
    path = Path(args["penugasan_folder"]) / "_QA-SAIPI" / f"laporan-qa-{args['stage']}.md"
    if not path.exists():
        return {
            "content": [{"type": "text", "text": "FAILED|laporan QA belum ada"}],
            "is_error": True,
        }
    text = path.read_text(encoding="utf-8")
    return {"content": [{"type": "text", "text": text[:6000]}]}


QC_TOOLS = [run_qc_saipi, read_laporan_qa]
