#!/usr/bin/env python3
"""Harness ujicoba DIGESTION (pipeline V6 deterministik) untuk BANYAK dokumen.

Menjalankan digest yang sama dgn produksi (digest_tor/digest_rab per-file,
digest_pengadaan folder-level) atas sebuah korpus, secara PARALEL, lalu mengukur
KECEPATAN + KUALITAS hasil otomatis (tanpa baca tiap JSON manual).

Klasifikasi jenis dokumen:
  - dari nama SUBFOLDER bila cocok {tor,rab,kak,hps,rfi,kontrak}; else
  - dari prefiks nama file (classify_doc_by_filename).
ST/KP/PKP/OTHER dilewati (tak punya digest script).

Kualitas:
  - JSON valid + tidak kosong.
  - Cakupan field kunci per jenis (reuse _summarize_digest).
  - Deteksi GAMBAR tertanam per dokumen → tandai "data mungkin di gambar" bila
    field kunci hilang + dokumen memuat gambar (tabel/diagram di-render jadi image).
  - (opsional) --llm-fallback → untuk dokumen yang field kuncinya hilang (parser
    deterministik tak menangani), panggil model murah (Haiku) atas TEKS dokumen
    untuk MEMULIHKAN field yang hilang. Mengukur berapa yang bisa dipulihkan.
  - (opsional) --golden golden.json → skor akurasi terhadap nilai harapan.

Pakai (dari root repo, venv aktif):
  PYTHONPATH=backend backend/.venv/bin/python backend/scripts/digestion_harness.py \
      --corpus <folder> [--out <folder>] [--workers 4] [--golden golden.json] \
      [--llm-fallback] [--llm-model claude-3-5-haiku-latest]

Format golden.json:
  { "NAMA-FILE.pdf": { "label": "nilai harapan (substring, case-insensitive)", ... } }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path

from app.llm_extract import (
    DEFAULT_LLM_MODEL,
    analyze_images,
    extract_fields_hybrid,
    extract_pdf_pages,
    llm_extract_fields,
    resolve_anthropic_key,
)
from app.storage import classify_doc_by_filename, target_subfolder_for
from app.tools.kkp_tools import COVERAGE_KEYS, _summarize_digest
from app.tools.v6_bridge import run_v6_script, safe_read_json

_SUBFOLDER_JENIS = {"tor", "rab", "kak", "hps", "rfi", "kontrak"}
_PBJ = {"KAK", "HPS", "RFI", "KONTRAK"}


def classify(path: Path, corpus: Path) -> str:
    parent = path.parent.name.lower()
    if parent in _SUBFOLDER_JENIS:
        return parent.upper()
    return classify_doc_by_filename(path.name)


def coverage(jenis_summary: str, summ: dict) -> tuple[int, int, list[str]]:
    keys = COVERAGE_KEYS.get(jenis_summary, [])
    present = [k for k in keys if summ.get(k) not in (None, "", [], 0)]
    missing = [k for k in keys if k not in present]
    return len(present), len(keys), missing


def golden_score(out_json: Path, expected: dict) -> tuple[int, int, list[str]]:
    try:
        blob = out_json.read_text(encoding="utf-8").lower()
    except OSError:
        blob = ""
    miss = []
    hit = 0
    for label, val in expected.items():
        if val and str(val).strip().lower() in blob:
            hit += 1
        else:
            miss.append(label)
    return hit, len(expected), miss


async def _digest(sem, script, args, out, timeout=180):
    async with sem:
        t0 = time.perf_counter()
        code, _stdout, err = await run_v6_script(script, args, timeout=timeout)
    return code, (time.perf_counter() - t0), err, out


async def main() -> int:
    ap = argparse.ArgumentParser(description="Harness ujicoba digestion V6")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", default=None, help="folder output (default: <corpus>/_digest-test)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--golden", default=None)
    ap.add_argument("--llm-fallback", action="store_true",
                    help="Untuk dokumen yang field kuncinya hilang, panggil model murah "
                         "(Haiku) atas TEKS dokumen untuk memulihkan field. Butuh ANTHROPIC_API_KEY.")
    ap.add_argument("--llm-model", default=DEFAULT_LLM_MODEL,
                    help=f"Model fallback (default: {DEFAULT_LLM_MODEL}).")
    args = ap.parse_args()

    llm_on = bool(args.llm_fallback)
    if llm_on and not resolve_anthropic_key():
        print("PERINGATAN: --llm-fallback diminta tapi ANTHROPIC_API_KEY tidak ada — "
              "fallback dimatikan (set di .env atau env var).")
        llm_on = False

    corpus = Path(args.corpus).resolve()
    if not corpus.is_dir():
        print(f"FATAL: korpus tidak ada: {corpus}"); return 1
    out_dir = Path(args.out).resolve() if args.out else corpus / "_digest-test"
    out_dir.mkdir(parents=True, exist_ok=True)
    golden = {}
    if args.golden and Path(args.golden).is_file():
        golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))

    pdfs = [p for p in sorted(corpus.rglob("*.pdf")) if "_digest-test" not in p.parts]
    tor, rab, pbj, skipped = [], [], [], []
    for p in pdfs:
        j = classify(p, corpus)
        if j == "TOR": tor.append(p)
        elif j == "RAB": rab.append(p)
        elif j in _PBJ: pbj.append((p, j))
        else: skipped.append((p, j))

    sem = asyncio.Semaphore(max(1, args.workers))
    jobs = []   # (label, jenis_summary, files, coro)

    for i, p in enumerate(tor, 1):
        o = out_dir / f"tor-{i:02d}.json"
        jobs.append((p.name, "TOR", [p],
                     _digest(sem, "scripts/reviu-rka-kl/digest_tor.py", [str(p), "--no-raw", "-o", str(o)], o)))
    for i, p in enumerate(rab, 1):
        o = out_dir / f"rab-{i:02d}.json"
        jobs.append((p.name, "RAB", [p],
                     _digest(sem, "scripts/reviu-rka-kl/digest_rab.py", [str(p), "-o", str(o)], o)))

    # PBJ folder-level: stage ke folder bergaya penugasan (subfolder sesuai target),
    # lalu digest_pengadaan sekali. Satu hasil gabungan utk semua dok PBJ.
    pbj_stage = None
    if pbj:
        pbj_stage = Path(tempfile.mkdtemp(prefix="pbj-stage-"))
        for p, j in pbj:
            sub = pbj_stage / target_subfolder_for(j)
            sub.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, sub / p.name)
        o = out_dir / "pengadaan-digest.json"
        jobs.append(("(" + ", ".join(p.name for p, _ in pbj) + ")", "PENGADAAN", [p for p, _ in pbj],
                     _digest(sem, "scripts/audit-pengadaan/digest_pengadaan.py", [str(pbj_stage), "-o", str(o)], o)))

    print(f"Korpus: {corpus}  | PDF={len(pdfs)} (TOR={len(tor)} RAB={len(rab)} PBJ={len(pbj)} skip={len(skipped)})")
    print(f"Workers={args.workers}  | LLM-fallback={'ON ('+args.llm_model+')' if llm_on else 'off'}"
          f"  | output={out_dir}\n--- menjalankan digest paralel ---")
    t0 = time.perf_counter()
    results = await asyncio.gather(*(c for *_, c in jobs))
    wall = time.perf_counter() - t0

    rows = []
    for (label, js, files, _), (code, dur, err, out) in zip(jobs, results):
        ok = code == 0 and out.exists()
        data = safe_read_json(out) if ok else {}
        nonempty = bool(data) and bool(json.dumps(data).strip()) and json.dumps(data) != "{}"
        summ = _summarize_digest(out.name, data) if nonempty else {}
        pres, tot, missing = coverage(js, summ)

        # Analisis GAMBAR (selalu) — agregasi lintas file sumber.
        img_total = img_pages = 0
        for f in files:
            a = analyze_images(f)
            img_total += a["total_images"]; img_pages += a["pages_with_images"]

        # Fallback LLM (opt-in) — hanya bila ada field kunci yang hilang.
        llm_recovered: list[str] = []
        llm_filled: dict = {}
        llm_error: str | None = None
        if llm_on and ok and missing:
            pages_text: list[str] = []
            for f in files:
                pages_text += extract_pdf_pages(f)
            # Hybrid: regex deterministik dulu, Haiku hanya untuk residual.
            res = extract_fields_hybrid(pages_text, js, missing, model=args.llm_model)
            if res.get("_error"):
                llm_error = res["_error"]
            for k in missing:
                v = res.get(k)
                if v not in (None, "", [], 0):
                    llm_recovered.append(k); llm_filled[k] = v
        missing_after = [k for k in missing if k not in llm_recovered]

        gh = gt = None; gmiss = []
        if ok:
            # golden cocokkan per file (untuk PBJ: cocokkan tiap file ke dok gabungan)
            for f in files:
                if f.name in golden:
                    h, t, m = golden_score(out, golden[f.name])
                    gh = (gh or 0) + h; gt = (gt or 0) + t; gmiss += [f"{f.name}:{x}" for x in m]
        rows.append({"label": label, "jenis": js, "ok": ok, "time_s": round(dur, 2),
                     "nonempty": nonempty, "coverage": f"{pres}/{tot}", "missing": missing,
                     "missing_after": missing_after,
                     "images": img_total, "pages_with_images": img_pages,
                     "llm_recovered": llm_recovered, "llm_filled": llm_filled,
                     "llm_error": llm_error,
                     "golden": (f"{gh}/{gt}" if gt else None), "golden_miss": gmiss,
                     "error": (err[:200] if not ok else "")})

    # ---- ringkasan konsol ----
    print(f"\n=== RINGKASAN (wall {wall:.2f}s, {len(jobs)} job) ===")
    by = {}
    for r in rows:
        by.setdefault(r["jenis"], []).append(r)
    header = f"{'jenis':11} {'n':>2} {'ok':>3} {'kosong':>6} {'avg s':>6} {'cakupan':>9} {'gbr':>5}"
    if llm_on:
        header += f" {'+LLM':>5}"
    print(header)
    for js, rs in by.items():
        nok = sum(1 for r in rs if r["ok"])
        empt = sum(1 for r in rs if r["ok"] and not r["nonempty"])
        avg = sum(r["time_s"] for r in rs) / len(rs)
        cov_pct = []
        for r in rs:
            a, b = r["coverage"].split("/")
            if int(b): cov_pct.append(int(a) / int(b))
        cavg = f"{(sum(cov_pct)/len(cov_pct)*100):.0f}%" if cov_pct else "-"
        imgtot = sum(r["images"] for r in rs)
        line = f"{js:11} {len(rs):>2} {nok:>3} {empt:>6} {avg:>6.2f} {cavg:>9} {imgtot:>5}"
        if llm_on:
            rec = sum(len(r["llm_recovered"]) for r in rs)
            line += f" {('+' + str(rec)) if rec else '-':>5}"
        print(line)

    if llm_on:
        rec_total = sum(len(r["llm_recovered"]) for r in rows)
        rec_docs = sum(1 for r in rows if r["llm_recovered"])
        n_err = sum(1 for r in rows if r["llm_error"])
        print(f"\nLLM fallback ({args.llm_model}): pulih {rec_total} field di {rec_docs} dok"
              + (f" · {n_err} dok gagal panggil LLM" if n_err else ""))

    attention = [r for r in rows if (not r["ok"]) or (not r["nonempty"])
                 or r["missing_after"] or r["golden_miss"] or r["llm_error"]]
    if attention:
        print(f"\n=== PERLU PERHATIAN ({len(attention)}) ===")
        for r in attention:
            why = []
            if not r["ok"]:
                why.append(f"GAGAL: {r['error']}")
            elif not r["nonempty"]:
                why.append("KOSONG (tak ada teks terbaca — cek dokumen)")
            if r["missing_after"]:
                msg = f"field hilang: {','.join(r['missing_after'])}"
                if r["pages_with_images"]:
                    msg += f" → data mungkin di GAMBAR ({r['images']} gbr/{r['pages_with_images']} hlm)"
                why.append(msg)
            if r["llm_recovered"]:
                why.append(f"LLM pulih: {','.join(r['llm_recovered'])}")
            if r["llm_error"]:
                why.append(f"fallback LLM gagal: {r['llm_error']}")
            if r["golden_miss"]:
                why.append(f"golden meleset: {','.join(r['golden_miss'])}")
            print(f"  [{r['jenis']}] {r['label'][:50]} — {' ; '.join(why)}")
    if skipped:
        print(f"\nDilewati (non-digestible): {[p.name for p, _ in skipped]}")

    # ---- report files ----
    (out_dir / "report.json").write_text(json.dumps(
        {"corpus": str(corpus), "wall_s": round(wall, 2), "rows": rows,
         "skipped": [p.name for p, _ in skipped]}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Laporan Ujicoba Digestion",
          f"Korpus: `{corpus}` · wall {wall:.2f}s · {len(jobs)} job"
          + (f" · LLM-fallback `{args.llm_model}`" if llm_on else "") + "\n",
          "| jenis | dok | ok | kosong | waktu(s) | cakupan | gbr | LLM pulih | golden |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        rec = ("+" + ",".join(r["llm_recovered"])) if r["llm_recovered"] else (
            "gagal" if r["llm_error"] else "-")
        md.append(f"| {r['jenis']} | {r['label'][:40]} | {'✓' if r['ok'] else '✗'} | "
                  f"{'kosong' if r['ok'] and not r['nonempty'] else '-'} | {r['time_s']} | "
                  f"{r['coverage']} | {r['images'] or '-'} | {rec} | {r['golden'] or '-'} |")
    (out_dir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nReport: {out_dir/'report.md'} + report.json")

    if pbj_stage:
        shutil.rmtree(pbj_stage, ignore_errors=True)
    n_fail = sum(1 for r in rows if not r["ok"])
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
