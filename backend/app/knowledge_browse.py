"""Knowledge Management — helpers untuk browser pattern temuan & template setup.

Dipakai oleh:
- routes/knowledge.py — endpoint GET /knowledge/patterns/library (concern 1: browser)
- routes/penugasan.py — endpoint GET /penugasan/{id}/sasaran/templates (concern 2: template)

Pure-Python (no LLM). Aman dipanggil tanpa session — read-only ke `wiki/temuan-patterns/`
+ vault `llm-wiki/wiki/` + folder penugasan historis.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.tools.wiki_tools import (
    _available_skills,
    _parse_frontmatter,
    _patterns_dir,
    _scan_pattern_files,
)

settings = get_settings()


# ---------------------------------------------------------------------------
# Concern 1 — Pattern Library Browser
# ---------------------------------------------------------------------------

def list_pattern_library(
    skill: str | None = None,
    severity: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """List semua pattern temuan terkurasi, dengan filter opsional.

    Tanpa filter: kembalikan semua pattern di `wiki/temuan-patterns/<skill>/`
    cross-skill. Filter cocok untuk UI dropdown + search. `search` mencari
    di id/judul/kategori/kriteria_baku/tags (case-insensitive, substring).

    Return:
        {
          "skills_available": [...],
          "severities_available": [...],
          "categories_available": [...],
          "total_all": int,         # total tanpa filter (untuk badge "X / Y")
          "total_filtered": int,
          "items": [{id, skill, kategori, severity, judul, kriteria_baku,
                     tags[], file}, ...]
        }
    """
    skills = _available_skills()
    items: list[dict] = []
    severities_set: set[str] = set()
    categories_set: set[str] = set()

    target_skills = [skill] if skill else skills
    total_all = 0
    for sk in target_skills:
        files = _scan_pattern_files(sk)
        total_all += len(files)
        for f in files:
            if f.name.startswith("._"):  # skip macOS AppleDouble shadow files
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta, _body = _parse_frontmatter(content)
            sev = str(meta.get("severity", "")).upper()
            kat = str(meta.get("kategori", ""))
            if sev:
                severities_set.add(sev)
            if kat:
                categories_set.add(kat)
            items.append({
                "id": meta.get("id", f.stem),
                "skill": sk,
                "kategori": kat,
                "severity": sev,
                "judul": meta.get("judul", ""),
                "kriteria_baku": meta.get("kriteria_baku", ""),
                "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
                "file": str(f.relative_to(settings.wiki_path)),
            })

    # Hitung agregat sebelum filter ekstra (severity/search)
    if not skill:
        total_all = sum(len(_scan_pattern_files(s)) for s in skills)

    filtered = items
    if severity:
        sev_upper = severity.upper()
        filtered = [it for it in filtered if it["severity"] == sev_upper]
    if search:
        q = search.lower().strip()
        if q:
            def hit(it: dict) -> bool:
                hay = " ".join([
                    str(it.get("id", "")),
                    str(it.get("judul", "")),
                    str(it.get("kategori", "")),
                    str(it.get("kriteria_baku", "")),
                    " ".join(str(t) for t in it.get("tags", [])),
                ]).lower()
                return q in hay
            filtered = [it for it in filtered if hit(it)]

    # Sort: skill asc, severity (CRITICAL > HIGH > MEDIUM > LOW > kosong), id asc
    sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 9}
    filtered.sort(key=lambda it: (it["skill"], sev_rank.get(it["severity"], 9), it["id"]))

    return {
        "skills_available": skills,
        "severities_available": sorted(severities_set, key=lambda s: sev_rank.get(s, 9)),
        "categories_available": sorted(categories_set),
        "total_all": total_all,
        "total_filtered": len(filtered),
        "items": filtered,
    }


def get_pattern_full(pattern_id: str) -> dict[str, Any] | None:
    """Cari pattern by ID lintas semua skill folder. Return metadata + body
    markdown. None bila tidak ketemu.
    """
    pid = pattern_id.strip()
    if not pid:
        return None
    base = settings.wiki_path / "temuan-patterns"
    if not base.exists():
        return None
    for skill_dir in base.iterdir():
        if not skill_dir.is_dir():
            continue
        for f in skill_dir.glob("*.md"):
            if f.name.lower() == "readme.md" or f.name.startswith("._"):
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            meta, body = _parse_frontmatter(content)
            if str(meta.get("id", f.stem)).strip() == pid:
                return {
                    "id": meta.get("id", f.stem),
                    "skill": skill_dir.name,
                    "kategori": meta.get("kategori", ""),
                    "severity": str(meta.get("severity", "")).upper(),
                    "judul": meta.get("judul", ""),
                    "kriteria_baku": meta.get("kriteria_baku", ""),
                    "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
                    "file": str(f.relative_to(settings.wiki_path)),
                    "body_md": body,
                }
    return None


# ---------------------------------------------------------------------------
# Concern 2 — Template Setup Penugasan
# ---------------------------------------------------------------------------

# Stopwords ID umum yg bukan pembeda obyek penugasan
_ID_STOPWORDS = {
    "dan", "atau", "atas", "di", "ke", "dari", "untuk", "yang", "dengan",
    "pada", "oleh", "dalam", "ini", "itu", "akan", "telah", "sudah",
    "ta", "tahun", "anggaran", "periode", "tahap", "fase",
    "kementerian", "kemkomdigi", "komdigi", "kominfo",
    "ditjen", "direktorat", "dit", "sub", "satker", "satuan", "kerja", "unit",
    "the", "of", "a",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Tokenize lowercase + buang stopwords + min len 3 chars."""
    if not text:
        return set()
    tokens = _WORD_RE.findall(text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _ID_STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity. 0 bila salah satu kosong."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def suggest_templates_from_history(
    skill: str,
    obyek: str,
    *,
    candidates: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """Cari penugasan historis v7 dgn skill sama + obyek similar.

    Args:
        skill: skill penugasan target (mis. 'reviu-pengadaan')
        obyek: obyek penugasan target (string)
        candidates: list dict {kode, obyek, skill, folder_path, status}
                    dari DB (caller yg query supaya modul ini pure).
        top_n: maks. berapa kandidat dikembalikan.

    Return list dict siap-pakai untuk UI:
        [{kode, obyek, similarity, total_sasaran, sasaran[...]}]
    """
    target_tokens = _tokenize(obyek)
    out: list[dict] = []
    for c in candidates:
        if c.get("skill") != skill:
            continue
        folder = c.get("folder_path")
        if not folder:
            continue
        sa_path = Path(folder) / "_PKP" / "sasaran-assignment.json"
        if not sa_path.exists():
            continue
        try:
            sa = json.loads(sa_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        sasaran = sa.get("sasaran") or []
        if not sasaran:
            continue
        cand_tokens = _tokenize(c.get("obyek", ""))
        score = _jaccard(target_tokens, cand_tokens)
        # Toleran skema lama (`id`/`nama`) maupun baru (`sasaran_id`/`deskripsi`).
        normalized_sasaran = []
        for s in sasaran:
            normalized_sasaran.append({
                "sasaran_id": str(s.get("sasaran_id") or s.get("id") or "").strip(),
                "deskripsi": str(s.get("deskripsi") or s.get("nama") or "").strip(),
                "assigned_to": s.get("assigned_to", []) if isinstance(s.get("assigned_to"), list) else [],
                "langkah_kerja": s.get("langkah_kerja", []) if isinstance(s.get("langkah_kerja"), list) else [],
            })
        out.append({
            "kode": c.get("kode"),
            "obyek": c.get("obyek"),
            "skill": c.get("skill"),
            "status": c.get("status"),
            "similarity": round(score, 3),
            "total_sasaran": len(sasaran),
            "sasaran": normalized_sasaran,
        })
    # Sort by similarity desc, then total_sasaran desc
    out.sort(key=lambda x: (-x["similarity"], -x["total_sasaran"]))
    return out[:top_n]


def _skill_prefix_for_id(skill: str) -> str:
    """Lokal: prefix ID sasaran per skill (sama dgn endpoint SIMWAS sync)."""
    mapping = {
        "reviu-rka-kl": "RKA",
        "reviu-pengadaan": "PBJ",
        "audit-kinerja": "KIN",
        "audit-pengadaan": "PBJ",
        "pemantauan-pengadaan": "PBJ",
        "pemantauan-tindak-lanjut": "TL",
        "evaluasi-spip": "SPIP",
        "evaluasi-sakip": "SAKIP",
        "evaluasi-manajemen-risiko": "MR",
        "evaluasi-reformasi-birokrasi": "RB",
        "kepatuhan-saipi": "SAIPI",
        "konsultasi-pengadaan": "KONS",
    }
    return mapping.get(skill, "")


def suggest_skeleton_from_patterns(skill: str) -> dict[str, Any]:
    """Bangun sasaran skeleton dari kategori pattern wiki — 1 sasaran per
    kategori dominan, langkah_kerja merefer ke ID pattern dalam kategori itu.

    Return:
        {
          "skill": ...,
          "total_patterns": int,
          "sasaran": [
              {sasaran_id, deskripsi, langkah_kerja, assigned_to=[],
               pattern_ids: [...], kategori}
          ]
        }
    """
    files = _scan_pattern_files(skill)
    by_cat: dict[str, list[dict]] = {}
    for f in files:
        if f.name.startswith("._"):  # skip macOS AppleDouble shadow files
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        meta, _ = _parse_frontmatter(content)
        kat = str(meta.get("kategori", "")).strip() or "LAIN"
        by_cat.setdefault(kat, []).append({
            "id": str(meta.get("id", f.stem)),
            "judul": str(meta.get("judul", "")),
            "severity": str(meta.get("severity", "")).upper(),
        })

    prefix = _skill_prefix_for_id(skill)
    sev_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 9}
    sasaran_out: list[dict] = []
    counter = 1
    # urut kategori dari yg paling banyak pattern-nya (proxy "tema dominan")
    cats_sorted = sorted(by_cat.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for kat, patterns in cats_sorted:
        # Sort pattern dalam kategori by severity, ambil maks 5 untuk langkah
        patterns.sort(key=lambda p: (sev_rank.get(p["severity"], 9), p["id"]))
        top_patterns = patterns[:5]
        sid = f"S-{prefix}-{counter:02d}" if prefix else f"S-{counter:02d}"
        counter += 1
        # Deskripsi sasaran = kategori dibersihkan (drop prefix skill)
        clean_kat = re.sub(r"^(PBJ|RKA|SPIP|SAKIP|RB|KIN|MR|TL|SAIPI|KONS)-", "", kat)
        clean_kat = clean_kat.replace("-", " ").title() or kat
        langkah = [
            f"Verifikasi sesuai pattern {p['id']}: {p['judul'] or '(tanpa judul)'}"
            for p in top_patterns
        ]
        sasaran_out.append({
            "sasaran_id": sid,
            "deskripsi": f"Kelengkapan & kewajaran aspek {clean_kat}",
            "langkah_kerja": langkah,
            "assigned_to": [],
            "kategori": kat,
            "pattern_ids": [p["id"] for p in top_patterns],
        })

    return {
        "skill": skill,
        "total_patterns": len(files),
        "sasaran": sasaran_out,
    }


# ---------------------------------------------------------------------------
# Concern 2c — context dari catatan W3 writeback di vault
# ---------------------------------------------------------------------------

def suggest_context_from_writeback(
    skill: str,
    obyek: str,
    *,
    top_n: int = 5,
) -> list[dict]:
    """Cari `pengawasan-*.md` di vault llm-wiki/wiki/ yg related dgn skill +
    obyek target. Catatan ini hasil W3 tulis-balik — berisi temuan + rekomendasi,
    BUKAN sasaran. Jadi ini di-suggest sbg **konteks pembelajaran** (auditor
    baca dulu temuan apa yg sering muncul), bukan template langsung.

    Return list:
        [{nama_file, judul, skill, jumlah_temuan, similarity}]
    """
    vault_root = settings.vault_path
    if vault_root is None:
        return []
    notes_dir = vault_root / "wiki"
    if not notes_dir.exists():
        return []
    target_tokens = _tokenize(obyek)
    out: list[dict] = []
    for f in notes_dir.glob("pengawasan-*.md"):
        if f.name.startswith("._"):
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Pull "Jenis pengawasan" + judul + total temuan dari format Karpathy W3
        title_match = re.search(r"^#\s+(.+?)$", content, re.MULTILINE)
        judul = title_match.group(1).strip() if title_match else f.stem
        skill_match = re.search(
            r"^\|\s*Jenis pengawasan\s*\|\s*(.+?)\s*\|", content, re.MULTILINE,
        )
        note_skill = skill_match.group(1).strip() if skill_match else ""
        obyek_match = re.search(
            r"^\|\s*Obyek\s*\|\s*(.+?)\s*\|", content, re.MULTILINE,
        )
        note_obyek = obyek_match.group(1).strip() if obyek_match else ""
        n_temuan = len(re.findall(r"^###\s+T-\d+\s+—", content, re.MULTILINE))
        # Skill match: longgar — match string mengandung skill atau sebaliknya
        skill_hit = False
        if skill and note_skill:
            ns = note_skill.lower().replace("/", "-").replace(" ", "-")
            skill_hit = skill in ns or ns in skill
        if not skill_hit:
            continue
        cand_tokens = _tokenize(note_obyek or judul)
        score = _jaccard(target_tokens, cand_tokens)
        out.append({
            "nama_file": f.name,
            "judul": judul,
            "skill_label": note_skill,
            "obyek": note_obyek,
            "jumlah_temuan": n_temuan,
            "similarity": round(score, 3),
        })
    out.sort(key=lambda x: (-x["similarity"], -x["jumlah_temuan"]))
    return out[:top_n]
