"""Orkestrator eval — nilai temuan agen terhadap golden case + rubrik.

Pakai:
    cd backend
    .venv/bin/python -m eval.run_eval                       # semua golden case
    .venv/bin/python -m eval.run_eval --case <case_id>      # satu case
    .venv/bin/python -m eval.run_eval --no-judge            # cek deterministik saja (gratis, tanpa API)

Hasil: ringkasan ke stdout + scorecard JSON di eval/out/scorecard-<case>-<ts>.json.
Model judge via env EVAL_JUDGE_MODEL (default claude-opus-4-8).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from eval import deterministic

EVAL_DIR = Path(__file__).parent
GOLDEN_DIR = EVAL_DIR / "golden"
OUT_DIR = EVAL_DIR / "out"


def _data_root() -> Path:
    return get_settings().data_dir / "penugasan"


def load_cases(case_id: str | None) -> list[dict]:
    cases = []
    for p in sorted(GOLDEN_DIR.glob("*.json")):
        c = json.loads(p.read_text())
        if case_id and c.get("case_id") != case_id:
            continue
        cases.append(c)
    return cases


def read_temuan(folder: Path) -> list[dict]:
    p = folder / "_KKP" / "temuan.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    if isinstance(d, list):
        return d
    return d.get("temuan") or d.get("items") or d.get("findings") or []


def score_case(case: dict, use_judge: bool) -> dict:
    # Case sintetis boleh menyertakan temuan inline (untuk fixture/regресi tanpa
    # penugasan nyata); selain itu baca dari folder data.
    if case.get("temuan_inline") is not None:
        folder = Path(case.get("folder", "(inline)"))
        temuan = case["temuan_inline"]
    else:
        folder = _data_root() / case["folder"]
        temuan = read_temuan(folder)
    result: dict = {
        "case_id": case["case_id"],
        "skill": case.get("skill"),
        "folder": case["folder"],
        "n_temuan": len(temuan),
        "deterministik": {
            "grounding": deterministic.grounding_presence(temuan),
            "unsur_lengkap": deterministic.unsur_lengkap(temuan, case.get("skill")),
            "pkp_assessment": deterministic.pkp_assessment(folder, temuan),
            "qc_saipi": deterministic.qc_saipi(folder),
        },
    }
    if not temuan:
        result["error"] = "temuan.json kosong / tidak ada — jalankan agen dulu."
        return result

    if not use_judge:
        return result

    # Impor judge hanya saat dibutuhkan (agar --no-judge tak butuh API key).
    import anthropic

    from eval import judge

    try:
        is_audit = deterministic.is_audit_skill(case.get("skill"))
        per_temuan = judge.judge_per_temuan(temuan, is_audit=is_audit)
        expected = case.get("expected_key_issues", [])
        recall = judge.judge_recall(expected, temuan) if expected else []
    except anthropic.APIStatusError as e:
        msg = getattr(e, "message", str(e))
        hint = ""
        if "credit balance" in msg.lower():
            hint = " (top-up kredit Anthropic dulu)"
        elif isinstance(e, anthropic.NotFoundError):
            hint = f" (model '{judge.JUDGE_MODEL}' tak tersedia — set EVAL_JUDGE_MODEL=claude-sonnet-4-6)"
        result["judge_error"] = f"{type(e).__name__}: {msg}{hint}"
        return result

    # Verdict dihitung DETERMINISTIK dari aspek (bukan dari LLM, agar konsisten dgn rubrik).
    # Rekomendasi TIDAK dinilai di tahap KKP (ranah LHR/Ketua Tim).
    def _verdict(s):
        g, k = s.get("grounded", 0), s.get("kriteria_tepat", 0)
        if g == 0 or k == 0:
            return "TIDAK_VALID"
        if g == 1 or k == 1:
            return "RAGU"
        return "VALID"
    for s in per_temuan:
        s["verdict"] = _verdict(s)
    n = len(per_temuan) or 1
    n_tidak_valid = sum(1 for s in per_temuan if s["verdict"] == "TIDAK_VALID")
    n_ragu = sum(1 for s in per_temuan if s["verdict"] == "RAGU")
    n_valid = sum(1 for s in per_temuan if s["verdict"] == "VALID")
    # "precision" = tidak-ngawur (fokus utama: hindari temuan ngawur/TIDAK_VALID).
    # valid_penuh = temuan tanpa cacat (polish) — metrik sekunder.
    precision = round(1 - n_tidak_valid / n, 3)   # tidak-ngawur
    valid_penuh = round(n_valid / n, 3)
    # Narasi agregat = (unsur_lengkap + narasi)/4 rata-rata (tanpa rekomendasi).
    def narasi_score(s):
        return (s.get("unsur_lengkap", 0) + s.get("narasi", 0)) / 4
    narasi_agg = round(sum(narasi_score(s) for s in per_temuan) / n, 3)
    # Recall.
    exp_nonkandidat = [e for e in expected if not e.get("_kandidat")]
    matched = {m["expected_id"] for m in recall if m.get("tertangani")}
    denom = len(exp_nonkandidat) or 1
    recall_score = round(sum(1 for e in exp_nonkandidat if e["id"] in matched) / denom, 3)

    skor_gabungan = round(0.40 * precision + 0.35 * recall_score + 0.25 * narasi_agg, 3)

    result["judge"] = {
        "model": judge.JUDGE_MODEL,
        "per_temuan": [
            {"judul": t.get("judul_temuan"), **{k: s.get(k) for k in
             ("grounded", "kriteria_tepat", "unsur_lengkap", "narasi", "verdict", "alasan")}}
            for t, s in zip(temuan, per_temuan)
        ],
        "recall": recall,
        "metrik": {
            "tidak_ngawur": precision,
            "valid_penuh": valid_penuh,
            "n_ragu": n_ragu,
            "recall": recall_score,
            "narasi_agregat": narasi_agg,
            "skor_gabungan": skor_gabungan,
        },
    }
    return result


def print_summary(r: dict) -> None:
    print(f"\n=== CASE {r['case_id']} ({r['skill']}) · {r['n_temuan']} temuan ===")
    det = r["deterministik"]
    g = det["grounding"]
    print(f"  Deterministik:")
    print(f"    grounding ber-bukti : {g['ber_bukti']}/{g['total']} (rasio {g['rasio']})")
    ul = det['unsur_lengkap']
    print(f"    unsur lengkap       : {ul['lengkap']}/{ul['total']} (rasio {ul['rasio']}) · wajib={'+'.join(ul['unsur_diwajibkan'])} [{ul['jenis']}]")
    pk = det.get('pkp_assessment')
    if pk:
        rec = "YA" if pk['direkam'] else "TIDAK (langkah wajib terlewat)"
        print(f"    PKP-assessment      : direkam={rec} · sasaran_dinilai={pk['n_sasaran_dinilai']} kurang_memadai={pk['n_kurang_memadai']} usul={pk['n_usul_langkah_tambahan']} · temuan_tertelusur={pk['temuan_tertelusur']}/{pk['temuan_total']}")
    if det["qc_saipi"]:
        q = det["qc_saipi"]
        print(f"    QC SAIPI            : OK={q.get('ok')} KRITIS={q.get('kritis')} status={q.get('status')}")
    if r.get("error"):
        print(f"  ⚠ {r['error']}")
        return
    if r.get("judge_error"):
        print(f"  ⚠ judge dilewati — {r['judge_error']}")
        return
    if "judge" not in r:
        print("  (judge dilewati — mode --no-judge)")
        return
    j = r["judge"]
    print(f"  Judge ({j['model']}):")
    for pt in j["per_temuan"]:
        print(f"    [{pt['verdict']:11}] g{pt['grounded']} k{pt['kriteria_tepat']} u{pt['unsur_lengkap']} n{pt['narasi']}  · {pt['judul'][:60]}")
    miss = [m for m in j["recall"] if not m.get("tertangani")]
    if miss:
        print("  Recall — TERLEWAT:")
        for m in miss:
            print(f"    ✗ {m['expected_id']}: {m['alasan'][:80]}")
    m = j["metrik"]
    print(f"  METRIK: tidak_ngawur={m['tidak_ngawur']} · valid_penuh={m['valid_penuh']} (ragu={m['n_ragu']}) · recall={m['recall']} · narasi={m['narasi_agregat']} → SKOR={m['skor_gabungan']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="case_id tertentu (default: semua)")
    ap.add_argument("--no-judge", action="store_true", help="cek deterministik saja (tanpa API)")
    args = ap.parse_args()

    cases = load_cases(args.case)
    if not cases:
        print("Tidak ada golden case ditemukan di eval/golden/.", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    all_results = []
    for c in cases:
        r = score_case(c, use_judge=not args.no_judge)
        print_summary(r)
        all_results.append(r)

    out = OUT_DIR / f"scorecard-{args.case or 'all'}-{ts}.json"
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2))
    print(f"\n→ scorecard: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
