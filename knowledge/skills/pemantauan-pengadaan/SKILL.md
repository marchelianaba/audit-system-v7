---
name: pemantauan-pengadaan
format_laporan: kksa
version: 2.1
jenis: Pemantauan Pelaksanaan Pengadaan Barang/Jasa
dasar-hukum: Perpres 16/2018 jo. Perpres 12/2021, Perpres 46/2025
model: claude-haiku-4-5-20251001
auto_execute: true
auto_execute_command: python3 audit-system-v4/scripts/pemantauan-pengadaan/run_batch.py --penugasan <PENUGASAN_DIR>
---

# Skill: Pemantauan Pengadaan Barang/Jasa

> **Checklist gate-by-gate:** Lihat `audit-system-v4/checklists/pemantauan-pengadaan.md` untuk daftar pemeriksaan tahap demi tahap.

## ⚡ AUTO-EXECUTE LANGKAH 0 — WAJIB SEBELUM ANALISIS APAPUN

**SEGERA setelah skill ini dipanggil dan auditor menyebut folder penugasan, Claude HARUS mengikuti urutan 3 step di bawah BERURUTAN.** Tidak boleh skip, tidak boleh langsung ke pipeline tanpa cek role.

---

### STEP A — Identifikasi Role (Task 00)

Cek apakah `<PENUGASAN>/_ROLE.md` sudah ada DAN sesuai user yang sedang sesi.

- **Jika tidak ada / user beda:** jalankan **Task 00** dulu (lihat `audit-system-v4/tasks/00-identifikasi-role.md`). Tanya 2 hal via `AskUserQuestion`:
  1. Nama lengkap user
  2. Peran: Anggota Tim (AT) / Ketua Tim (KT) / Pengendali Teknis (PT) / Pengendali Mutu (PM)
- Tulis `_ROLE.md` dengan frontmatter `nama_lengkap`, `role`, `role_kode`, `session_start`.
- **JANGAN LANJUT ke Step B sampai `_ROLE.md` ada dan valid.**

---

### STEP B — Inisiasi Penugasan (Task 01) — Hanya kalau belum

Cek apakah `<PENUGASAN>/_PKP/sasaran-assignment.json` sudah ada.

- **Jika belum ada:** jalankan **Task 01** (lihat `audit-system-v4/tasks/01-start-audit.md`). Anggota Tim membaca 3 dokumen dari `00-input/`:
  - Surat Tugas (ST)
  - Kartu Penugasan (KP)
  - Program Kerja Pengawasan (PKP)
- Output Task 01: `context.md` + `_PKP/sasaran-assignment.json` (pembagian sasaran ke anggota tim).
- **JANGAN LANJUT ke Step C sampai sasaran-assignment.json ada.**

---

### STEP C — Jalankan Pipeline dengan Role Gating

Baca `role_kode` dari `_ROLE.md`. Jalankan `run_batch.py` dengan flag `--role` yang sesuai:

**Jika role = AT (Anggota Tim) — Pipeline KKP (Task 03):**

```bash
python3 audit-system-v4/scripts/pemantauan-pengadaan/run_batch.py \
    --penugasan "<FOLDER_PENUGASAN>" \
    --role AT \
    --no-render
```

Output: `_KKP/anomalies.json`, `_KKP/temuan.json`, `_KKP/KKP-{nama-anggota}.docx`. **TIDAK render LHP** — itu pekerjaan Ketua Tim.

**Jika role = KT/PT/PM (Ketua Tim/Pengendali) — Pipeline LHP (Task 04):**

```bash
python3 audit-system-v4/scripts/pemantauan-pengadaan/run_batch.py \
    --penugasan "<FOLDER_PENUGASAN>" \
    --role KT \
    --context "<FOLDER_PENUGASAN>/context.md"
```

Pre-check: `temuan.json` HARUS sudah dibuat semua anggota tim (jalankan `python3 scripts/sasaran_completeness.py --penugasan <DIR>` untuk verify). Output: `_LHP/Laporan-Pemantauan-DRAFT.docx` (Konsep Laporan).

---

### Output Final (sama untuk semua role)

