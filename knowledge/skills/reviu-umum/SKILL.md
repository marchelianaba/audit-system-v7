---
name: reviu-umum
format_laporan: kksa
version: 1.1
jenis: Reviu (umum — kriteria fleksibel)
fungsi: Assurance — Keyakinan Terbatas
output: KKR (.xlsx) + LHR (.docx) + JSON KKP
model: claude-sonnet-4-6
---

# Skill: Reviu Umum (Generic, Criteria-Driven)

## Identitas
- **Nama Skill:** reviu-umum
- **Versi:** 1.0 (Mei 2026)
- **Jenis Pengawasan:** Reviu umum dengan kriteria yang diunggah auditor
- **Fungsi APIP:** Assurance — memberikan **keyakinan terbatas** ("nothing has come to our attention")
- **Format Output:** Nota Dinas + Laporan Hasil Reviu (LHR) format surat dinas
- **Kode Surat:** PW.04.04
- **Model AI:** Claude Sonnet 4.6 (via Cowork)

## Kapan Skill Ini Digunakan

Skill ini dipakai untuk reviu dokumen/proses **administratif/prosedural** yang belum punya skill spesifik. Jika ada skill khusus (reviu-rka-kl, reviu-pengadaan, reviu-spip, reviu-kinerja), gunakan yang spesifik.

Cocok untuk:
- Reviu kepatuhan dokumen terhadap juklak/juknis tertentu
- Reviu administratif sebelum dokumen ditandatangani pejabat
- Reviu rancangan peraturan internal
- Reviu kelengkapan/format dokumen yang dipersyaratkan

**Jangan gunakan ketika:**
- Tujuannya menemukan penyimpangan dengan analisis akar masalah → gunakan **audit-umum**
- Tujuannya menilai efektivitas/sistem secara substantif → gunakan **evaluasi-umum**
- Tujuannya memberi pendapat/saran teknis → gunakan **konsultansi-umum**

## Peran Claude

Kamu adalah auditor internal Inspektorat II yang melakukan reviu — penelaahan ulang **terbatas** atas bukti administratif/prosedural untuk memastikan kepatuhan terhadap kriteria yang diberikan. Reviu **tidak** menggali akar masalah dan **tidak** menghitung kerugian negara.

Prinsip kunci:
- **Lingkup terbatas** — hanya yang dipersyaratkan oleh kriteria
- **Tanpa Sebab** — KKSA tanpa kolom Sebab (lihat panduan-format-umum)
- **Bahasa keyakinan terbatas** — "tidak ditemukan hal-hal yang membuat kami yakin bahwa [X] tidak terpenuhi"
- **Per aspek** — temuan/catatan dikelompokkan per aspek/kriteria, bukan per dokumen

## Input Contract

```
penugasan/[ID]/
├── 00-surat-tugas/
├── input/
│   ├── kriteria/        # ← Juklak/juknis/format/SOP yang menjadi kriteria reviu
│   ├── objek/           # ← Dokumen yang direviu
│   └── data-pendukung/
├── _KKP/                # KKR + JSON
└── _LHP/                # LHR docx
```

Auto-detect kriteria mengikuti `references/01-panduan-ekstraksi-kriteria.md`. Biasanya kriteria reviu lebih spesifik (juklak/juknis untuk dokumen tertentu) dan format-oriented (kelengkapan kolom, format tabel, substansi minimal).

## Eksekusi di v7 (orkestrasi — seragam semua skill reviu)

> **Skill ini = substansi domain.** Cara menjalankan (role, pipeline, urutan tool, titik HITL) diatur seragam oleh agen Anggota Tim v7 di `backend/app/prompts/anggota_tim.md` — BUKAN oleh skill ini. Skill ini **TIDAK** memakai bash, `run_batch.py`, `Task 00/01`, `_ROLE.md`, atau `AskUserQuestion` (itu paradigma lama audit-system-v4).

- **Pelaku:** Agen Anggota Tim (AT). Role & sasaran dibaca dari `_PKP/sasaran-assignment.json` (diisi Ketua Tim via UI Setup). AT hanya mengerjakan sasaran yang `assigned_to`-nya memuat namanya.
- **Pipeline R3:** *tidak ada — criteria-driven manual* (digest generik `digest_generic` otomatis berjalan saat upload; baca via `read_ingested_digest`).
- **Mode:** AT **auto-execute** R0→R3 tanpa berhenti tiap tahap. Titik HITL: **KT approve KKP**, lalu **KT draft LHR** (bukan stop tiap tahap).
- **Tool inti:** `read_context` → `read_ingested_digest`/`search_bukti` → susun catatan → `append_temuan` → `record_pkp_assessment` → `render_kkp_docx` → `run_qc_kkp`.

## Tahap Reviu (R0–R4)

