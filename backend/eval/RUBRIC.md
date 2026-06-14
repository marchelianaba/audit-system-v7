# Rubrik Kualitas Output Agen — Audit AI v7

> Dipakai oleh harness eval (`backend/eval/`) untuk menilai temuan (KKP) yang
> diproduksi agen Anggota Tim. Rubrik ini **wajib divalidasi auditor senior** —
> skor "golden" baru sah setelah ditinjau manusia. Versi 0.1 · 2026-06-11.

Empat dimensi (sesuai kekhawatiran yang ditetapkan): **precision** (temuan
salah/ngawur), **recall** (temuan terlewat), **narasi & rekomendasi LHP**, dan
**konsistensi** antar-run.

---

## A. Skor per-temuan (dinilai LLM-judge + cek deterministik)

Tiap temuan diberi skor 0–2 pada 5 aspek. 0 = tidak memenuhi, 1 = sebagian,
2 = memenuhi penuh.

| Aspek | Dimensi | 2 (baik) | 0 (buruk) |
|---|---|---|---|
| `grounded` | precision | `dokumen_sumber` ada (file+halaman+kutipan) **dan** kutipan benar-benar mendukung `kondisi`; angka cocok | klaim tanpa bukti, kutipan tidak mendukung, atau dokumen_sumber kosong |
| `kriteria_tepat` | precision | regulasi yang dikutip nyata, pasal benar, dan relevan dengan kondisi | regulasi salah/karangan, pasal tidak relevan |
| `unsur_lengkap` | narasi | **sadar-jenis** — AUDIT: 4 unsur (kondisi/kriteria/**sebab**/akibat); REVIU/EVALUASI/PEMANTAUAN: 3 unsur (kondisi/kriteria/akibat, **tanpa sebab**) terisi substantif | ada unsur wajib kosong atau sekadar mengulang |
| `rekomendasi_actionable` | narasi | rekomendasi (eksplisit/implisit) konkret, dapat ditindaklanjuti auditee | tidak ada arah perbaikan / normatif kosong |
| `narasi` | narasi | bahasa jelas, formal, angka konsisten, tidak ambigu | berbelit, ambigu, atau angka tidak konsisten |

**Verdict precision** (turunan): tiap temuan diberi `VALID` / `RAGU` / `TIDAK_VALID`.
- `TIDAK_VALID` bila `grounded=0` **atau** `kriteria_tepat=0` (temuan ngawur).
- `RAGU` bila ada aspek bernilai 1 yang material.
- `VALID` selebihnya.

**Metrik precision** = `VALID / total temuan`. Target awal ≥ 0,85.

---

## B. Recall vs reference (dinilai LLM-judge)

Tiap golden case punya `expected_key_issues` — daftar isu yang **seharusnya**
ditemukan (divalidasi auditor senior). Judge mencocokkan tiap expected issue ke
temuan yang diproduksi.

**Metrik recall** = `expected issue yang tertangani / total expected issue`.
Target awal ≥ 0,80. Isu yang terlewat dicatat eksplisit (untuk perbaikan
coverage / checklist kriteria per skill).

---

## C. Narasi & rekomendasi (agregat dari aspek A)

Skor narasi = rata-rata (`unsur_lengkap` + `rekomendasi_actionable` + `narasi`) / 6.
Untuk konsep LHP (output Ketua Tim) dinilai terpisah memakai QC SAIPI + judge LHP
(lihat `run_eval.py --lhp`, menyusul).

---

## D. Konsistensi antar-run (opsional, `--consistency N`)

Jalankan agen N kali pada input sama, ukur variansi: (1) jumlah temuan,
(2) berapa expected issue yang stabil tertangkap di semua run. Output =
`stabilitas = isu yang muncul di semua run / union semua isu`. Target ≥ 0,8.

---

## Skor gabungan per case

```
skor_case = 0.40 * precision      (A)
          + 0.35 * recall         (B)
          + 0.25 * narasi_agregat (C)
```

Bobot mencerminkan: temuan ngawur dan terlewat lebih berisiko bagi APIP daripada
gaya bahasa. Angka ini ditinjau ulang setelah golden set divalidasi auditor.

## Cara membaca hasil

`run_eval.py` menghasilkan `scorecard-<timestamp>.json` + ringkasan markdown:
per-temuan (aspek+verdict+alasan), recall (matched/missed), dan skor gabungan.
Bandingkan angka ini SEBELUM dan SESUDAH tiap perubahan prompt/model/konteks —
itu inti dari "mengukur supaya bisa memperbaiki".
