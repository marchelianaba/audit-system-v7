# Eval — pengukuran kualitas output agen (P1)

Fondasi "ukur dulu, baru perbaiki". Menilai temuan (KKP) yang diproduksi agen
Anggota Tim terhadap **golden case** + **rubrik** (lihat `RUBRIC.md`), di empat
dimensi: precision (temuan ngawur), recall (terlewat), narasi & rekomendasi,
konsistensi.

## Jalankan

```bash
cd backend
.venv/bin/python -m eval.run_eval --no-judge          # cek deterministik (GRATIS, tanpa API)
.venv/bin/python -m eval.run_eval                      # + LLM-judge (butuh kredit Anthropic)
.venv/bin/python -m eval.run_eval --case reviurkakl-e2e-51
```

Hasil tercetak ke layar + `eval/out/scorecard-*.json`. Bandingkan skor SEBELUM
dan SESUDAH tiap perubahan prompt/model/konteks.

Model judge: env `EVAL_JUDGE_MODEL` (default `claude-opus-4-8`; pakai
`claude-sonnet-4-6` bila key belum punya akses Opus).

## Isi

| File | Fungsi |
|---|---|
| `RUBRIC.md` | Rubrik 4 dimensi — **wajib divalidasi auditor senior** |
| `golden/*.json` | Golden case: pointer ke folder penugasan + `expected_key_issues` |
| `deterministic.py` | Cek gratis: grounding-presence, kelengkapan 4-unsur, QC SAIPI |
| `judge.py` | LLM-judge (Anthropic SDK, forced tool-use → JSON terstruktur) |
| `run_eval.py` | Orkestrator + scorecard |

## Cara menambah golden case

1. Jalankan agen pada penugasan nyata sampai `temuan.json` terisi.
2. Salin `golden/case-*.json`, isi `folder` (nama folder di `data/penugasan/`)
   dan `expected_key_issues` (daftar isu yang SEHARUSNYA ketahuan).
3. **Mintakan validasi auditor senior** atas `expected_key_issues` + rubrik.

## Aturan domain: unsur `sebab` sadar-jenis

`sebab` (penyebab/akar masalah) **hanya digali pada penugasan AUDIT**. Reviu,
evaluasi, dan pemantauan tidak sampai menggali penyebab — maka `sebab` kosong
pada non-audit (mis. Reviu RKA-K/L) itu **benar**, bukan cacat. Cek
`unsur_lengkap` + prompt judge keduanya sadar-jenis (`is_audit_skill()` =
slug skill diawali `audit`).

## Catatan (2026-06-11)

- Cek `sebab` kosong 6/6 pada penugasan 51 (Reviu RKA-K/L) adalah **benar/expected**
  setelah aturan sadar-jenis diterapkan — bukan temuan cacat.
- LLM-judge terverifikasi sampai batas API (request diterima); eksekusi penuh
  menunggu **top-up kredit Anthropic** (saldo habis juga memblokir agen AT/KT).
