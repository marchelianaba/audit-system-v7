"""LLM-judge untuk eval kualitas temuan agen.

Memakai Anthropic SDK langsung (bukan claude_agent_sdk) dengan forced tool-use
agar output terstruktur & valid — kompatibel dengan anthropic==0.42.0 yang belum
punya messages.parse()/output_config.

Model judge bisa diatur via env EVAL_JUDGE_MODEL (default claude-opus-4-8 — judge
butuh akurasi tinggi, frekuensi rendah jadi biaya tak jadi soal). Bila API key
belum punya akses Opus, set EVAL_JUDGE_MODEL=claude-sonnet-4-6.
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from app.config import get_settings

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-opus-4-8")

_settings = get_settings()
_client = anthropic.Anthropic(api_key=_settings.anthropic_api_key)


def _call_tool(system: str, user: str, tool_name: str, schema: dict, max_tokens: int = 4096) -> dict[str, Any]:
    """Panggil model dengan tool_choice terkunci → kembalikan input tool (dict)."""
    resp = _client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=max_tokens,
        system=system,
        tools=[{"name": tool_name, "description": "Rekam hasil penilaian.", "input_schema": schema}],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    raise RuntimeError("Judge tidak mengembalikan tool_use block")


# ---------------------------------------------------------------------------
# A. Skor per-temuan (precision + narasi)
# ---------------------------------------------------------------------------

_PER_TEMUAN_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "indeks temuan (mulai 0) sesuai urutan input"},
                    "grounded": {"type": "integer", "enum": [0, 1, 2]},
                    "kriteria_tepat": {"type": "integer", "enum": [0, 1, 2]},
                    "unsur_lengkap": {"type": "integer", "enum": [0, 1, 2]},
                    "narasi": {"type": "integer", "enum": [0, 1, 2]},
                    "alasan": {"type": "string", "description": "1-2 kalimat, bahasa Indonesia"},
                },
                "required": ["index", "grounded", "kriteria_tepat", "unsur_lengkap", "narasi", "alasan"],
            },
        }
    },
    "required": ["scores"],
}

def _per_temuan_system(is_audit: bool) -> str:
    if is_audit:
        unsur_rule = ("- unsur_lengkap: kondisi/kriteria/SEBAB/akibat semua terisi substantif "
                      "(penugasan AUDIT wajib menggali sebab/akar penyebab).")
    else:
        unsur_rule = ("- unsur_lengkap: kondisi/kriteria/akibat terisi substantif. "
                      "PENTING: ini penugasan REVIU/EVALUASI/PEMANTAUAN — TIDAK menggali penyebab; "
                      "'sebab' yang kosong itu BENAR dan TIDAK boleh menurunkan skor.")
    return f"""Anda auditor senior APIP Inspektorat yang menilai mutu temuan hasil pengawasan (Kertas Kerja Pengawasan).
Nilai SETIAP temuan secara adversarial — default skeptis. Pakai rubrik (skor 0/1/2 per aspek):
- grounded: dokumen_sumber ada (file+halaman+kutipan) DAN kutipan benar-benar mendukung 'kondisi' (angka cocok). Bila tak ber-bukti → 0.
- kriteria_tepat: regulasi yang dikutip nyata, pasal benar, relevan dengan kondisi. Regulasi karangan/salah → 0.
{unsur_rule}
- narasi: bahasa jelas, formal, angka konsisten, tidak ambigu.
PENTING: JANGAN menilai rekomendasi — di tahap KKP temuan TIDAK memuat rekomendasi (itu ranah LHR/Ketua Tim).
Nilai hanya 4 aspek di atas (grounded/kriteria_tepat/unsur_lengkap/narasi). Verdict dihitung otomatis dari skor, jangan kirim verdict.
Jangan menilai murah hati — tujuan menemukan temuan ngawur, bukan meloloskannya."""


def judge_per_temuan(temuan_list: list[dict], is_audit: bool = False) -> list[dict]:
    """Skor tiap temuan. Kembalikan list dict skor (urut sesuai input)."""
    payload = []
    for t in temuan_list:
        payload.append({
            "judul": t.get("judul_temuan"),
            "kondisi": t.get("kondisi"),
            "kriteria": t.get("kriteria"),
            "sebab": t.get("sebab"),
            "akibat": t.get("akibat"),
            "dokumen_sumber": t.get("dokumen_sumber", []),
        })
    user = ("Nilai temuan berikut (JSON array; index dimulai 0). "
            "Kembalikan satu objek skor per temuan via tool.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2))
    out = _call_tool(_per_temuan_system(is_audit), user, "rekam_skor_temuan", _PER_TEMUAN_SCHEMA,
                     max_tokens=400 + 220 * len(payload))
    scores = out.get("scores", [])
    scores.sort(key=lambda s: s.get("index", 0))
    return scores


# ---------------------------------------------------------------------------
# B. Recall vs reference
# ---------------------------------------------------------------------------

_RECALL_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "expected_id": {"type": "string"},
                    "tertangani": {"type": "boolean"},
                    "matched_temuan_index": {"type": "integer", "description": "indeks temuan yang menutup isu ini; -1 bila tidak ada"},
                    "alasan": {"type": "string"},
                },
                "required": ["expected_id", "tertangani", "matched_temuan_index", "alasan"],
            },
        }
    },
    "required": ["matches"],
}

_RECALL_SYSTEM = """Anda auditor senior APIP. Anda diberi (1) daftar isu yang SEHARUSNYA ditemukan
(expected_key_issues, hasil validasi auditor) dan (2) daftar temuan yang BENAR diproduksi agen.
Untuk tiap expected issue, tentukan apakah ada temuan yang secara substansi menutupinya (boleh beda
kata, yang penting inti masalah & kriterianya sama). Jangan longgar: kecocokan dangkal/topik beda = tidak tertangani."""


def judge_recall(expected_issues: list[dict], temuan_list: list[dict]) -> list[dict]:
    produced = [{"index": i, "judul": t.get("judul_temuan"), "kondisi": (t.get("kondisi") or "")[:400]}
                for i, t in enumerate(temuan_list)]
    user = ("EXPECTED_KEY_ISSUES:\n" + json.dumps(expected_issues, ensure_ascii=False, indent=2)
            + "\n\nTEMUAN_DIPRODUKSI:\n" + json.dumps(produced, ensure_ascii=False, indent=2)
            + "\n\nCocokkan tiap expected issue. Kembalikan via tool.")
    out = _call_tool(_RECALL_SYSTEM, user, "rekam_recall", _RECALL_SCHEMA,
                     max_tokens=400 + 160 * len(expected_issues))
    return out.get("matches", [])
