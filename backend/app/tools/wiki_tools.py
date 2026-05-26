"""Tools wiki — agen akses pattern temuan + konteks dari knowledge base auditor.

Folder wiki/ berisi pattern temuan + konteks pendukung (pola-berulang, glossary,
regulasi). Struktur (folder-driven — 1 subfolder = 1 skill spesifik):

    wiki/
    ├── temuan-patterns/
    │   ├── <skill>/                    # 1 folder per skill spesifik
    │   │   ├── README.md               # index pattern skill itu
    │   │   └── <ID>-<slug>.md          # mis. RP-08-..., RKA-01-..., ESP-35-...
    │   └── ...                         # 12 skill: audit-kinerja, audit-pengadaan,
    │       # evaluasi-{spip,sakip,manajemen-risiko,reformasi-birokrasi},
    │       # kepatuhan-saipi, konsultasi-pengadaan, pemantauan-{pengadaan,tindak-lanjut},
    │       # reviu-pengadaan, reviu-rka-kl  (~65 pattern total)
    └── konteks/
        ├── README.md
        ├── pola-temuan-berulang.md    (id KONTEKS-POLA-BERULANG)
        ├── glossary-komdigi.md         (id KONTEKS-GLOSSARY)
        └── regulasi-kunci.md           (id KONTEKS-REGULASI)

Skill *-umum (audit/reviu/pemantauan/evaluasi/konsultansi-umum) sengaja TIDAK
punya folder pattern — bersifat criteria-driven (kriteria diunggah auditor saat
penugasan), bukan dari pustaka pattern. `_available_skills()` menurunkan daftar
skill dari folder yang ADA, jadi menambah folder = menambah skill (tanpa ubah kode).

Setiap file pattern punya YAML frontmatter (id, skill, kategori, severity,
judul, kriteria_baku, tags) lalu body markdown.
Setiap file konteks punya YAML frontmatter (id, kategori=konteks, judul, sumber,
tanggal_update, tags) lalu body markdown.

Path resolusi via env var APP_WIKI_PATH (lihat config.py).
"""
import json
import re
from pathlib import Path

from claude_agent_sdk import tool

from app.config import get_settings

