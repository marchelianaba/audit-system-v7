"""Tools feedback retrospective — agen catat refleksi sebelum return ke pengguna.

Output: file JSON di `<penugasan>/_FEEDBACK-AGEN/feedback-{agent}-{ts}.json`.

Tujuan: auditor manusia baca feedback periodik untuk perbaiki:
- WORKFLOW: bug di pipeline V6, scaffolding kurang, tool yang error, ingestion mishap
- SUBSTANSI: anomali rule false positive, area sulit di-verify, pattern wiki yang hilang

Feedback agen TIDAK menggantikan judgment auditor — ini sinyal apa yang agen lihat,
auditor decide actionable atau tidak.

Schema feedback file (v1):

    {
        "schema_version": "v1",
        "agent_name": "anggota_tim" | "ketua_tim" | "qc_saipi" | "ingestion",
        "timestamp": "2026-05-20T10:30:00Z",
        "overall_confidence": "HIGH" | "MEDIUM" | "LOW",
        "summary": "Ringkasan 1-2 kalimat",
        "workflow_issues": [
            {
                "category": "tools|pipeline|scaffolding|data|context",
                "severity": "blocker|major|minor",
                "description": "...",
                "suggested_action": "..."
            }
        ],
        "substansi_issues": [
            {
                "category": "false_positive|missed_pattern|ambiguous_data|kriteria_unclear",
                "severity": "blocker|major|minor",
                "description": "...",
                "evidence": "...",
                "suggested_action": "..."
            }
        ],
        "pattern_suggestions": [
            {
                "id_proposed": "RP-XX",
                "judul": "...",
                "rationale": "..."
            }
        ],
        "pkp_assessment": [
            {
                "sasaran_id": "S-01",
                "kememadaian": "MEMADAI|KURANG_MEMADAI|TIDAK_ADA",
                "alasan": "kaitkan ke standar skill, bukan sekadar mengikuti PKP",
                "langkah_tambahan_diusulkan": ["usulan langkah utk KT/PT bila kurang memadai"]
            }
        ],
        "notes_freetext": "..."
    }

Catatan: `pkp_assessment` = penilaian kememadaian PKP per sasaran (apakah langkah kerja
KT sudah memadai dibanding standar skill). Disimpan DI SINI sebagai bahan evaluasi —
bukan artefak/panel terpisah. Auditor & eval harness membaca dari feedback ini.
"""
import json
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import tool


VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
VALID_SEVERITY = {"blocker", "major", "minor"}
VALID_WORKFLOW_CAT = {"tools", "pipeline", "scaffolding", "data", "context"}
VALID_SUBSTANSI_CAT = {"false_positive", "missed_pattern", "ambiguous_data", "kriteria_unclear"}


def _normalize_issues(issues, valid_cats: set[str]) -> list[dict]:
    """Bersihkan + validate array of issue dict."""
    out: list[dict] = []
    if not isinstance(issues, list):
        return out
    for it in issues:
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category", "")).lower()
        sev = str(it.get("severity", "")).lower()
        out.append({
            "category": cat if cat in valid_cats else "other",
            "severity": sev if sev in VALID_SEVERITY else "minor",
            "description": str(it.get("description", "")).strip(),
            "evidence": str(it.get("evidence", "")).strip(),
            "suggested_action": str(it.get("suggested_action", "")).strip(),
        })
    return out


def _normalize_patterns(patterns) -> list[dict]:
    out: list[dict] = []
    if not isinstance(patterns, list):
        return out
    for p in patterns:
        if not isinstance(p, dict):
            continue
        out.append({
            "id_proposed": str(p.get("id_proposed", "")).strip(),
            "judul": str(p.get("judul", "")).strip(),
            "rationale": str(p.get("rationale", "")).strip(),
        })
    return out


VALID_KEMEMADAIAN = {"MEMADAI", "KURANG_MEMADAI", "TIDAK_ADA"}


