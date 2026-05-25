"""Tools untuk Agen Ketua Tim: baca temuan, completeness check, render LHR, QC LHP sync.

Schema rekomendasi.json yang dipakai V6 render_lhp.py:

    {
        "T-001": "Rekomendasi tegas untuk perbaikan...",
        "T-002": "...",
        ...
    }

Note: Function `request_qc_lhp` lama (async-flag) DIGANTI dengan `run_qc_lhp`
sync — sama pola dengan `run_qc_kkp` di kkp_tools.py. Pola lama bermasalah:
agen tidak dapat hasil → improvisasi.
"""
import json
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import tool

from app.tools.v6_bridge import qc_summary_counts, run_v6_script, safe_read_json

# Template LHP placeholder-driven, dimiliki app (bukan V6) supaya backend/v6/
# tetap read-only. render_lhp.py V6 menerima override path lewat --template.
_APP_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


@tool(
    "write_sasaran_assignment",
    "Tulis (overwrite) _PKP/sasaran-assignment.json. PAKAI HANYA di mode 'Setup Penugasan' "
    "saat sasaran-assignment masih kosong/draft. Input `sasaran` adalah list of dict dengan "
    "field: sasaran_id (mis. 'S-PBJ-01'), deskripsi, assigned_to (list[str] nama anggota), "
    "langkah_kerja (list[str]), status (default 'AKTIF'). KT primary path tetap via UI form — "
    "tool ini fallback untuk agent-driven setup.",
    {"penugasan_folder": str, "sasaran": list},
)
async def write_sasaran_assignment(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    path = folder / "_PKP" / "sasaran-assignment.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    raw_sasaran = args.get("sasaran", [])
    if not isinstance(raw_sasaran, list):
        return {
            "content": [{"type": "text", "text": "FAILED|sasaran harus list of dict"}],
            "is_error": True,
        }

    # Normalize + validasi
    sasaran_clean: list[dict] = []
    seen_ids: set[str] = set()
    for s in raw_sasaran:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("sasaran_id", "")).strip()
        if not sid:
            continue
        if sid in seen_ids:
            return {
                "content": [{"type": "text", "text": f"FAILED|sasaran_id duplikat: {sid}"}],
                "is_error": True,
            }
        seen_ids.add(sid)
        assigned = s.get("assigned_to", [])
        if isinstance(assigned, str):
            assigned = [assigned]
        langkah = s.get("langkah_kerja", [])
        if isinstance(langkah, str):
            langkah = [langkah]
        sasaran_clean.append({
            "sasaran_id": sid,
            "deskripsi": str(s.get("deskripsi", "")).strip(),
            "assigned_to": [str(x).strip() for x in assigned if str(x).strip()],
            "langkah_kerja": [str(x).strip() for x in langkah if str(x).strip()],
            "status": str(s.get("status", "AKTIF")).strip() or "AKTIF",
        })

    # Preserve existing envelope kalau file sudah ada, supaya penugasan_id/skill tidak hilang
    existing = safe_read_json(path) if path.exists() else {}
    data = {
        "penugasan_id": existing.get("penugasan_id", folder.name),
        "skill": existing.get("skill", ""),
        "schema_version": "v4.0.0",
        "tanggal_dibuat": datetime.utcnow().isoformat() + "Z",
        "sasaran": sasaran_clean,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "content": [{
            "type": "text",
            "text": f"OK|total_sasaran={len(sasaran_clean)}|path={path.name}",
        }]
    }