settings = get_settings()


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter sederhana di awal file.

    Format:
        ---
        key: value
        list: [a, b, c]
        ---
        body markdown...

    Return (metadata_dict, body_str). Kalau tidak ada frontmatter, return ({}, content).
    Parser ini sederhana — tidak butuh dep tambahan PyYAML.
    """
    if not content.startswith("---"):
        return {}, content

    # Cari closing ---
    end_match = re.search(r"^---\s*$", content[3:], re.MULTILINE)
    if not end_match:
        return {}, content

    fm_text = content[3 : end_match.start() + 3].strip()
    body = content[end_match.end() + 3:].lstrip("\n")

    metadata: dict = {}
    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        key, raw_value = m.group(1), m.group(2).strip()

        # Strip quotes
        if (raw_value.startswith('"') and raw_value.endswith('"')) or (
            raw_value.startswith("'") and raw_value.endswith("'")
        ):
            metadata[key] = raw_value[1:-1]
            continue

        # List inline [a, b, c]
        if raw_value.startswith("[") and raw_value.endswith("]"):
            inner = raw_value[1:-1].strip()
            items = [it.strip().strip('"').strip("'") for it in inner.split(",") if it.strip()]
            metadata[key] = items
            continue

        metadata[key] = raw_value

    return metadata, body


def _patterns_dir(skill: str) -> Path:
    """Folder pattern untuk skill tertentu. Skill di-slugify untuk safety."""
    skill_slug = re.sub(r"[^a-zA-Z0-9\-]", "-", skill.lower())
    return settings.wiki_path / "temuan-patterns" / skill_slug


def _scan_pattern_files(skill: str) -> list[Path]:
    """List semua .md di folder skill (kecuali README.md)."""
    folder = _patterns_dir(skill)
    if not folder.exists():
        return []
    return sorted([p for p in folder.glob("*.md") if p.name.lower() != "readme.md"])


def _available_skills() -> list[str]:
    """Daftar skill yang punya folder pattern (turunan dari isi folder, bukan
    hardcode) — tambah folder = tambah skill, tanpa ubah kode."""
    base = settings.wiki_path / "temuan-patterns"
    if not base.exists():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir())


@tool(
    "list_temuan_patterns",
    "Daftar semua pattern temuan dari wiki untuk skill tertentu. "
    "Return list ringkas {id, judul, kategori, severity, tags} per pattern. "
    "Pakai SEBELUM susun temuan substantif supaya kamu tahu pattern apa yang sudah "
    "ada di knowledge base tim. Untuk baca detail pattern, panggil `get_temuan_pattern`.",
    {"skill": str},
)
async def list_temuan_patterns(args: dict) -> dict:
    skill = args["skill"].strip().lower()
    if not _patterns_dir(skill).exists():
        avail = _available_skills()
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"FAILED|skill='{skill}' belum punya folder pattern. "
                    f"Tersedia: {', '.join(avail) if avail else '(belum ada)'}"
                ),
            }],
            "is_error": True,
        }

    files = _scan_pattern_files(skill)
    if not files:
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"WIKI_KOSONG|skill={skill}|wiki_path={settings.wiki_path}|"
                    f"Belum ada pattern temuan untuk skill ini. "
                    f"Auditor manusia perlu menambahkan file pattern di "
                    f"wiki/temuan-patterns/{skill}/ — lanjutkan tanpa pattern."
                ),
            }]
        }

    summaries: list[dict] = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = _parse_frontmatter(content)
        summaries.append({
            "id": meta.get("id", f.stem),
            "judul": meta.get("judul", ""),
            "kategori": meta.get("kategori", ""),
            "severity": meta.get("severity", ""),
            "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
            "kriteria_baku": meta.get("kriteria_baku", ""),
            "file": str(f.relative_to(settings.wiki_path)),
        })

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(
                {
                    "skill": skill,
                    "total": len(summaries),
                    "patterns": summaries,
                },
                ensure_ascii=False,
            ),
        }]
    }


@tool(
    "get_temuan_pattern",
    "Baca isi LENGKAP satu pattern temuan dari wiki berdasarkan ID (mis. 'RP-08' atau 'RKA-01'). "
    "Return metadata + body markdown. Pakai SETELAH `list_temuan_patterns` untuk dapat detail "
    "pattern yang ingin di-referensikan saat menyusun temuan.",
    {"pattern_id": str},
)
async def get_temuan_pattern(args: dict) -> dict:
    pid = args["pattern_id"].strip()
    if not pid:
        return {
            "content": [{"type": "text", "text": "FAILED|pattern_id kosong"}],
            "is_error": True,
        }

    # Search di semua skill folder
    base = settings.wiki_path / "temuan-patterns"
    if not base.exists():
        return {
            "content": [{
                "type": "text",
                "text": f"FAILED|folder wiki tidak ada: {base}",
            }],
            "is_error": True,
        }

    found: Path | None = None
    found_meta: dict | None = None
    for skill_dir in base.iterdir():
        if not skill_dir.is_dir():
            continue
        for f in skill_dir.glob("*.md"):
            if f.name.lower() == "readme.md":
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _ = _parse_frontmatter(content)
            if meta.get("id") == pid or f.stem.upper().startswith(pid.upper()):
                found = f
                found_meta = meta
                break
        if found:
            break

    if not found:
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"NOT_FOUND|pattern_id={pid}|"
                    f"Coba list_temuan_patterns(skill) untuk lihat ID yang tersedia."
                ),
            }],
            "is_error": True,
        }

    content = found.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(content)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(
                {
                    "pattern_id": meta.get("id", found.stem),
                    "judul": meta.get("judul", ""),
                    "skill": meta.get("skill", ""),
                    "kategori": meta.get("kategori", ""),
                    "severity": meta.get("severity", ""),
                    "kriteria_baku": meta.get("kriteria_baku", ""),
                    "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
                    "file": str(found.relative_to(settings.wiki_path)),
                    "body_markdown": body[:8000],  # cap 8KB supaya context agen tidak meledak
                },
                ensure_ascii=False,
            ),
        }]
    }


# =============================================================================
# KONTEKS — pola temuan berulang, glossary, regulasi kunci
# =============================================================================

# Mapping kategori → nama file di wiki/konteks/. Sengaja whitelist supaya agen
# tidak bisa baca file sembarangan.
_KONTEKS_FILES: dict[str, str] = {
    "pola-berulang": "pola-temuan-berulang.md",
    "glossary": "glossary-komdigi.md",
    "regulasi": "regulasi-kunci.md",
}


def _konteks_dir() -> Path:
    return settings.wiki_path / "konteks"


@tool(
    "list_konteks",
    "Daftar konteks pendukung yang tersedia di knowledge base auditor "
    "(pola temuan berulang, glossary istilah Komdigi, regulasi kunci). "
    "Konteks ini WAJIB DIBACA SEBELUM susun KKP supaya tidak halusinasi "
    "(salah definisi istilah, ngarang sitasi pasal, atau memaksakan pola). "
    "Return list ringkas {kategori, id, judul, file, tanggal_update}.",
    {},
)
async def list_konteks(_args: dict) -> dict:
    folder = _konteks_dir()
    if not folder.exists():
        return {
            "content": [{
                "type": "text",
                "text": (
                    f"KONTEKS_KOSONG|wiki_path={settings.wiki_path}|"
                    f"Folder konteks/ belum ada. Lanjutkan tanpa konteks tapi "
                    f"hati-hati halusinasi (terutama sitasi peraturan)."
                ),
            }]
        }

    items: list[dict] = []
    for kategori, filename in _KONTEKS_FILES.items():
        f = folder / filename
        if not f.exists():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = _parse_frontmatter(content)
        items.append({
            "kategori": kategori,
            "id": meta.get("id", f.stem),
            "judul": meta.get("judul", ""),
            "sumber": meta.get("sumber", ""),
            "tanggal_update": meta.get("tanggal_update", ""),
            "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
            "file": str(f.relative_to(settings.wiki_path)),
        })

    return {
        "content": [{
            "type": "text",
            "text": json.dumps(
                {"total": len(items), "konteks": items},
                ensure_ascii=False,
            ),
        }]
    }


@tool(
    "get_konteks",
    "Baca isi LENGKAP satu konteks pendukung berdasarkan kategori. "
    "Kategori valid: 'pola-berulang' (9 akar masalah lintas LHP/LHR), "
    "'glossary' (definisi akronim + profil vendor mitra), "
    "'regulasi' (pasal baku + kutipan inti — cegah salah sitasi). "
    "Pakai SEBELUM tulis bagian 'kriteria' di temuan untuk pastikan sitasi peraturan benar.",
    {"kategori": str},
)
async def get_konteks(args: dict) -> dict:
    kategori = args["kategori"].strip().lower()
    if kategori not in _KONTEKS_FILES:
        valid = ", ".join(_KONTEKS_FILES.keys())
        return {
            "content": [{
                "type": "text",
                "text": f"FAILED|kategori='{kategori}' tidak valid. Pilih: {valid}",
            }],
            "is_error": True,
        }

    f = _konteks_dir() / _KONTEKS_FILES[kategori]
    if not f.exists():
        return {
            "content": [{
                "type": "text",
                "text": f"NOT_FOUND|file konteks tidak ada: {f}",
            }],
            "is_error": True,
        }

    try:
        content = f.read_text(encoding="utf-8")
    except OSError as e:
        return {
            "content": [{"type": "text", "text": f"FAILED|gagal baca: {e}"}],
            "is_error": True,
        }

    meta, body = _parse_frontmatter(content)
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(
                {
                    "kategori": kategori,
                    "id": meta.get("id", f.stem),
                    "judul": meta.get("judul", ""),
                    "sumber": meta.get("sumber", ""),
                    "tanggal_update": meta.get("tanggal_update", ""),
                    "tags": meta.get("tags", []) if isinstance(meta.get("tags"), list) else [],
                    "file": str(f.relative_to(settings.wiki_path)),
                    "body_markdown": body[:12000],  # cap 12KB — konteks lebih besar dari pattern
                },
                ensure_ascii=False,
            ),
        }]
    }


# =============================================================================
# VAULT — pencarian penuh atas knowledge base Obsidian/Karpathy (read-only)
# =============================================================================
#
# Vault (llm-wiki/) berisi ratusan catatan hasil ingest dokumen resmi non-rahasia
# (profil unit/auditi, riwayat temuan BPK, profil vendor, regulasi, Renja/RKA, dll).
# Berbeda dari `wiki/` proyek yang hanya pattern+konteks terkurasi. Fitur ini
# memberi agen jangkauan baca yang lebih luas saat analisis. Path via APP_VAULT_PATH.

# File meta yang bukan catatan substantif — dikecualikan dari hasil search.
_VAULT_SKIP = {"index.md", "log.md"}


def _vault_notes_dir() -> Path | None:
    """Folder catatan vault (<APP_VAULT_PATH>/wiki/), atau None bila tak dikonfigurasi."""
    base = settings.vault_path
    if base is None:
        return None
    notes = base / "wiki"
    return notes if notes.exists() else None


def _parse_vault_index(notes_dir: Path) -> dict[str, dict]:
    """Parse index.md → {name: {section, summary}} dari baris '- [[name]] — desc'."""
    out: dict[str, dict] = {}
    idx = notes_dir / "index.md"
    if not idx.exists():
        return out
    section = ""
    try:
        text = idx.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("##"):
            section = s.lstrip("#").strip()
            continue
        m = re.match(r"^-\s*\[\[([^\]]+)\]\]\s*[—-]?\s*(.*)$", s)
        if m:
            name = m.group(1).strip()
            out[name] = {"section": section, "summary": m.group(2).strip()}
    return out


def vault_search(query: str, limit: int = 12) -> dict:
    """Cari catatan vault relevan. Index-driven + full-text scoring sederhana.

    Return dict siap-serialize: {configured, total, results:[{name,section,summary,
    path,score,snippet}]}.
    """
    notes_dir = _vault_notes_dir()
    if notes_dir is None:
        return {"configured": False, "total": 0, "results": [],
                "message": "Vault tidak dikonfigurasi (set APP_VAULT_PATH)."}

    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
    if not terms:
        return {"configured": True, "total": 0, "results": [],
                "message": "Query terlalu pendek."}

    index = _parse_vault_index(notes_dir)
    scored: list[dict] = []
    for f in notes_dir.glob("*.md"):
        if f.name.lower() in _VAULT_SKIP:
            continue
        name = f.stem
        try:
            content = f.read_text(encoding="utf-8")[:30000]
        except OSError:
            continue
        name_lc = name.lower()
        meta = index.get(name, {})
        summary = meta.get("summary", "")
        summary_lc = summary.lower()
        content_lc = content.lower()

        score = 0
        for t in terms:
            score += name_lc.count(t) * 4
            score += summary_lc.count(t) * 3
            score += content_lc.count(t)
        if score <= 0:
            continue

        # Snippet: baris pertama (bukan heading/frontmatter) yang memuat salah satu term
        snippet = ""
        for line in content.splitlines():
            ls = line.strip()
            if not ls or ls.startswith("#") or ls.startswith("---"):
                continue
            if any(t in ls.lower() for t in terms):
                snippet = ls[:200]
                break
        scored.append({
            "name": name,
            "section": meta.get("section", ""),
            "summary": summary,
            "path": str(f.relative_to(notes_dir)),
            "score": score,
            "snippet": snippet,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"configured": True, "total": len(scored), "results": scored[: max(1, limit)]}


def vault_get_page(name: str) -> dict:
    """Baca satu catatan vault by name (aman dari path traversal). Return dict."""
    notes_dir = _vault_notes_dir()
    if notes_dir is None:
        return {"found": False, "configured": False,
                "message": "Vault tidak dikonfigurasi (set APP_VAULT_PATH)."}

    # Sanitasi: ambil basename saja, paksa .md
    safe = Path(str(name)).name.strip()
    if not safe:
        return {"found": False, "configured": True, "message": "Nama kosong."}
    if not safe.lower().endswith(".md"):
        safe += ".md"

    target = (notes_dir / safe).resolve()
    notes_resolved = notes_dir.resolve()
    # Pastikan tetap di dalam folder catatan vault
    if notes_resolved not in target.parents or not target.is_file():
        return {"found": False, "configured": True,
                "message": f"Catatan tidak ditemukan: {safe}"}

    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as e:
        return {"found": False, "configured": True, "message": f"Gagal baca: {e}"}

    cap = 16000
    body = raw[:cap]
    return {
        "found": True,
        "configured": True,
        "name": target.stem,
        "path": str(target.relative_to(notes_resolved)),
        "content": body,
        "truncated": len(raw) > cap,
    }


@tool(
    "search_wiki",
    "Cari catatan di vault pengetahuan organisasi (llm-wiki) — ratusan catatan hasil "
    "ingest dokumen resmi: profil unit/auditi, riwayat temuan BPK, profil vendor, "
    "regulasi, Renja/RKA, isu strategis. Pakai SAAT analisis untuk menarik konteks "
    "auditi/vendor/riwayat yang relevan (mis. 'temuan BPK PSTE', 'profil Ditjen Ekosdig', "
    "'vendor X'). Return daftar {name, section, summary, snippet}. Baca isi lengkap via "
    "get_wiki_page(name). Beda dari list_temuan_patterns (pattern terkurasi) — ini jangkauan luas.",
    {"query": str, "limit": int},
)
async def search_wiki(args: dict) -> dict:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"content": [{"type": "text", "text": "FAILED|query kosong"}], "is_error": True}
    try:
        limit = int(args.get("limit", 12))
    except (TypeError, ValueError):
        limit = 12
    res = vault_search(query, limit=limit)
    return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}]}


@tool(
    "get_wiki_page",
    "Baca isi LENGKAP satu catatan vault by name (mis. 'bpk-kinerja-pste-2024' atau "
    "'direktorat-pengembangan-ekosistem-digital'). Pakai SETELAH search_wiki untuk "
    "mendalami catatan yang relevan. Catatan vault memuat sitasi sumber (source: …) — "
    "pakai untuk konteks, tetap verifikasi fakta penugasan saat ini.",
    {"name": str},
)
async def get_wiki_page(args: dict) -> dict:
    res = vault_get_page(str(args.get("name", "")))
    if not res.get("found"):
        return {"content": [{"type": "text", "text": f"NOT_FOUND|{res.get('message', '')}"}]}
    return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}]}


WIKI_TOOLS = [
    list_temuan_patterns,
    get_temuan_pattern,
    list_konteks,
    get_konteks,
    search_wiki,
    get_wiki_page,
]
