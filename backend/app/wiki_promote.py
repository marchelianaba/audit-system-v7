"""W2 — Promosi pattern: dari feedback agen jadi pattern wiki resmi.

Loop perbaikan: agen mengusulkan pattern lewat `pattern_suggestions` di
`_FEEDBACK-AGEN/*.json` (lihat app.tools.feedback_tools). Usulan yang BERULANG
lintas penugasan adalah kandidat kuat untuk dijadikan pattern terkurasi di
`wiki/temuan-patterns/{skill}/`. Modul ini:

1. `aggregate_pattern_suggestions(...)` — kelompokkan usulan pattern lintas
   penugasan (per judul ter-normalisasi), beri atribusi skill/obyek dari
   penugasan asal, dan tandai usulan yang ID/judulnya SUDAH ada di wiki.
2. `promote_pattern(...)` — tulis satu file pattern `.md` ke folder skill
   (frontmatter sesuai format wiki existing), anti-dup ID, validasi skill via
   registry. Best-effort append baris ke README index skill.

Human-in-the-loop: agregasi hanya menyajikan kandidat; auditor PT/PM yang
memutuskan + menyunting isi sebelum promote. V6 tetap read-only — ini menulis
ke folder wiki proyek, bukan ke V6.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from app import skills_registry as sreg
from app.config import get_settings
from app.tools.wiki_tools import _parse_frontmatter

VALID_SEVERITY = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


def _patterns_base() -> Path:
    return get_settings().wiki_path / "temuan-patterns"


def _slug(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s-]", "", str(text).lower().strip())
    return re.sub(r"[\s_-]+", "-", text).strip("-")


def _norm_judul(judul: str) -> str:
    return re.sub(r"\s+", " ", str(judul or "").strip().lower())


def _sanitize_id(pattern_id: str) -> str:
    """ID pattern aman dipakai sebagai nama file: huruf besar, hanya [A-Z0-9-]."""
    pid = re.sub(r"[^A-Z0-9-]", "", str(pattern_id or "").upper().strip())
    return pid.strip("-")


def _quote_yaml(value: str) -> str:
    """Bungkus nilai frontmatter dalam kutip ganda, escape kutip di dalamnya."""
    return '"' + str(value or "").replace('"', "'").strip() + '"'


# =============================================================================
# Index pattern existing (untuk flag already_exists + anti-dup)
# =============================================================================

def _existing_patterns() -> dict[str, dict]:
    """Index semua pattern existing: {id_upper: {skill, judul, judul_norm, file}}.

    Plus key tambahan 'by_judul' di-handle terpisah oleh pemanggil. Di sini
    cukup kembalikan map by-id; pemanggil derive set judul ter-normalisasi.
    """
    base = _patterns_base()
    out: dict[str, dict] = {}
    if not base.exists():
        return out
    for skill_dir in base.iterdir():
        if not skill_dir.is_dir():
            continue
        for f in skill_dir.glob("*.md"):
            if f.name.lower() == "readme.md" or f.name.startswith("._"):
                continue
            try:
                meta, _ = _parse_frontmatter(f.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            pid = str(meta.get("id", f.stem)).upper().strip()
            if not pid:
                continue
            out[pid] = {
                "skill": str(meta.get("skill", skill_dir.name)),
                "judul": str(meta.get("judul", "")),
                "judul_norm": _norm_judul(meta.get("judul", "")),
                "file": str(f.relative_to(get_settings().wiki_path)),
            }
    return out


def _existing_judul_index(existing: dict[str, dict]) -> dict[str, str]:
    """Map judul_norm → id, dari index pattern existing."""
    out: dict[str, str] = {}
    for pid, meta in existing.items():
        jn = meta.get("judul_norm")
        if jn:
            out.setdefault(jn, pid)
    return out


# =============================================================================
# Agregasi usulan pattern dari feedback
# =============================================================================

def aggregate_pattern_suggestions(
    feedback_rows: list[dict],
    folder_meta: dict[str, dict],
) -> dict:
    """Kelompokkan `pattern_suggestions` lintas feedback jadi kandidat promosi.

    Args:
        feedback_rows: hasil _collect_feedback (tiap row punya `_penugasan_folder`
            + array `pattern_suggestions`/`substansi_issues`).
        folder_meta: {folder_name: {"skill": str, "obyek": str}} — atribusi
            penugasan asal supaya kandidat bisa diarahkan ke folder skill yg tepat.

    Return:
        {
          "total_suggestions": int,   # total mentah (sebelum group)
          "candidates": [
            {
              "judul", "id_proposed", "count",
              "rationales": [...],
              "skills": {skill: count},    # dari penugasan asal
              "suggested_skill": str,      # skill terbanyak
              "penugasan": [{folder, obyek, skill}],
              "already_exists": bool,
              "existing_id": str | None,   # ID pattern wiki yg sudah cocok
            }, ...
          ],
          "missed_pattern_issues": [        # sinyal sekunder: substansi missed_pattern
            {"description", "suggested_action", "severity", "penugasan_folder", "skill"}
          ],
        }
    """
    existing = _existing_patterns()
    judul_index = _existing_judul_index(existing)

    groups: dict[str, dict] = {}
    total = 0
    missed: list[dict] = []

    for row in feedback_rows:
        folder = row.get("_penugasan_folder", "")
        meta = folder_meta.get(folder, {})
        skill = str(meta.get("skill", "") or "")
        obyek = str(meta.get("obyek", "") or folder)

        for p in row.get("pattern_suggestions", []) or []:
            judul = str(p.get("judul", "")).strip()
            if not judul:
                continue
            total += 1
            key = _norm_judul(judul)
            g = groups.get(key)
            if g is None:
                g = {
                    "judul": judul,
                    "id_proposed_counter": Counter(),
                    "count": 0,
                    "rationales": [],
                    "skills": Counter(),
                    "penugasan": [],
                    "_pen_seen": set(),
                }
                groups[key] = g
            g["count"] += 1
            idp = str(p.get("id_proposed", "")).strip()
            if idp:
                g["id_proposed_counter"][idp.upper()] += 1
            rationale = str(p.get("rationale", "")).strip()
            if rationale and len(g["rationales"]) < 5 and rationale not in g["rationales"]:
                g["rationales"].append(rationale)
            if skill:
                g["skills"][skill] += 1
            if folder and folder not in g["_pen_seen"]:
                g["_pen_seen"].add(folder)
                g["penugasan"].append({"folder": folder, "obyek": obyek, "skill": skill})

        # Sinyal sekunder: substansi issue kategori missed_pattern.
        for s in row.get("substansi_issues", []) or []:
            if str(s.get("category", "")).lower() != "missed_pattern":
                continue
            desc = str(s.get("description", "")).strip()
            if not desc:
                continue
            missed.append({
                "description": desc[:240],
                "suggested_action": str(s.get("suggested_action", "")).strip()[:240],
                "severity": str(s.get("severity", "")).strip(),
                "penugasan_folder": folder,
                "skill": skill,
            })

    candidates: list[dict] = []
    for key, g in groups.items():
        idp = g["id_proposed_counter"].most_common(1)
        id_proposed = idp[0][0] if idp else ""
        suggested_skill = ""
        if g["skills"]:
            suggested_skill = g["skills"].most_common(1)[0][0]

        # Cocokkan dgn pattern existing: by id_proposed (utama) lalu by judul.
        existing_id = None
        if id_proposed and id_proposed.upper() in existing:
            existing_id = id_proposed.upper()
        elif key in judul_index:
            existing_id = judul_index[key]

        candidates.append({
            "judul": g["judul"],
            "id_proposed": id_proposed,
            "count": g["count"],
            "rationales": g["rationales"],
            "skills": dict(g["skills"]),
            "suggested_skill": suggested_skill,
            "penugasan": g["penugasan"],
            "already_exists": existing_id is not None,
            "existing_id": existing_id,
        })

    # Urut: yg belum ada dulu, lalu frekuensi tertinggi.
    candidates.sort(key=lambda c: (c["already_exists"], -c["count"], c["judul"].lower()))

    return {
        "total_suggestions": total,
        "candidates": candidates,
        "missed_pattern_issues": missed[:20],
    }


# =============================================================================
# Promote — tulis file pattern ke folder skill
# =============================================================================

def _render_pattern_md(
    pattern_id: str,
    skill: str,
    judul: str,
    kategori: str,
    severity: str,
    kriteria_baku: str,
    kondisi: str,
    akibat: str,
    rekomendasi: str,
    bukti: str,
    tags: list[str],
    sumber_penugasan: list[str],
) -> str:
    tags_inline = "[" + ", ".join(tags) + "]" if tags else "[]"
    now = datetime.utcnow().strftime("%Y-%m-%d")
    sumber = ", ".join(sumber_penugasan) if sumber_penugasan else "(usulan feedback agen)"

    lines = [
        "---",
        f"id: {pattern_id}",
        f"skill: {skill}",
        f"kategori: {kategori}",
        f"severity: {severity}",
        f"judul: {_quote_yaml(judul)}",
        f"kriteria_baku: {_quote_yaml(kriteria_baku)}",
        f"tags: {tags_inline}",
        "---",
        "",
        f"# {pattern_id}: {judul}",
        "",
        "## Pattern Kondisi",
        "",
        kondisi.strip() or "_(lengkapi deskripsi kondisi)_",
        "",
        "## Kriteria",
        "",
        kriteria_baku.strip() or "_(sebut pasal/ayat — JANGAN 'peraturan yang berlaku')_",
        "",
        "## Akibat",
        "",
        akibat.strip() or "_(lengkapi akibat/risiko)_",
        "",
        "## Bukti Yang Harus Dicari",
        "",
        bukti.strip() or "_(dokumen + field yang harus diverifikasi)_",
        "",
        "## Rekomendasi",
        "",
        rekomendasi.strip() or "_(rekomendasi standar — opsional)_",
        "",
        "## Catatan",
        "",
        f"Dipromosikan dari feedback agen ({sumber}) pada {now}. "
        "Reviu & lengkapi sitasi sebelum dipakai sebagai rujukan resmi.",
        "",
    ]
    return "\n".join(lines)


def _append_readme_row(skill_dir: Path, pattern_id: str, judul: str,
                       kategori: str, severity: str, kriteria_baku: str) -> bool:
    """Best-effort: sisipkan baris index ke README.md skill. Return True bila sukses.

    Cari tabel index (baris header `| ID |` lalu separator `|---`) dan sisipkan
    baris baru tepat setelah separator. Tidak pernah mengangkat exception —
    README hanya dokumentasi manusia (agen baca file pattern langsung).
    """
    readme = skill_dir / "README.md"
    if not readme.is_file():
        return False
    try:
        lines = readme.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    row = (
        f"| {pattern_id} | {judul} | {kategori} | {severity} | "
        f"{kriteria_baku or '-'} |"
    )
    for i, line in enumerate(lines):
        if line.strip().startswith("| ID ") and i + 1 < len(lines) and re.match(
            r"^\s*\|[-\s|]+\|\s*$", lines[i + 1]
        ):
            lines.insert(i + 2, row)
            try:
                readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return True
            except OSError:
                return False
    return False


def promote_pattern(
    skill: str,
    pattern_id: str,
    judul: str,
    kategori: str = "",
    severity: str = "MEDIUM",
    kriteria_baku: str = "",
    kondisi: str = "",
    akibat: str = "",
    rekomendasi: str = "",
    bukti: str = "",
    tags: list[str] | None = None,
    sumber_penugasan: list[str] | None = None,
) -> dict:
    """Tulis satu pattern ke wiki/temuan-patterns/{skill}/. Return {ok, ...} / {ok:False, error}."""
    skill_slug = sreg._slugify(skill)
    if not sreg.skill_exists(skill_slug):
        return {"ok": False, "error": f"skill '{skill}' tidak terdaftar di registry"}

    pid = _sanitize_id(pattern_id)
    if not pid:
        return {"ok": False, "error": "pattern_id wajib (huruf/angka/dash, mis. 'RP-17')"}

    judul = str(judul or "").strip()
    if not judul:
        return {"ok": False, "error": "judul wajib"}

    sev = str(severity or "MEDIUM").upper().strip()
    if sev not in VALID_SEVERITY:
        return {"ok": False, "error": f"severity '{severity}' tidak valid. Pilih: {sorted(VALID_SEVERITY)}"}

    kategori = str(kategori or "").strip() or "UMUM"

    # Anti-dup: cek ID sudah ada di seluruh wiki.
    existing = _existing_patterns()
    if pid in existing:
        return {
            "ok": False,
            "error": f"pattern ID '{pid}' sudah ada (skill {existing[pid]['skill']}, file {existing[pid]['file']})",
        }

    skill_dir = _patterns_base() / skill_slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    fname = f"{pid}-{_slug(judul)[:60] or 'pattern'}.md"
    target = skill_dir / fname
    if target.exists():
        return {"ok": False, "error": f"file '{fname}' sudah ada"}

    norm_tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
    md = _render_pattern_md(
        pid, skill_slug, judul, kategori, sev, kriteria_baku,
        kondisi, akibat, rekomendasi, bukti, norm_tags, sumber_penugasan or [],
    )
    try:
        target.write_text(md, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": f"gagal tulis file: {e}"}

    readme_updated = _append_readme_row(skill_dir, pid, judul, kategori, sev, kriteria_baku)

    return {
        "ok": True,
        "id": pid,
        "skill": skill_slug,
        "kategori": kategori,
        "severity": sev,
        "file": str(target.relative_to(get_settings().wiki_path)),
        "readme_updated": readme_updated,
    }