@tool(
    "read_temuan_json",
    "Baca _KKP/temuan.json penugasan. Return JSON lengkap dengan envelope penugasan + array temuan.",
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
    "Pastikan semua sasaran di sasaran-assignment.json sudah DISETUJUI_KT (sudah di-approve "
    "oleh Ketua Tim). Kalau ada yang masih AKTIF (belum ada temuan) atau SELESAI_KKP "
    "(sudah ada temuan tapi belum approve), STOP — minta KT approve dulu lewat UI Setup.",
    {"penugasan_folder": str},
)
async def check_completeness(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    assignment = safe_read_json(folder / "_PKP" / "sasaran-assignment.json")
    sasaran_list = assignment.get("sasaran", []) if isinstance(assignment, dict) else []

    # Approved statuses yang siap LHR
    APPROVED = {"DISETUJUI_KT"}

    belum = [s for s in sasaran_list if s.get("status") not in APPROVED]
    if belum:
        text = "BELUM_LENGKAP|sasaran_belum=" + json.dumps(
            [
                {
                    "id": s.get("sasaran_id"),
                    "status_current": s.get("status"),
                    "assigned_to": s.get("assigned_to"),
                }
                for s in belum
            ],
            ensure_ascii=False,
        )
        return {"content": [{"type": "text", "text": text}], "is_error": False}
    return {
        "content": [{
            "type": "text",
            "text": f"OK|total_sasaran={len(sasaran_list)}|all_disetujui_kt=true"
        }]
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
    "Render LHR Reviu RKA-K/L via scripts/render_lhp.py V6. Butuh _LHP/rekomendasi.json sudah ada.",
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
    template = _APP_TEMPLATE_DIR / "template-lhp-reviu-rka-kl.docx"
    if not template.exists():
        return {
            "content": [{"type": "text", "text": f"FAILED|template LHP tidak ada: {template}"}],
            "is_error": True,
        }
    code, out, err = await run_v6_script(
        "scripts/render_lhp.py",
        [
            "--penugasan", str(folder),
            "--rekomendasi-file", str(rekomendasi),
            "--template", str(template),
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
    "Render LHR Reviu Pengadaan via scripts/reviu-pengadaan/run_batch.py V6 mode KT. "
    "Script baca context.md dan _LHP/rekomendasi.json dari folder penugasan.",
    {"penugasan_folder": str},
)
async def render_lhr_pbj(args: dict) -> dict:
    """Note: V6 reviu-pengadaan/run_batch.py supports only --penugasan, --input-dir,
    --render, --role. Tidak ada --context (KT baca context.md langsung dari folder).
    --render WAJIB untuk trigger LHR generation (default OFF).
    """
    code, out, err = await run_v6_script(
        "scripts/reviu-pengadaan/run_batch.py",
        [
            "--penugasan", args["penugasan_folder"],
            "--role", "KT",
            "--render",
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
    "run_qc_lhp",
    "Jalankan QC SAIPI stage LHP secara SYNCHRONOUS. Memanggil scripts/qc_saipi.py "
    "V6 dengan --stage lhp lalu return status + breakdown severity + excerpt laporan. "
    "Pakai SETELAH render_lhr selesai untuk gate kepatuhan SAIPI tahap pelaporan.",
    {"penugasan_folder": str},
)
async def run_qc_lhp(args: dict) -> dict:
    """Sync version dari QC LHP — ganti pola async marker-flag yang lama
    (`request_qc_lhp` writer flag). Pola lama bermasalah: agen yang memanggilnya
    tidak dapat hasil → improvisasi sendiri.
    """
    folder = Path(args["penugasan_folder"])
    if not folder.exists():
        return {
            "content": [{
                "type": "text",
                "text": f"FAILED|folder penugasan tidak ada: {folder} — cek path (typo?), jangan anggap PASS",
            }],
            "is_error": True,
        }
    code, out, err = await run_v6_script(
        "scripts/qc_saipi.py",
        ["--penugasan", str(folder), "--stage", "lhp"],
        timeout=120,
    )

    checklist = safe_read_json(folder / "_QA-SAIPI" / "checklist-lhp.json")
    total_kritis, total_peringatan, total_needs_review, total_ok = qc_summary_counts(checklist)

    if total_kritis > 0:
        status_label = "BLOCKED_KRITIS"
    elif total_peringatan > 0 or total_needs_review > 0:
        status_label = "PASS_WITH_WARNINGS"
    else:
        status_label = "PASS"

    laporan_path = folder / "_QA-SAIPI" / "laporan-qa-lhp.md"
    laporan_excerpt = ""
    if laporan_path.exists():
        laporan_excerpt = laporan_path.read_text(encoding="utf-8")[:4000]

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"stage=lhp|status={status_label}|exit_code={code}|"
                    f"kritis={total_kritis}|peringatan={total_peringatan}|"
                    f"needs_review={total_needs_review}|ok={total_ok}|"
                    f"laporan_path={laporan_path}\n\n"
                    f"=== LAPORAN QA (excerpt) ===\n{laporan_excerpt}"
                ),
            }
        ]
    }


LHR_TOOLS = [
    write_sasaran_assignment,  # Setup Penugasan mode
    read_temuan_json,
    check_completeness,
    write_rekomendasi_json,
    render_lhr_rka,
    render_lhr_pbj,
    run_qc_lhp,
]