def _normalize_pkp(items) -> list[dict]:
    """Bersihkan penilaian kememadaian PKP per sasaran (bahan evaluasi)."""
    out: list[dict] = []
    if not isinstance(items, list):
        return out
    for a in items:
        if not isinstance(a, dict):
            continue
        kem = str(a.get("kememadaian", "")).strip().upper().replace(" ", "_").replace("-", "_")
        if kem not in VALID_KEMEMADAIAN:
            kem = "KURANG_MEMADAI"  # default skeptis bila label tak dikenal
        usul = a.get("langkah_tambahan_diusulkan") or []
        if isinstance(usul, str):
            usul = [usul]
        out.append({
            "sasaran_id": str(a.get("sasaran_id", "")).strip(),
            "kememadaian": kem,
            "alasan": str(a.get("alasan", "")).strip(),
            "langkah_tambahan_diusulkan": [str(x).strip() for x in usul if str(x).strip()],
        })
    return out


@tool(
    "submit_feedback",
    "Catat feedback retrospective ke _FEEDBACK-AGEN/feedback-{agent}-{ts}.json. "
    "PANGGIL DI AKHIR session, SEBELUM return ringkasan akhir ke pengguna. "
    "Field: overall_confidence (HIGH/MEDIUM/LOW), summary (1-2 kalimat), "
    "workflow_issues (array of {category, severity, description, suggested_action}), "
    "substansi_issues (array of {category, severity, description, evidence, suggested_action}), "
    "pattern_suggestions (array of {id_proposed, judul, rationale}), "
    "pkp_assessment (array of {sasaran_id, kememadaian: MEMADAI|KURANG_MEMADAI|TIDAK_ADA, alasan, "
    "langkah_tambahan_diusulkan:[str]}) — penilaian kememadaian PKP per sasaran sbg bahan evaluasi, "
    "notes_freetext (catatan bebas).",
    {
        "penugasan_folder": str,
        "agent_name": str,
        "overall_confidence": str,
        "summary": str,
        "workflow_issues": list,
        "substansi_issues": list,
        "pattern_suggestions": list,
        "pkp_assessment": list,
        "notes_freetext": str,
    },
)
async def submit_feedback(args: dict) -> dict:
    folder = Path(args["penugasan_folder"])
    fb_dir = folder / "_FEEDBACK-AGEN"
    fb_dir.mkdir(parents=True, exist_ok=True)

    agent = str(args.get("agent_name", "agent")).strip().replace(" ", "_") or "agent"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = fb_dir / f"feedback-{agent}-{ts}.json"

    confidence = str(args.get("overall_confidence", "MEDIUM")).upper()
    if confidence not in VALID_CONFIDENCE:
        confidence = "MEDIUM"

    data = {
        "schema_version": "v1",
        "agent_name": agent,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "overall_confidence": confidence,
        "summary": str(args.get("summary", "")).strip(),
        "workflow_issues": _normalize_issues(args.get("workflow_issues", []), VALID_WORKFLOW_CAT),
        "substansi_issues": _normalize_issues(args.get("substansi_issues", []), VALID_SUBSTANSI_CAT),
        "pattern_suggestions": _normalize_patterns(args.get("pattern_suggestions", [])),
        "pkp_assessment": _normalize_pkp(args.get("pkp_assessment", [])),
        "notes_freetext": str(args.get("notes_freetext", "")).strip(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Counts untuk return ke agen — biar dia tahu submit-nya berhasil tanpa bloat
    n_wf = len(data["workflow_issues"])
    n_sub = len(data["substansi_issues"])
    n_pat = len(data["pattern_suggestions"])
    n_pkp = len(data["pkp_assessment"])
    n_pkp_kurang = sum(1 for x in data["pkp_assessment"] if x["kememadaian"] != "MEMADAI")
    return {
        "content": [{
            "type": "text",
            "text": (
                f"FEEDBACK_SAVED|path={path.name}|confidence={confidence}|"
                f"workflow_issues={n_wf}|substansi_issues={n_sub}|pattern_suggestions={n_pat}|"
                f"pkp_assessment={n_pkp}(kurang_memadai={n_pkp_kurang})"
            ),
        }]
    }


FEEDBACK_TOOLS = [submit_feedback]