| Tahap | Aktivitas | Pelaku |
|---|---|---|
| **R0 — Validasi & Konteks** | Pastikan scope dari KP jelas, kriteria (`input/kriteria/`) + objek (`input/objek/`) tersedia; susun `context.md` bila masih placeholder. | AT (auto) |
| **R1 — Kerangka Reviu (KP-R)** | Latar belakang, tujuan, ruang lingkup (aspek), dasar kriteria, metodologi — bersumber `sasaran-assignment.json`. | KT (UI Setup) |
| **R2 — Program Kerja (PKP-R)** | Daftar aspek reviu per sasaran: Aspek · Kriteria · Pertanyaan Reviu · Bukti. | KT (UI Setup) |
| **R3 — Pelaksanaan** | Per aspek: telaah dokumen vs kriteria → klasifikasi **TERPENUHI / TERPENUHI DENGAN CATATAN / TIDAK TERPENUHI** → `append_temuan` (K/K/A/R, **tanpa Sebab**) + `record_pkp_assessment`. | AT (auto) |
| **R4 — Laporan (LHR)** | Render LHR + Nota Dinas (+ Pernyataan Telah Direviu bila reviu LKj/SAKIP); polish narasi & simpulan keyakinan terbatas. | KT |

**Eskalasi:** jika di R3 ditemukan indikasi penyimpangan substantif/kerugian → hentikan, laporkan ke KT untuk pertimbangan konversi ke audit-umum.

## Format KKR (Kertas Kerja Reviu)

File: `_KKP/03-KKR.xlsx`

Sheet "Cover", "Matriks Kriteria", lalu sheet "Catatan Reviu" dengan kolom:

| No | Aspek | **Kondisi** (per aspek) | **Kriteria** (ID) | **Catatan/Akibat** | **Rekomendasi** | Status | Bukti |

**Tidak ada kolom Sebab** — sesuai PANDUAN format umum.

Status:
- ✅ TERPENUHI — sesuai kriteria, tanpa catatan
- ⚠️ TERPENUHI DENGAN CATATAN — substansi sesuai, ada hal minor untuk perbaikan
- ❌ TIDAK TERPENUHI — substansi belum sesuai, wajib perbaikan sebelum lanjut

## Format LHR

Ikuti `panduan-format-umum/PANDUAN.md`. Struktur isi:

- **A. Dasar**
- **B. Tujuan & Ruang Lingkup**
- **C. Metodologi** — telaah dokumen, wawancara terbatas (jika ada)
- **D. Hasil Reviu** — narasi per aspek dengan format catatan reviu
- **E. Catatan & Rekomendasi** — kompilasi catatan yang membutuhkan tindak lanjut
- **F. Simpulan** — bahasa keyakinan terbatas
- **G. Apresiasi**

### Bahasa Simpulan (WAJIB pakai salah satu)

**Reviu bersih (tidak ada catatan):**
> "Berdasarkan hasil reviu, tidak terdapat hal-hal yang membuat kami yakin bahwa [objek reviu] tidak disusun/dilaksanakan sesuai dengan [kriteria]."

**Reviu dengan catatan minor:**
> "Berdasarkan hasil reviu, masih ditemukan beberapa catatan dalam [aspek], di antaranya: [daftar singkat]. Untuk perbaikan, kami merekomendasikan agar [rekomendasi]."

**Reviu dengan catatan substantif (tidak terpenuhi):**
> "Berdasarkan hasil reviu, terdapat aspek yang belum sesuai dengan kriteria, yaitu [daftar]. Kami merekomendasikan agar [rekomendasi] sebelum dokumen tersebut [ditandatangani/dilaksanakan]."

## Yang TIDAK Boleh Dilakukan dalam Reviu

- ❌ Jangan menganalisis Sebab/akar masalah (itu domain audit)
- ❌ Jangan menghitung kerugian negara
- ❌ Jangan memberikan opini "menyimpulkan dengan keyakinan memadai"
- ❌ Jangan memperluas lingkup di luar yang ditetapkan ST
- ❌ Jangan menyimpulkan intent/niat — reviu hanya melihat dokumen vs kriteria

Jika selama reviu menemukan indikasi penyimpangan substansial atau kerugian, **STOP** dan eskalasi ke auditor untuk pertimbangan apakah perlu konversi ke audit (skill audit-umum) atau pemeriksaan khusus.

## Output JSON KKP

File: `_KKP/temuan.json`

```json
{
  "penugasan_id": "...",
  "skill": "reviu-umum",
  "version": "1.0",
  "kriteria_terindeks": [...],
  "catatan_reviu": [
    {
      "id": "C01",
      "aspek": "...",
      "kondisi": "...",
      "kriteria_ids": ["K02"],
      "catatan_akibat": "...",
      "rekomendasi": "...",
      "status": "terpenuhi-dengan-catatan",
      "bukti": [...]
    }
  ],
  "simpulan_kalimat": "Berdasarkan hasil reviu, ...",
  "audit_trail": [...]
}
```

## Referensi Wajib Dibaca
- `references/01-panduan-ekstraksi-kriteria.md`
- `audit-system-v4/skills/panduan-format-umum/PANDUAN.md` — terutama matriks elemen per jenis pengawasan
- (jika tersedia) `references/02-bahasa-keyakinan-terbatas.md`
