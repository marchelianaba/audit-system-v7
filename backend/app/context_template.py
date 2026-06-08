"""Generator DETERMINISTIK untuk `context.md` penugasan.

Sebelumnya context.md disusun penuh oleh agen AT lewat LLM. Sekitar 80% isinya
sebenarnya bisa dirakit langsung dari data yang sudah ada:

  - Identitas penugasan (kode, obyek, skill, nomor ST, tanggal ST) → row DB.
  - Periode/anggaran → DB + ekstrak tahun dari obyek/digest.
  - Tujuan + Ruang Lingkup → template per skill (reviu-rka-kl / reviu-pengadaan).
  - Tim → `_PKP/sasaran-assignment.json`.
  - Ringkasan Obyek (bagian "keras") → digest TOR/RAB/KAK/HPS yang sudah ada
    (kementerian, RO, total anggaran, dasar hukum).

Yang TETAP butuh AI hanyalah "Gambaran Umum" 2-4 kalimat naratif. Modul ini
men-emit placeholder `<!-- AI_PARAGRAPH:gambaran_umum -->` yang akan
di-isi oleh agen di langkah berikutnya (atau dibiarkan untuk auditor isi manual).

Tujuan: hemat ~$0.05/penugasan, lebih konsisten, lebih cepat (~ms).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Template per skill — bahasa baku APIP, sesuai PMK 107/2024 (RKA-K/L) dan
# Perpres 16/2018 jo. 12/2021 (Pengadaan).
# ---------------------------------------------------------------------------

_SKILL_TEMPLATES: dict[str, dict[str, str]] = {
    "reviu-rka-kl": {
        "title_prefix": "RKA-K/L",
        "tujuan": (
            "Memberikan keyakinan terbatas atas kelengkapan dan kewajaran TOR "
            "dan RAB {obyek_singkat} sesuai PMK 107/2024."
        ),
        "ruang_lingkup": (
            "Reviu dokumen TOR dan RAB {obyek_singkat} pada {kementerian_atau_unit}, "
            "Tahun Anggaran {tahun_anggaran}."
        ),
        "fokus": (
            "Reviu difokuskan pada keselarasan substansi TOR (7 blok wajib), "
            "kewajaran komponen RAB terhadap Rincian Output, serta kesesuaian "
            "penandaan dan sumber dana."
        ),
    },
    "reviu-pengadaan": {
        "title_prefix": "Pengadaan",
        "tujuan": (
            "Memberikan keyakinan terbatas atas perencanaan pengadaan {obyek_singkat} "
            "sesuai Perpres 16/2018 jo. Perpres 12/2021 dan SOP UKPBJ."
        ),
        "ruang_lingkup": (
            "Reviu dokumen perencanaan pengadaan {obyek_singkat} pada "
            "{kementerian_atau_unit}, Tahun Anggaran {tahun_anggaran}: KAK, HPS, "
            "RFI/penawaran, dan rancangan kontrak (bila tersedia)."
        ),
        "fokus": (
            "Reviu difokuskan pada kelengkapan KAK (dasar hukum, ruang lingkup, "
            "spesifikasi teknis, jadwal), kewajaran HPS (minimal dua sumber harga "
            "independen sesuai Perpres 16/2018 Pasal 26 ayat 5), serta integritas "
            "vendor RFI (cek afiliasi/alamat sama)."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers — baca digest yang sudah ada
# ---------------------------------------------------------------------------

def _safe_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _collect_digest_summaries(penugasan_folder: Path) -> list[dict]:
    """Ringkas semua digest di `_INGESTED/*.json` via `_summarize_digest`."""
    from app.tools.kkp_tools import _summarize_digest  # late import (circular)

    ingested = penugasan_folder / "_INGESTED"
    if not ingested.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(ingested.glob("*.json")):
        data = _safe_json(p)
        if not isinstance(data, dict):
            continue
        out.append(_summarize_digest(p.name, data))
    return out


def _pick_first(summaries: list[dict], key: str) -> Any:
    """Ambil nilai pertama yang non-empty untuk `key`."""
    for s in summaries:
        v = s.get(key)
        if v not in (None, "", [], 0):
            return v
    return None


def _collect_dasar_hukum(summaries: list[dict], cap: int = 8) -> list[str]:
    """Gabungkan dasar_hukum dari semua summary, dedup, cap."""
    seen: dict[str, None] = {}
    for s in summaries:
        dh = s.get("dasar_hukum")
        if isinstance(dh, list):
            for item in dh:
                key = str(item).strip()
                if key and key not in seen:
                    seen[key] = None
                    if len(seen) >= cap:
                        return list(seen.keys())
    return list(seen.keys())


def _format_rupiah(n: int | float | None) -> str | None:
    if n in (None, 0):
        return None
    try:
        return f"Rp{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return None


def _detect_tahun_anggaran(summaries: list[dict], default: str = "2026") -> str:
    """Cari tahun anggaran dari summary atau obyek; default 2026.

    Cara cari:
      1. Field eksplisit `tahun_anggaran` / `tahun` di summary.
      2. Field `nama_file` yang mengandung "2026"/"2027".
      3. Default ke param default — JANGAN scan seluruh JSON karena
         tahun regulasi (UU 27/2022) sering muncul lebih dulu dan
         akan salah ditebak sebagai tahun anggaran.
    """
    import re
    for s in summaries:
        for k in ("tahun_anggaran", "tahun"):
            v = s.get(k)
            if v and re.match(r"^20\d{2}$", str(v)):
                return str(v)
    # Cari di nama file digest saja (hindari false positive dari dasar_hukum)
    for s in summaries:
        fname = s.get("file", "")
        m = re.search(r"\b(20[2-3]\d)\b", str(fname))
        if m:
            return m.group(1)
    return default


def _load_tim(penugasan_folder: Path) -> list[dict]:
    """Baca `_PKP/sasaran-assignment.json` → list anggota tim."""
    p = penugasan_folder / "_PKP" / "sasaran-assignment.json"
    data = _safe_json(p)
    if not isinstance(data, dict):
        return []
    members = data.get("anggota") or data.get("tim") or []
    return members if isinstance(members, list) else []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_context_md(
    *,
    kode: str,
    obyek: str,
    skill: str,
    nomor_st: str | None = None,
    tanggal_st: str | None = None,
    penugasan_folder: str | Path,
    tim_anggota: list[dict] | None = None,
    gambaran_umum: str | None = None,
) -> str:
    """Susun context.md DETERMINISTIK dari field penugasan + digest.

    Field `gambaran_umum` (opsional) bila diisi → langsung dipakai. Kalau None
    → ditaruh placeholder `<!-- AI_PARAGRAPH:gambaran_umum -->` yang bisa
    di-isi LLM nanti (atau auditor manual).

    Hasil: string markdown siap tulis ke `<folder>/context.md`.
    """
    folder = Path(penugasan_folder)
    summaries = _collect_digest_summaries(folder)

    # --- ekstrak field kunci dari summaries (deterministik) ---
    kementerian = _pick_first(summaries, "kementerian") or "Kementerian Komunikasi dan Digital"
    unit_eselon = _pick_first(summaries, "unit_eselon_i") or _pick_first(summaries, "unit_eselon")
    program = _pick_first(summaries, "program_nama") or _pick_first(summaries, "program")
    kegiatan = _pick_first(summaries, "kegiatan_nama") or _pick_first(summaries, "kegiatan")
    ro = _pick_first(summaries, "ro")
    volume = _pick_first(summaries, "volume")
    satuan = _pick_first(summaries, "satuan")
    total_biaya = _pick_first(summaries, "total_biaya") or _pick_first(summaries, "total_pagu")
    dasar_hukum = _collect_dasar_hukum(summaries)
    tahun_anggaran = _detect_tahun_anggaran(summaries)
    obyek_singkat = obyek if len(obyek) < 90 else obyek[:87] + "…"
    kementerian_atau_unit = unit_eselon or kementerian

    # --- template per skill ---
    skill_norm = (skill or "").strip().lower()
    tpl = _SKILL_TEMPLATES.get(skill_norm, _SKILL_TEMPLATES["reviu-rka-kl"])
    # Hindari "RKA-K/L — RKA-K/L Kegiatan ...": kalau obyek sudah mengandung
    # prefix-nya, pakai obyek langsung.
    if tpl["title_prefix"].lower() in obyek_singkat.lower():
        judul = obyek_singkat
    else:
        judul = f"{tpl['title_prefix']} — {obyek_singkat}"
    tujuan_txt = tpl["tujuan"].format(
        obyek_singkat=obyek_singkat,
    )
    rl_txt = tpl["ruang_lingkup"].format(
        obyek_singkat=obyek_singkat,
        kementerian_atau_unit=kementerian_atau_unit,
        tahun_anggaran=tahun_anggaran,
    )
    fokus_txt = tpl["fokus"]

    # --- tim ---
    if tim_anggota is None:
        tim_anggota = _load_tim(folder)

    tim_rows: list[str] = []
    tim_rows.append("| Peran | Nama | NIP | Jabfung |")
    tim_rows.append("|-------|------|-----|---------|")
    if tim_anggota:
        for m in tim_anggota:
            peran = m.get("peran") or m.get("role") or "Anggota"
            nama = m.get("nama") or m.get("name") or "[DIISI AUDITOR]"
            nip = m.get("nip") or "[DIISI AUDITOR]"
            jabfung = m.get("jabfung") or m.get("jabatan") or "Auditor Pertama"
            tim_rows.append(f"| {peran} | {nama} | {nip} | {jabfung} |")
    else:
        tim_rows.append("| Ketua Tim | [DIISI AUDITOR] | [DIISI AUDITOR] | Auditor Madya |")
        tim_rows.append("| Anggota | [DIISI AUDITOR] | [DIISI AUDITOR] | Auditor Pertama |")
    tim_md = "\n".join(tim_rows)

    # --- ringkasan obyek (paragraf deterministik dari digest) ---
    ringkasan_parts: list[str] = []
    if kementerian_atau_unit:
        intro = f"{kementerian_atau_unit}, {kementerian}," if unit_eselon else kementerian
        ringkasan_parts.append(intro)
    if kegiatan and program:
        ringkasan_parts.append(
            f" merencanakan Kegiatan **{kegiatan}** dalam Program {program} "
            f"Tahun Anggaran {tahun_anggaran}."
        )
    elif kegiatan:
        ringkasan_parts.append(f" merencanakan Kegiatan **{kegiatan}** Tahun Anggaran {tahun_anggaran}.")
    else:
        ringkasan_parts.append(
            f" merencanakan kegiatan {obyek_singkat} Tahun Anggaran {tahun_anggaran}."
        )

    if ro:
        vol_str = ""
        if volume:
            v_text = str(volume).strip()
            sat_text = (satuan or "").strip()
            # Hindari "1 Sistem Sistem" — kalau volume sudah mengandung satuan,
            # jangan tempel satuan lagi.
            if sat_text and sat_text.lower() not in v_text.lower():
                vol_str = f" dengan volume **{v_text} {sat_text}**"
            else:
                vol_str = f" dengan volume **{v_text}**"
        ringkasan_parts.append(
            f" Rincian Output (RO) yang menjadi obyek reviu adalah **{ro}**{vol_str}."
        )

    rp = _format_rupiah(total_biaya)
    if rp:
        ringkasan_parts.append(f" Total anggaran yang diusulkan sebesar **{rp}**.")

    if dasar_hukum:
        if len(dasar_hukum) <= 3:
            ringkasan_parts.append(
                f" Dasar hukum penyusunan meliputi {', '.join(dasar_hukum)}."
            )
        else:
            head = ", ".join(dasar_hukum[:3])
            ringkasan_parts.append(
                f" Dasar hukum penyusunan meliputi {head}, dan {len(dasar_hukum)-3} regulasi lain."
            )

    ringkasan_parts.append(f" {fokus_txt}")
    ringkasan_obyek = "".join(ringkasan_parts).strip()

    # --- gambaran umum (LLM-opsional) ---
    if not gambaran_umum:
        gambaran_umum = (
            "<!-- AI_PARAGRAPH:gambaran_umum — 2-4 kalimat naratif latar belakang "
            "penugasan; isi otomatis via LLM (Mode A KT) atau biarkan auditor "
            "isi manual. -->"
        )

    # --- daftar dokumen sumber ---
    docs_md = ""
    if summaries:
        lines = ["", "## Dokumen Sumber Hasil Ingestion", ""]
        for s in summaries:
            jenis = s.get("jenis") or "—"
            fname = s.get("file") or "?"
            extras: list[str] = []
            for k in ("ro", "obyek", "total_biaya", "total_pagu", "nilai_hps", "jumlah_komponen"):
                if s.get(k) not in (None, "", 0):
                    v = s[k]
                    if k in ("total_biaya", "total_pagu", "nilai_hps"):
                        v = _format_rupiah(v) or v
                    extras.append(f"{k}={v}")
            extra_str = f" — {', '.join(extras)}" if extras else ""
            lines.append(f"- **{jenis}** `{fname}`{extra_str}")
        docs_md = "\n".join(lines)

    # --- compose ---
    md = f"""# Konteks Penugasan: {judul}

## Identitas Penugasan

- Kode: {kode}
- Obyek: {obyek}
- Skill / Jenis Pengawasan: {skill_norm}
- Nomor ST: {nomor_st or '[DIISI AUDITOR]'}
- Tanggal ST: {tanggal_st or '[DIISI AUDITOR]'}

## Periode & Anggaran

- Periode: Januari–Desember {tahun_anggaran}
- Tahun Anggaran: {tahun_anggaran}

Tujuan: {tujuan_txt}

Ruang Lingkup: {rl_txt}

## Tim

{tim_md}

## Ringkasan Obyek

{ringkasan_obyek}

## Gambaran Umum

{gambaran_umum}
{docs_md}
"""
    return md.rstrip() + "\n"


def write_context_md(
    penugasan_folder: str | Path,
    *,
    overwrite: bool = False,
    **kwargs,
) -> tuple[Path, bool]:
    """Tulis context.md ke folder. Return (path, written_or_skipped).

    Bila file sudah ada dan `overwrite=False` → SKIP (return False).
    """
    folder = Path(penugasan_folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "context.md"
    if path.exists() and not overwrite:
        return path, False
    md = build_context_md(penugasan_folder=folder, **kwargs)
    path.write_text(md, encoding="utf-8")
    return path, True
