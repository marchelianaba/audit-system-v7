"""Registry gate — alur evaluasi BERTAHAP (gate-based) folder-driven.

Sebagian skill evaluasi (SPIP/SAKIP/RB) dijalankan tidak dalam satu lintasan,
melainkan **gate demi gate** dengan konfirmasi auditor (LANJUT/KOREKSI/ULANG) di
tiap tahap. Definisi gate diambil dari file `knowledge/tasks/*-bertahap.md`
(APP_TASKS_PATH) — tambah/ubah file = ubah gate, tanpa hardcode.

Format yang diparse di tiap file bertahap:
  - Baris penanda skill induk: `> **Skill induk**: \`<slug>\`` → memetakan file ke skill.
  - Header gate: `## Gate <id> — <judul>` atau `### Gate <id> — <judul>`.
    `<id>` boleh "0","1","4A" (token setelah kata "Gate").
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

_SKILL_INDUK_RE = re.compile(r"Skill\s+induk\*{0,2}\s*:\s*`?([a-z0-9\-]+)`?", re.IGNORECASE)
_GATE_RE = re.compile(r"^#{2,3}\s*Gate\s+(\S+)\s*[—–-]\s*(.+?)\s*$")


def _tasks_dir() -> Path:
    return get_settings().tasks_path


def _parse_gate_file(path: Path) -> dict | None:
    """Parse satu file bertahap → {skill, file, gates:[{id, judul}]}. None bila
    tidak menyebut skill induk atau tak punya gate."""
    # Skip macOS AppleDouble shadow files (._*) — binary, bukan UTF-8
    if path.name.startswith("._"):
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    skill = None
    gates: list[dict] = []
    for line in text.splitlines():
        if skill is None:
            m = _SKILL_INDUK_RE.search(line)
            if m:
                skill = m.group(1).strip().lower()
        gm = _GATE_RE.match(line)
        if gm:
            gates.append({"id": gm.group(1).strip(), "judul": gm.group(2).strip()})
    if not skill or not gates:
        return None
    return {"skill": skill, "file": path.name, "gates": gates}


@lru_cache(maxsize=1)
def _scan() -> dict[str, dict]:
    """Scan APP_TASKS_PATH untuk *-bertahap.md → {skill: spec}. Cached."""
    base = _tasks_dir()
    out: dict[str, dict] = {}
    if base.exists():
        for f in sorted(base.glob("*-bertahap.md")):
            spec = _parse_gate_file(f)
            if spec:
                out[spec["skill"]] = spec
    return out


def refresh() -> None:
    _scan.cache_clear()


def skill_has_gates(skill: str) -> bool:
    return str(skill).strip().lower() in _scan()


def gated_skills() -> list[str]:
    return sorted(_scan().keys())


def list_gates(skill: str) -> list[dict]:
    """Daftar gate untuk skill (atau [] bila bukan skill bertahap)."""
    spec = _scan().get(str(skill).strip().lower())
    return list(spec["gates"]) if spec else []


def gate_ids(skill: str) -> list[str]:
    return [g["id"] for g in list_gates(skill)]


def gate_section(skill: str, gate_id: str) -> str | None:
    """Ambil teks markdown SATU gate (dari header gate sampai sebelum gate
    berikutnya) untuk instruksi agen. None bila tak ada."""
    spec = _scan().get(str(skill).strip().lower())
    if not spec:
        return None
    path = _tasks_dir() / spec["file"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    want = str(gate_id).strip().upper()
    start = None
    for i, line in enumerate(lines):
        gm = _GATE_RE.match(line)
        if gm and gm.group(1).strip().upper() == want:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _GATE_RE.match(lines[j]):
            end = j
            break
    return "\n".join(lines[start:end]).strip()
