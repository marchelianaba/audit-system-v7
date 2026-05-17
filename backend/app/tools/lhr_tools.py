"""Tools untuk Agen Ketua Tim: baca temuan, completeness check, render LHR."""
import json
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import tool

from app.tools.v6_bridge import run_v6_script, safe_read_json


@tool(
    "read_temuan_json",
    "Baca _KKP/temuan.json penugasan.",
    {"penugasan_folder": str},
)
async def read_temuan_json(args: dict) -> dict:
    path = Path(args["penugasan_folder"]) / "_KKP" / "temuan.json"
    if not path.exists():
        return {
            "content": [{"type": "text", "text": "FAILED|temuan.json tidak ada"}],
            "is_error": True,
        }
    data = safe_read_json(path)
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}


@tool(
    "check_completeness",
    "Pastikan semua sasaran di sasaran-assignment.json sudah SELESAI_KKP.",
    {"penugasan_folder": str},
)
async def check_completeness(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    assignment = safe_read_json(folder / "_PKP" / "sasaran-assignment.json")
    sasaran_list = assignment.get("sasaran", []) if isinstance(assignment, dict) else []
    belum = [s for s in sasaran_list if s.get("status") != "SELESAI_KKP"]
    if belum:
        text = "BELUM_LENGKAP|sasaran_belum=" + json.dumps(
            [{"id": s.get("sasaran_id"), "assigned_to": s.get("assigned_to")} for s in belum],
            ensure_ascii=False,
        )
        return {"content": [{"type": "text", "text": text}], "is_error": False}
    return {
        "content": [{"type": "text", "text": f"OK|total_sasaran={len(sasaran_list)}|all_selesai_kkp=true"}]
    }


@tool(
    "write_rekomendasi_json",
    "Tulis _LHP/rekomendasi.json — mapping id_temuan ke teks rekomendasi.",
    {"penugasan_folder": str, "rekomendasi": dict},
)
async def write_rekomendasi_json(args: dict) -> dict:
    path = Path(args["penugasan_folder"]) / "_LHP" / "rekomendasi.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(args["rekomendasi"], ensure_ascii=False, indent=2), encoding="utf-8")
    return {"content": [{"type": "text", "text": f"OK|n_rekomendasi={len(args['rekomendasi'])}"}]}


@tool(
    "render_lhr_rka",
    "Render LHR Reviu RKA-K/L via scripts/reviu-rka-kl/render_lhr.py V6.",
    {
        "penugasan_folder": str,
        "judul": str,
        "auditi": str,
        "dasar_permintaan": str,
        "gambaran_umum": str,
        "tanggal_exit_meeting": str,
    },
)
async def render_lhr_rka(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    rekomendasi = folder / "_LHP" / "rekomendasi.json"
    if not rekomendasi.exists():
        return {
            "content": [{"type": "text", "text": "FAILED|rekomendasi.json belum ada"}],
            "is_error": True,
        }
    code, out, err = await run_v6_script(
        "scripts/render_lhp.py",
        [
            "--penugasan", str(folder),
            "--rekomendasi-file", str(rekomendasi),
            "--judul", args["judul"],
            "--auditi", args["auditi"],
            "--dasar-permintaan", args["dasar_permintaan"],
            "--gambaran-umum", args["gambaran_umum"],
            "--tanggal-exit-meeting", args["tanggal_exit_meeting"],
        ],
        timeout=120,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:400]}"}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": f"OK|{out[:200]}"}]}


@tool(
    "render_lhr_pbj",
    "Render LHR Reviu Pengadaan via scripts/reviu-pengadaan/run_batch.py V6 mode KT.",
    {
        "penugasan_folder": str,
        "context_path": str,
    },
)
async def render_lhr_pbj(args: dict) -> dict:
    code, out, err = await run_v6_script(
        "scripts/reviu-pengadaan/run_batch.py",
        [
            "--penugasan", args["penugasan_folder"],
            "--role", "KT",
            "--context", args["context_path"],
        ],
        timeout=180,
    )
    if code != 0:
        return {
            "content": [{"type": "text", "text": f"FAILED|exit={code}|err={err[:400]}"}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": f"OK|{out[:200]}"}]}


@tool(
    "request_qc_lhp",
    "Trigger Agen QC SAIPI stage LHP.",
    {"penugasan_folder": str},
)
async def request_qc_lhp(args: dict) -> dict:
    marker = Path(args["penugasan_folder"]) / "_QA-SAIPI" / "_pending-lhp.flag"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
    return {"content": [{"type": "text", "text": "QC_LHP_REQUESTED"}]}


LHR_TOOLS = [
    read_temuan_json,
    check_completeness,
    write_rekomendasi_json,
    render_lhr_rka,
    render_lhr_pbj,
    request_qc_lhp,
]
