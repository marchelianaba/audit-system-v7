"""Verification pass (P2) — saring temuan secara adversarial SEBELUM HITL.

Memakai LLM-judge eval (`judge.judge_per_temuan`) untuk menilai tiap temuan di
`_KKP/temuan.json`, lalu menurunkan verdict deterministik (sama dgn run_eval) dan
menandai temuan **TIDAK_VALID** (ngawur) / **RAGU** (perlu dipertajam) + alasan —
sebagai gerbang pra-approval Ketua Tim/Auditor. TIDAK mengubah temuan.json.

Pakai:
    cd backend
    EVAL_JUDGE_MODEL=claude-sonnet-4-6 .venv/bin/python -m eval.verify \
        --folder data/penugasan/<folder> --skill <skill>
Exit code 0 = semua VALID; 1 = ada yang perlu revisi/konfirmasi.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval import judge


def _verdict(s: dict) -> str:
    g, k = s.get("grounded", 0), s.get("kriteria_tepat", 0)
    if g == 0 or k == 0:
        return "TIDAK_VALID"
    if g == 1 or k == 1:
        return "RAGU"
    return "VALID"


def _is_audit(skill: str) -> bool:
    return bool(skill) and skill.lower().startswith("audit")


def _load_temuan(folder: Path) -> list[dict]:
    p = folder / "_KKP" / "temuan.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else (d.get("temuan") or d.get("items") or [])


def verify(folder: Path, skill: str) -> dict:
    temuan = _load_temuan(folder)
    if not temuan:
        return {"n": 0, "items": [], "flagged": 0, "lolos": True}
    scores = judge.judge_per_temuan(temuan, is_audit=_is_audit(skill))
    items = []
    for t, s in zip(temuan, scores):
        items.append({
            "judul": t.get("judul_temuan"),
            "verdict": _verdict(s),
            "grounded": s.get("grounded"),
            "kriteria_tepat": s.get("kriteria_tepat"),
            "alasan": s.get("alasan"),
        })
    flagged = sum(1 for i in items if i["verdict"] != "VALID")
    return {"n": len(temuan), "items": items, "flagged": flagged, "lolos": flagged == 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--skill", default="")
    args = ap.parse_args()
    r = verify(Path(args.folder), args.skill)
    print(f"Verification pass — {r['n']} temuan · {r['flagged']} perlu perhatian (judge {judge.JUDGE_MODEL})")
    for it in r["items"]:
        mark = "✓" if it["verdict"] == "VALID" else "⚠"
        print(f"  {mark} [{it['verdict']:11}] g{it['grounded']} k{it['kriteria_tepat']} · {(it['judul'] or '')[:56]}")
        if it["verdict"] != "VALID":
            print(f"      → {(it['alasan'] or '')[:110]}")
    print("GATE:", "LOLOS (semua VALID)" if r["lolos"] else
          f"{r['flagged']} temuan perlu revisi/konfirmasi sebelum HITL")
    return 0 if r["lolos"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
