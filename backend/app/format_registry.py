"""Registry profil format laporan per skill.

Tidak semua jenis pengawasan memakai format KKSA (Kondisi-Kriteria-Akibat-
Rekomendasi). Profil menentukan renderer mana yang dipakai:

  - "kksa"   : LHP paradigma reviu (render_lhp.py V6, placeholder {{...}}). Default.
  - "memo"   : Memo Konsultansi (pendapat/saran, tanpa keyakinan) — renderer app.
  - "rb-4dim": Evaluasi RB tabel 4-dimensi per komponen Renaksi — renderer app.

Profil diturunkan dari frontmatter SKILL.md (`format_laporan: ...`) bila ada,
selain itu dari peta default. Folder-driven — tambah field di SKILL.md = ubah profil.
"""
from __future__ import annotations

import re

from app import skills_registry as sreg

VALID_PROFILES = {"kksa", "memo", "rb-4dim"}

# Default bila SKILL.md tak menyebut format_laporan.
_DEFAULT_PROFILE = {
    "konsultansi-umum": "memo",
    "konsultasi-pengadaan": "memo",
    "evaluasi-reformasi-birokrasi": "rb-4dim",
}


def format_profile(skill: str) -> str:
    """Profil format laporan untuk skill. Override via frontmatter `format_laporan`."""
    slug = re.sub(r"[^a-z0-9\-]", "-", str(skill).strip().lower())
    d = sreg.skill_dir(slug)
    if d is not None:
        md = d / "SKILL.md"
        if md.is_file():
            try:
                meta = sreg._parse_frontmatter(md.read_text(encoding="utf-8"))
            except OSError:
                meta = {}
            fmt = str(meta.get("format_laporan", "")).strip().lower()
            if fmt in VALID_PROFILES:
                return fmt
    return _DEFAULT_PROFILE.get(slug, "kksa")