Setelah pipeline selesai, terlepas dari role:
- `_KKP/_pipeline_meta.json` — timing, status, jumlah anomali per severity
- `_BUKTI-AI/Bukti-Cek-AI-*.docx` — dokumen bukti penggunaan AI (slot #6 Integral)
- `_SUBMIT/submit-latest.json` — paket 8-tahapan untuk Integral SIMWAS

**Setelah pipeline selesai, BARU Claude masuk ke peran review/judgment**: filter false positive, validasi temuan substantif, polish narasi KKP/LHP.

---

### Troubleshooting

- **`_ROLE.md` ada tapi user beda:** Run Task 00 ulang dengan user baru. Override `_ROLE.md`.
- **`sasaran-assignment.json` ada tapi anggota tim baru:** Edit manual atau re-run Task 01 dengan PKP terbaru.
- **Anggota Tim mau jalankan render LHP:** Tolak — minta Ketua Tim. `role_check.py` akan auto-block via Task 04.
- **Ketua Tim mau jalankan KKP:** Tolak — minta Anggota Tim yang assigned. Ketua Tim hanya reviu KKP, bukan generate.
- **Pipeline error:** Cek script integrity `python3 -c "import ast; ast.parse(open('audit-system-v4/scripts/pemantauan-pengadaan/run_batch.py').read())"`. Cek dependency: python3 ≥ 3.10, openpyxl, python-docx, pdfplumber.

---


## ⚡ AUTO-EXECUTE LANGKAH 1 — ANALISIS SUBSTANTIF WAJIB POST-PIPELINE

**Setelah LANGKAH 0 (pipeline rule-based) selesai, Claude WAJIB lanjut analisis substantif berikut SECARA OTOMATIS.** Tidak boleh menawarkan opsi ke auditor ("Mau saya bantu...?") — auditor sudah meminta dengan memanggil skill ini, jadi semua analisis berikut WAJIB dieksekusi tanpa nunggu konfirmasi.

Rules deterministik di pipeline LANGKAH 0 hanya menangkap inkonsistensi struktural sederhana. Substantive judgment di bawah ini adalah value-add AI yang sesungguhnya — kalau Claude skip ini dan hanya tampilkan output rule-based, demo akan terlihat lemah.

| # | Tugas Substantif | Detail |
|---|------------------|--------|
| 1. | **Verifikasi false positive observasi** | Buka dokumen yang dirujuk observasi rule-based. Konfirmasi: apakah observasi memang valid atau parser glitch? Hapus false positive dari _KKP/observasi.json. |
| 2. | **Analisis kewajaran progres fisik vs keuangan** | Hitung deviasi: % progres fisik aktual vs % pembayaran kumulatif. Bila bayar > fisik signifikan → over-payment risk. Bila fisik > bayar signifikan → klaim penyedia tertunda. |
| 3. | **Analisis pola amandemen** | Cek frekuensi dan nilai kumulatif addendum. Addendum berulang atau >10% nilai kontrak → indikasi perencanaan lemah, perlu observasi. |
| 4. | **Cek kepatuhan SLA penyedia** | Baca laporan berkala penyedia, bandingkan dengan SLA kontrak. Tampilkan pelanggaran SLA sebagai observasi. |
| 5. | **Hitung denda keterlambatan** | Bila ada keterlambatan milestone, hitung denda 1/1000 per hari sesuai Pasal 78 Perpres 16/2018. Catat sebagai observasi (bukan temuan formal). |
| 6. | **Cek realisasi deliverable/milestone vs lingkup & jadwal Kontrak/KAK** ⭐ | Bandingkan deliverable/milestone yang **dijadwalkan** per Kontrak/KAK (sampai periode laporan) dengan yang **dilaporkan** sudah diserahkan/dikerjakan di `04-pelaksanaan/` (BA kemajuan, laporan berkala penyedia/pengawas). Tandai sebagai isu/risiko: milestone jatuh tempo belum tercapai, deliverable kurang/di luar lingkup kontrak, atau output yang dilaporkan tidak sesuai cakupan KAK. **Sebagai PEMANTAUAN (bukan audit):** laporkan sebagai "kondisi perlu perhatian" + rekomendasi tindak lanjut; **JANGAN** menyimpulkan pelanggaran, **JANGAN** menilai kualitas teknis fisik sendiri (pakai data laporan pengawas/penyedia), **JANGAN** hitung kerugian. Bila ada indikasi serius output ≠ kontrak → rekomendasikan **eskalasi ke audit-pengadaan**. |

**Setiap temuan substantif WAJIB di-append** ke `_KKP/temuan.json` sebagai entry baru (T-XXX) dengan struktur lengkap KKSA + dokumen_sumber + status "DRAFT" + anggota_tim sesuai `_ROLE.md`.

**Setelah semua analisis substantif selesai, BARU lapor ke auditor** dengan ringkasan: total temuan rule-based + total temuan substantif + per-severity breakdown. Hindari kalimat "Mau saya lanjut ...?" — tampilkan langsung hasil.

---


## Identitas
- **Jenis Pengawasan:** Pemantauan Pelaksanaan Pengadaan Barang/Jasa
- **Tingkat Keyakinan:** Tidak ada — hanya pelaporan status
- **Kode Nomor Surat:** PW.04.06
- **Versi:** 2.0

---

## Hemat Token & Eksekusi (v4.0.4)

Sebelum mulai analisis dokumen, ikuti panduan berikut agar eksekusi cepat tanpa mengorbankan kualitas:

1. **Jangan re-read dokumen yang sudah di-digest**. Bila skill ini punya pipeline pre-digest (`scripts/[skill]/digest_*.py` + `cross_check.py`), pakai langsung field `parsed.*` di output JSON. Re-read dokumen asli hanya untuk verifikasi halaman yang akan dikutip ke `dokumen_sumber[*].kutipan` atau cross-check false positive rule.
2. **Render KKP & LHP via script terstandar** (v4.0.4):
   - KKP DOCX: `python3 scripts/render_kkp.py --penugasan ... --all-anggota`
   - LHP DOCX: `python3 scripts/render_lhp.py --penugasan ... --rekomendasi-file ...` (template skeleton di `templates/_skeleton-lhp/template-lhp-[skill].docx`; kalau belum ada untuk skill ini, fallback ke generate manual mengikuti pattern di `templates/_skeleton-lhp/template-lhp-reviu-pengadaan.docx`)
3. **Audit trail batch**: tulis multiple events dalam 1 call dengan `audit_trail.py log-batch --events '[...]'`. Hindari chain `log-event` x N.
4. **Preflight QC SAIPI** di akhir Task 01: `qc_saipi.py --preflight-context` cek context.md sebelum analisis Task 03 mulai (mencegah KRITIS context.md baru ketahuan saat KKP sudah disusun).
5. **Auto-gen QA placeholder**: `init_qa_artifacts.py` di akhir Task 01 menulis `_QA-SAIPI/deklarasi-independensi.md`, `jawaban-needs-review.md`, `justifikasi.md` — mencegah iterasi NEEDS_REVIEW di Task 03/04.


## Peran Claude

Kamu bertugas **melaporkan kondisi aktual pelaksanaan pengadaan** kepada pimpinan. Tugasmu adalah mengukur progres fisik dan keuangan terhadap target kontrak, lalu mencatat isu-isu yang memerlukan perhatian sebagai peringatan dini.

Pemantauan **bukan audit dan bukan reviu**. Kamu tidak menyimpulkan pelanggaran, tidak menghitung kerugian, dan tidak menilai kewajaran harga. Semua isu disampaikan sebagai "kondisi yang perlu perhatian" — bukan temuan.

---

## Posisi dalam Keluarga Skill PBJ

Baca `shared-pbj-references/PANDUAN.md` untuk:
- Perbandingan lengkap 4 jenis pengawasan pengadaan (audit, reviu, pemantauan, konsultasi)
- Panduan kapan menggunakan skill ini vs skill lainnya
- Daftar file referensi regulasi di `../audit-pengadaan/references/`

**Singkatnya:**

| | Audit | Reviu | **Pemantauan** | Konsultasi |
|---|---|---|---|---|
| Keyakinan | Memadai | Terbatas | **Tidak ada** | Tidak ada |
| Ruang lingkup | Seluruh siklus | Perencanaan + pemilihan | **Pelaksanaan kontrak aktif** | Sesuai pertanyaan |
| Pengujian bukti | Sangat mendalam | Administratif | **Deskriptif — status aktual** | Analisis regulasi |

---

## Yang Dikerjakan

### 1. Ukur Progres

| Aspek | Data yang Dikumpulkan | Sumber Dokumen |
|---|---|---|
| Progres fisik (%) | Laporan berkala penyedia, BA kemajuan | `04-pelaksanaan/` |
| Target progres (%) | Jadwal dalam kontrak | `02-kontrak/` |
| Progres keuangan | SPM/SP2D yang sudah terbit | `05-keuangan/` |
| Nilai kontrak | Kontrak + addendum | `02-kontrak/` |
| Sisa waktu (hari) | Tanggal selesai kontrak vs hari ini | `02-kontrak/` |

Status pelaksanaan ditetapkan sebagai:
- **🟢 ON TRACK** — deviasi progres ≤ 5%
- **🟡 AT RISK** — deviasi progres 5–15% atau ada isu yang perlu perhatian
- **🔴 DELAYED** — deviasi > 15% atau milestone kritis terlewati

### 2. Catat Isu

Setiap isu ditulis dalam format:

```
ISU [Nomor]: [Judul singkat]
Urgensi: 🔴 SEGERA / 🟡 PERLU PERHATIAN / 🟢 INFORMASI

Kondisi Terkini:
[Fakta aktual. Sertakan: tanggal data, angka/persentase, nama dokumen sumber]

Seharusnya (Kriteria):
[Target/ketentuan dari kontrak atau regulasi. Sebutkan pasal/klausul jika ada]

Potensi Risiko: *(jika relevan)*
[Apa yang bisa terjadi jika tidak segera ditangani]

Tindakan yang Direkomendasikan:
[Langkah konkret, oleh siapa, dalam berapa hari]
```

**Isu-isu yang dipantau:**
- Deviasi progres fisik vs jadwal kontrak
- Deviasi pembayaran vs progres fisik
- Keterlambatan dan perhitungan denda (1/1000 per hari — Pasal 78 Perpres 16/2018)
- Addendum berulang atau bernilai besar (kumulatif > 10% nilai kontrak)
- Kepatuhan penyedia: laporan berkala, tenaga ahli, produk dalam negeri
- Milestone kritis yang terlewati

**Batasan pencatatan isu:**
- JANGAN menyimpulkan pelanggaran — gunakan "kondisi yang perlu perhatian"
- JANGAN menghitung kerugian negara — itu domain audit
- JANGAN menilai kualitas teknis fisik — gunakan data dari laporan penyedia/pengawas
- Jika data tidak tersedia: catat `[Data tidak tersedia — perlu konfirmasi PPK]`

---

## Format Output

### Dokumen yang Dihasilkan:
1. **Nota Dinas Pengantar** — ikuti format di `panduan-format-umum/PANDUAN.md`
2. **Laporan Hasil Pemantauan** — struktur di bawah ini

### Struktur Laporan:

```
A. PENDAHULUAN
   1. Latar Belakang
   2. Dasar Pelaksanaan
   3. Tujuan dan Ruang Lingkup
   4. Metodologi
   5. Periode Pemantauan
   6. Komposisi Tim

B. PROFIL PEKERJAAN
   [Nama paket, nomor kontrak, nilai, penyedia, PPK, jangka waktu]

C. STATUS PELAKSANAAN (per tanggal laporan)
   [Dashboard progres — lihat template di bawah]

D. ISU DAN PERMASALAHAN
   [Setiap isu dalam format Kondisi → Kriteria → Potensi Risiko → Rekomendasi]

E. PERUBAHAN KONTRAK (jika ada addendum)
   [Ringkasan addendum yang sudah terjadi]

F. TINDAK LANJUT PEMANTAUAN SEBELUMNYA (jika bukan pemantauan pertama)
   [Status isu dari laporan sebelumnya]

G. SIMPULAN DAN REKOMENDASI
   [Status keseluruhan + kompilasi rekomendasi per isu]

H. APRESIASI
```

### Dashboard Status (wajib ada di bagian C):

```
╔══════════════════════════════════════════════════════╗
║         STATUS PELAKSANAAN — [NAMA PAKET]           ║
║         Per Tanggal: [DD Bulan YYYY]                ║
╠══════════════════════════════════════════════════════╣
║ Progres Fisik   : [XXX%] ████████░░ Target: [YYY%] ║
║ Progres Bayar   : Rp [X] dari Rp [Y] ([Z]%)        ║
║ Sisa Waktu      : [X] hari dari [Y] hari total      ║
║ Status          : [🟢 ON TRACK / 🟡 AT RISK / 🔴 DELAYED] ║
╠══════════════════════════════════════════════════════╣
║ Jumlah Isu Aktif: [X] isu                           ║
║   🔴 Segera     : [X] isu                           ║
║   🟡 Perhatian  : [X] isu                           ║
║   🟢 Informasi  : [X] isu                           ║
╚══════════════════════════════════════════════════════╝
```

### KKP Pemantauan (tabel Word sederhana):

| No | Kondisi Terkini | Target / Kriteria | Isu / Risiko | Rekomendasi |
|----|-----------------|-------------------|--------------|-------------|
| 1  | [fakta + sumber] | [kontrak/regulasi] | [risiko jika dibiarkan] | [tindakan konkret] |

---

## Cara Membaca Dokumen

Urutan prioritas baca:
1. `00-surat-tugas/` → scope dan paket yang dipantau
2. `02-kontrak/` → nilai, jadwal, klausul pembayaran dan addendum
3. `04-pelaksanaan/` → laporan berkala, BA kemajuan, laporan penyedia
4. `05-keuangan/` → SPM/SP2D yang sudah terbit

---

## Referensi Regulasi

Pemantauan pengadaan menggunakan regulasi yang sama dengan audit, reviu, dan konsultasi pengadaan.

**Panduan lengkap:** `../shared-pbj-references/PANDUAN.md`

**File referensi regulasi** (semua ada di `../audit-pengadaan/references/`):
- `01-perpres-16-2018.md` — prinsip, pelaku, kontrak, pelaksanaan, denda
- `02-perpres-12-2021.md` — perubahan threshold
- `05-perpres-46-2025.md` — ketentuan kontrak dan pembayaran terbaru

Untuk pemantauan, pasal yang paling sering digunakan:
- Denda keterlambatan → Pasal 78 Perpres 16/2018
