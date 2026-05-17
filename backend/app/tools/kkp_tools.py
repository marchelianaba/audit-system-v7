"""Tools untuk Agen Anggota Tim: append temuan ke temuan.json, render KKP.docx."""
import json
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import tool

from app.tools.v6_bridge import run_v6_script, safe_read_json


@tool(
    "read_context",
    "Baca context.md + sasaran-assignment.json penugasan.",
    {"penugasan_folder": str},
)
async def read_context(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    context_md = (folder / "context.md").read_text(encoding="utf-8") if (folder / "context.md").exists() else ""
    assignment = safe_read_json(folder / "_PKP" / "sasaran-assignment.json")
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {"context_md": context_md, "sasaran_assignment": assignment},
                    ensure_ascii=False,
                ),
            }
        ]
    }


@tool(
    "list_ingested",
    "Daftar file JSON hasil ingestion di _INGESTED/.",
    {"penugasan_folder": str},
)
async def list_ingested(args: dict) -> dict:
    folder = Path(args["penugasan_folder"]) / "_INGESTED"
    files = [p.name for p in folder.glob("*.json")] if folder.exists() else []
    return {"content": [{"type": "text", "text": "\n".join(files) or "(kosong)"}]}


@tool(
    "append_temuan",
    "Append 1 temuan ke _KKP/temuan.json. Struktur input mengikuti schema kkp-temuan.",
    {
        "penugasan_folder": str,
        "temuan": dict,
    },
)
async def append_temuan(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    path = folder / "_KKP" / "temuan.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict
    if path.exists():
        data = safe_read_json(path) or {"penugasan_id": folder.name, "temuan": []}
    else:
        data = {"penugasan_id": folder.name, "skill": "", "version": "1.0", "temuan": []}

    new_temuan = dict(args["temuan"])
    new_temuan.setdefault("tanggal_input", datetime.utcnow().isoformat() + "Z")
    new_temuan.setdefault("status", "DRAFT")
    new_temuan.setdefault("catatan_ketua_tim", None)
    new_temuan.setdefault("integral", None)

    if not new_temuan.get("id_temuan"):
        seq = len(data["temuan"]) + 1
        new_temuan["id_temuan"] = f"T-{seq:03d}"

    data["temuan"].append(new_temuan)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "content": [
            {"type": "text", "text": f"OK|id={new_temuan['id_temuan']}|total_now={len(data['temuan'])}"}
        ]
    }


@tool(
    "render_kkp_docx",
    "Render KKP-{nama-anggota}.docx menggunakan scripts/render_kkp.py V6.",
    {"penugasan_folder": str, "nama_anggota": str},
)
async def render_kkp_docx(args: dict) -> dict:
    code, out, err = await run_v6_script(
        "scripts/render_kkp.py",
        [
            "--penugasan",
            args["penugasan_folder"],
            "--anggota",
            args["nama_anggota"],
        ],
        timeout=120,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:400]}"}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": f"OK|stdout={out[:200]}"}]}


@tool(
    "request_qc_kkp",
    "Trigger Agen QC SAIPI stage KKP. Web orchestrator akan memanggil agen QC terpisah.",
    {"penugasan_folder": str},
)
async def request_qc_kkp(args: dict) -> dict:
    # Tool ini hanya menulis "marker" — orchestrator agent SDK di routes/agen.py
    # akan mendeteksinya dan men-spawn agen QC SAIPI.
    marker = Path(args["penugasan_folder"]) / "_QA-SAIPI" / "_pending-kkp.flag"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
    return {"content": [{"type": "text", "text": "QC_KKP_REQUESTED"}]}


KKP_TOOLS = [read_context, list_ingested, append_temuan, render_kkp_docx, request_qc_kkp]
