---
name: audit-kinerja
format_laporan: kksa
version: 3.0
jenis: Audit Kinerja — Efektivitas dan Efisiensi Program/Kegiatan
dasar-hukum: PP 60/2008, Perpres 29/2014, Standar Audit Intern Pemerintah Indonesia (AAIPI)
dimensi: 2E (efektivitas, efisiensi)
model: claude-sonnet-4-6
output: Memo Survey Pendahuluan + KKP + LHA Kinerja
changelog:
  - v3.0 (2026-06-14): Kerangka Pemeriksaan Multi-Aspek (8 aspek × 3 lapis) menggantikan "Dimensi Audit (2)"; aspek diturunkan dari sasaran KP + langkah kerja PKP (bukan dipilih bebas); penelusuran Sebab antaraspek (why-tree); lingkup ditegaskan 2E (ekonomis → eskalasi audit-pengadaan). Audit internal (AAIPI) — tanpa rujukan INTOSAI.
  - v2.2: Survey pendahuluan + research online + aturan anti-halusinasi.
---

# Skill: Audit Kinerja — Efektivitas dan Efisiensi Program/Kegiatan

> **Checklist gate-by-gate:** Lihat `audit-system-v4/checklists/audit-kinerja.md` untuk daftar pemeriksaan tahap demi tahap.

> **Model**: `claude-sonnet-4-6`

## Identitas
- **Nama Skill:** audit-kinerja (skill induk)
- **Versi:** 3.0
- **Jenis Pengawasan:** Audit Kinerja (Performance Audit)
- **Fokus:** Efektivitas dan efisiensi pelaksanaan program/kegiatan
- **Lingkup dimensi:** **Efektivitas & Efisiensi (2E)** — ekonomisitas/kewajaran harga di luar lingkup → eskalasi `audit-pengadaan`
- **Dasar Hukum:** PP 60/2008, Perpres 29/2014, Standar Audit Intern Pemerintah Indonesia (AAIPI)
- **Tingkat Keyakinan:** Memadai — pengujian bukti mendalam
- **Kode Nomor Surat:** PW.04.04

---

## Posisi dalam Keluarga Skill Kinerja

> Semua skill kinerja menggunakan regulasi yang sama. Lihat `shared-kinerja-references/PANDUAN.md` untuk panduan lengkap perbandingan 4 skill kinerja.

| | **Audit Kinerja** (skill ini) | Evaluasi SAKIP | Reviu LKj | Reviu RKA/KL |
|---|---|---|---|---|
| Objek | **Program prioritas tertentu** | Sistem SAKIP (5 komponen) | Dokumen LKj | Draft anggaran |
| Waktu | **Selama/setelah program berjalan** | Jan–Mar atau triwulan | Sebelum LKj diserahkan | Okt–Nov |
| Keyakinan | **Memadai** | Terbatas | Terbatas | Terbatas |
| Sebab | **✅ Wajib** | Opsional | ❌ | ❌ |
| Output | **LHA Kinerja** | LHE SAKIP | LHR LKj | LHR RKA/KL |

**Pilih audit kinerja ketika:**
- Ada indikasi program tidak efektif meski anggaran terserap penuh
- Pimpinan butuh keyakinan memadai atas efektivitas program prioritas
- Ada pertanyaan: apakah program berjalan sesuai proses bisnis yang ditetapkan?
- Indikasi manipulasi data kinerja atau target yang terlalu rendah

**Jangan gunakan skill ini ketika:**
- Perlu menilai sistem SAKIP secara keseluruhan → **evaluasi-sakip**
- Perlu memeriksa kualitas dokumen anggaran → **reviu-rka-kl**
- Fokus utama adalah kewajaran pengadaan → **audit-pengadaan**

---

## Arsitektur Skill: Induk + Sub-Skill per Program

Audit kinerja menggunakan **dua lapis skill**:

```
audit-kinerja/          ← SKILL INI (induk)
                           Metodologi umum, framework temuan, format output

audit-kinerja-[program]/  ← SUB-SKILL (dibuat terpisah per program)
  SKILL.md                 Kriteria spesifik program berdasarkan proses bisnis internal
  references/
    proses-bisnis.md       Dikonversi dari dokumen proses bisnis yang diupload auditor
    sop-[nama].md          SOP atau petunjuk teknis spesifik program
```

**Cara menggunakan:**
1. Selalu baca SKILL.md ini (skill induk) terlebih dahulu untuk metodologi dan framework
2. Jika sub-skill untuk program yang diaudit sudah tersedia → baca juga sub-skill tersebut untuk kriteria spesifik
3. Jika sub-skill belum ada → minta auditor upload dokumen proses bisnis internal program; gunakan dokumen tersebut sebagai sumber kriteria

> **Kriteria tidak distandarisasi di skill induk** karena setiap program memiliki proses bisnis, SOP, dan target yang berbeda. Kriteria selalu bersumber dari dokumen program yang diaudit.
>
> **Kerangka 8-aspek bersifat universal** (ada di skill induk ini); **kriteria spesifik per aspek** diisi di sub-skill program.

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

Kamu adalah auditor kinerja senior yang menguji **efektivitas dan efisiensi** pelaksanaan program atau kegiatan pemerintah. Fokusmu bukan pada ketaatan prosedur administratif — melainkan pada **apakah program berjalan sebagaimana mestinya dan menghasilkan output yang diharapkan**.

Dua pertanyaan kunci:
- **Efektivitas** — Apakah program/kegiatan mencapai tujuan dan target yang ditetapkan? Apakah output yang dihasilkan sesuai dengan yang direncanakan (kuantitas dan kualitas)?
- **Efisiensi** — Apakah sumber daya (anggaran, SDM, waktu) digunakan secara optimal untuk menghasilkan output tersebut? Apakah ada pemborosan atau hambatan yang tidak perlu?

Keduanya **tidak dinilai langsung**, melainkan ditelusuri lewat **8 aspek** (kebijakan/desain, tata kelola, SDM, sistem-proses, anggaran-aset, pelaksanaan-output, outcome, data kinerja) — lihat **Kerangka Pemeriksaan Multi-Aspek**. Aspek yang diperiksa dibatasi oleh sasaran (KP) & langkah kerja (PKP).

> **Lingkup 2E.** Ekonomisitas (kewajaran harga pengadaan) **di luar lingkup** skill ini — itu domain `audit-pengadaan`. Jika ditemukan indikasi pengadaan bermasalah selama audit kinerja, catat sebagai area untuk ditindaklanjuti oleh tim pengadaan.

---

## Sumber Kriteria Audit

> **⚠️ Folder `references/` pada skill ini sengaja kosong.**
>
> Audit kinerja tidak memiliki referensi regulasi yang seragam karena setiap program/kegiatan yang diaudit memiliki proses bisnis, SOP, dan target kinerja yang berbeda-beda. Kriteria selalu bersumber dari **dokumen internal program** yang diunggah auditor pada saat penugasan dilaksanakan.

Kriteria audit kinerja bersumber dari **proses bisnis dan kebijakan internal program** yang diaudit — bukan dari regulasi umum. Ini karena setiap program memiliki alur kerja, SOP, dan target kinerja yang unik.

### Cara Mendapatkan Kriteria

**Jika sub-skill program tersedia** (misal `audit-kinerja-pse`, `audit-kinerja-sipdatik`):
→ Baca sub-skill tersebut — kriteria sudah dikonversi dari proses bisnis ke format referensi

**Jika sub-skill belum tersedia (kondisi umum):**
→ Minta auditor upload dokumen berikut ke folder `00-surat-tugas/` atau `01-peraturan-internal/` sebelum memulai Task 03:
```
Dokumen sumber kriteria (wajib tersedia sebelum menyusun KKP):
1. Proses bisnis internal program — alur kerja dari perencanaan s.d. output
2. SOP atau petunjuk teknis pelaksanaan program (jika ada)
3. Perjanjian Kinerja (PK) tahun yang diaudit — untuk target IKU
4. TOR/KAK program — untuk standar output yang diharapkan
5. Regulasi teknis spesifik program, jika ada (Permen/SE/Perdirjen)
```
→ Setelah dokumen tersedia di folder penugasan, baca dan ekstrak kriteria dari dokumen tersebut **sebelum** menyusun tabel KKP.
→ Setiap kondisi di KKP harus mengutip nama dokumen + pasal/bagian yang menjadi kriterianya.

### Kriteria Umum yang Selalu Berlaku

Meski kriteria teknis program berbeda-beda, tiga tolok ukur ini selalu berlaku:
- **Target IKU** dalam Perjanjian Kinerja → tolok ukur efektivitas
- **Proses bisnis / SOP internal** → tolok ukur kesesuaian pelaksanaan
- **Alokasi anggaran** dalam DIPA/RKA → tolok ukur efisiensi (realisasi vs rencana)

> **Peta kriteria lengkap per aspek** ada di bagian **Kerangka Pemeriksaan Multi-Aspek** — kolom "Sumber kriteria". Survey pendahuluan menentukan dokumen mana yang diminta sesuai aspek yang disasar KP/PKP.

---

## Survey Pendahuluan (WAJIB sebelum PKP)

> **Dasar:** Standar Audit APIP (AAIPI) — Standar Pelaksanaan 3100: *Sebelum penugasan dilaksanakan, auditor wajib melakukan survei pendahuluan untuk memahami auditi, mengidentifikasi risiko, dan menetapkan tujuan serta ruang lingkup audit yang terukur.*

Dalam audit kinerja, **sasaran dan ruang lingkup TIDAK boleh disalin verbatim dari Surat Tugas saja**. ST hanya memberi arahan umum; penajaman dilakukan melalui survey pendahuluan.

### Tujuan Survey Pendahuluan

1. Memahami **desain program**: logika intervensi (input–proses–output–outcome), stakeholder, anggaran
2. Mengidentifikasi **area berisiko kinerja** — indikasi awal ketidakcapaian target, pemborosan, atau hambatan
3. Menajamkan **sasaran audit** agar terukur dan fokus pada risiko signifikan (bukan sekadar "meneliti pelaksanaan program")
4. Menetapkan **ruang lingkup** yang realistis: periode audit, unit/lokasi yang diperiksa, aspek 3E yang diuji, dan batasan
5. Menyusun **hipotesis audit awal** yang akan diuji di KKP

### Input Survey Pendahuluan

Dokumen yang dikumpulkan dan dibaca auditor:
- Dokumen desain program: TOR/KAK, proposal program, logframe
- Proses bisnis internal dan SOP program
- Perjanjian Kinerja (PK) tahun yang diaudit + IKU + target
- LKj tahun lalu dan tahun berjalan (jika ada)
- Laporan monitoring/e-monev program
- DIPA/RKA — alokasi anggaran dan komponen belanja
- Hasil audit/reviu sebelumnya atas program yang sama (jika ada)
- Notulen wawancara awal dengan pengelola program (opsional, didorong)

### Langkah Pelaksanaan Survey Pendahuluan

1. **Pemahaman program** — petakan logika intervensi: Input → Proses → Output → Outcome
2. **Research online — benchmarking & best practice** (lihat subbagian "Research Online" di bawah):
   - Cari benchmark K/L lain di Indonesia yang menjalankan program sejenis
   - Cari best practice internasional (OECD, World Bank, UN, dll) sebagai kriteria pembanding
   - Cari regulasi terbaru & pedoman teknis dari instansi pembina (Bappenas, KemenPAN-RB, Kemenkeu)
   - Cari hasil audit BPK/BPKP sebelumnya atau kajian akademis atas program/sektor sejenis
   - Setiap klaim **WAJIB** disertai URL sumber + tanggal akses
3. **Pemetaan risiko kinerja** — untuk setiap simpul logika **dan setiap aspek dari 8 aspek** (lihat Kerangka Pemeriksaan Multi-Aspek), identifikasi:
   - Risiko efektivitas: target tidak tercapai, output tidak berkualitas, tidak sampai ke penerima manfaat
   - Risiko efisiensi: pemborosan anggaran, overhead tinggi, serapan tidak konsisten dengan progres fisik
   - Risiko data: IKU tidak valid, manipulasi data kinerja, target terlalu rendah
   - *Gunakan temuan research online sebagai input tambahan untuk menajamkan risiko*
4. **Analytical review awal** — bandingkan target vs realisasi (PK vs LKj vs data B12), % serapan vs % capaian fisik, dan **bandingkan juga dengan benchmark K/L lain atau best practice** yang ditemukan di Langkah 2
5. **Identifikasi area fokus** — pilih 2–4 area dengan risiko tertinggi untuk menjadi sasaran audit
6. **Rumuskan sasaran audit** yang SMART — spesifik per area fokus, bukan generik
7. **Tetapkan ruang lingkup** — periode, unit, aspek 3E yang diuji, lokasi sampel, batasan audit
8. **Susun hipotesis audit awal** — dugaan temuan yang akan diuji (sekaligus dasar langkah kerja PKP)

### Research Online — Benchmarking & Best Practice

> **Dasar:** Untuk menghindari audit kinerja yang self-referential (hanya mengacu pada dokumen internal), survey pendahuluan diperkaya dengan referensi eksternal. Namun karena kriteria utama tetap dari proses bisnis internal, research online hanya berfungsi sebagai **konteks pembanding dan penajaman risiko** — bukan sebagai kriteria utama yang dipakai menjustifikasi temuan.

**Empat jenis research yang harus dicari:**

| Jenis | Contoh Query | Kegunaan |
|-------|-------------|----------|
| **Benchmark K/L lain di Indonesia** | "audit kinerja program [sejenis] BPK", "laporan kinerja [program sejenis] kementerian", "LKj [K/L sejenis] [tahun]" | Membandingkan target, realisasi, dan pendekatan K/L sejenis |
| **Best practice internasional** | "OECD best practice [sektor program]", "World Bank performance audit [topik]", "INTOSAI performance audit guideline [topik]" | Standar pembanding untuk menilai kewajaran target & proses |
| **Regulasi & pedoman teknis** | "Permen/SE [instansi pembina] [topik] [tahun]", "Pedoman teknis [program] Bappenas/KemenPAN-RB/Kemenkeu" | Memastikan kriteria internal tidak konflik dengan regulasi terbaru |
| **Hasil audit/riset akademis** | "temuan BPK [program sejenis]", "hasil audit BPKP [sektor]", "kajian [topik program] jurnal" | Dasar hipotesis risiko — area yang sudah terbukti bermasalah di tempat lain |

**Alur research:**

1. Dari `context.md` + TOR/KAK, identifikasi 3–5 kata kunci inti program (nama program, sektor, jenis output, instansi pembina).
2. Jalankan query WebSearch untuk masing-masing dari 4 jenis di atas (minimal 1 query per jenis).
3. Untuk setiap hasil yang relevan, **baca sumber aslinya** (WebFetch) — jangan menyimpulkan hanya dari snippet.
4. Catat untuk setiap temuan research:
   - **Judul sumber** (lengkap)
   - **URL lengkap**
   - **Tanggal akses** (tanggal Claude menjalankan WebSearch/WebFetch)
   - **Ringkasan faktual** (2–4 kalimat, tanpa interpretasi)
   - **Relevansi terhadap program yang diaudit** (1 kalimat)
5. Filter: buang hasil yang tidak relevan, tidak bisa diakses penuh, atau dari sumber non-otoritatif (blog tanpa kredensial, situs komersial SEO).
6. Simpulkan sebagai input untuk Langkah 3 (pemetaan risiko) dan Langkah 4 (analytical review).

**Sumber yang dipercaya (whitelist indikatif):**
- `.go.id` (K/L, BPK, BPKP, Bappenas, KemenPAN-RB, Kemenkeu)
- `bpk.go.id`, `bpkp.go.id` (laporan hasil audit/reviu)
- `oecd.org`, `worldbank.org`, `un.org`, `intosai.org` (best practice internasional)
- Jurnal akademis (`doi.org`, `scholar.google`, repositori universitas)

**Sumber yang ditolak:**
- Blog tanpa identitas penulis yang jelas
- Situs SEO/content farm yang menyalin ulang konten
- Situs berita populer tanpa data primer (hanya kutipan tanpa sumber)
- Media sosial / forum

**Aturan anti-halusinasi untuk research online:**
- **Setiap klaim WAJIB disertai URL + tanggal akses** — tidak ada URL = tandai `[DIISI AUDITOR]`.
- **Jangan parafrasa angka tanpa sumber** — kutipan angka harus mencantumkan laporan sumber + halaman/bagian.
- **Jika sumber tidak dapat diakses penuh** (paywall, 403, PDF rusak) → jangan gunakan snippet sebagai basis klaim; tandai sebagai *"perlu verifikasi oleh auditor"*.
- **Jika research tidak menemukan sumber yang memadai** untuk salah satu dari 4 jenis → nyatakan eksplisit di Memo SP *"Tidak ditemukan sumber memadai untuk [jenis]; auditor diminta memberi arahan"*.
- **Jangan menjadikan hasil research sebagai kriteria tunggal** untuk temuan — research online hanya konteks pembanding; kriteria utama tetap dari proses bisnis/SOP/PK program.

### Output Survey Pendahuluan — Memo Survey Pendahuluan

File: `_SP/SP-[nomor-ST].docx` (disusun sebelum KP + PKP). Struktur minimal:

```
MEMO SURVEY PENDAHULUAN
SP/[nomor-penugasan]/IJ.3/KP.01.06/[bulan]/[tahun]

A. Dasar Penugasan      : [Nomor ST]
B. Program yang Diaudit : [Nama program]
C. Unit Pelaksana       : [Unit]

1. GAMBARAN UMUM PROGRAM
   - Tujuan program (dari TOR/KAK)
   - Logika intervensi (Input → Proses → Output → Outcome)
   - Anggaran dan sumber daya
   - IKU utama dan target PK

2. BENCHMARKING & BEST PRACTICE (Research Online)
   2.1 Benchmark K/L Lain di Indonesia
       | No | Sumber | URL | Tgl Akses | Ringkasan Faktual | Relevansi |
       |----|--------|-----|-----------|-------------------|-----------|
   2.2 Best Practice Internasional (OECD / World Bank / INTOSAI / dll)
       | No | Sumber | URL | Tgl Akses | Ringkasan Faktual | Relevansi |
       |----|--------|-----|-----------|-------------------|-----------|
   2.3 Regulasi & Pedoman Teknis Terbaru (instansi pembina)
       | No | Sumber | URL | Tgl Akses | Ringkasan Faktual | Relevansi |
       |----|--------|-----|-----------|-------------------|-----------|
   2.4 Hasil Audit BPK/BPKP & Riset Akademis atas Program Sejenis
       | No | Sumber | URL | Tgl Akses | Ringkasan Faktual | Relevansi |
       |----|--------|-----|-----------|-------------------|-----------|
   2.5 Catatan sumber yang TIDAK ditemukan / perlu verifikasi auditor
       [daftar eksplisit jenis yang tidak bisa diisi — jangan kosongkan diam-diam]

3. PEMETAAN RISIKO KINERJA (per aspek)
   | No | Aspek (1–8) | Risiko Efektivitas | Risiko Efisiensi | Tingkat Risiko | Dasar Risiko (internal/benchmark) |
   |----|-------------|--------------------|-|----------------|-----------------------------------|

4. ANALYTICAL REVIEW AWAL
   - Target vs realisasi IKU (indikasi awal)
   - % serapan anggaran vs % capaian fisik
   - Perbandingan dengan benchmark K/L lain atau best practice (jika tersedia)
   - Anomali yang teridentifikasi

5. AREA FOKUS AUDIT (hasil prioritas risiko)
   [2–4 area terpilih, sebutkan referensi baris Bagian 2 yang mendukung jika relevan]

6. PENAJAMAN SASARAN AUDIT
   Sasaran dari ST (asli)        : [verbatim]
   Sasaran setelah penajaman     :
     1. [sasaran spesifik per area fokus]
     2. [sasaran spesifik per area fokus]
     ...

7. RUANG LINGKUP TERUKUR
   - Periode diaudit         : [tanggal]
   - Unit/lokasi sampel      : [daftar]
   - Aspek 3E yang diuji     : [Efektivitas / Efisiensi / keduanya]
   - Batasan audit           : [eksplisit]

8. HIPOTESIS AUDIT AWAL
   [dugaan temuan yang akan diuji → dasar langkah kerja PKP]

9. DOKUMEN YANG MASIH DIBUTUHKAN
   [daftar dokumen yang harus diminta sebelum Task 03]

Disusun oleh: [Ketua Tim]         Tanggal: [...]
Disetujui oleh: [Pengendali Teknis] Tanggal: [...]
```

### Aturan Turunan — Sasaran & Ruang Lingkup di KP/PKP

Setelah Memo Survey Pendahuluan disetujui auditor:
- **Sasaran di KP dan PKP WAJIB diambil dari bagian 5 Memo SP** (sasaran hasil penajaman), BUKAN verbatim dari ST
- **Ruang lingkup di KP WAJIB diambil dari bagian 6 Memo SP** (ruang lingkup terukur)
- **Langkah kerja per sasaran di PKP WAJIB diturunkan dari bagian 7 Memo SP** (hipotesis audit awal)
- **Tiap sasaran (KP) & langkah kerja (PKP) menyebut aspek yang disasar** (dari 8 aspek). Inilah yang **mengikat ruang lingkup aspek** saat KKP — agen hanya memeriksa aspek yang tercermin di KP/PKP.
- Jika sasaran hasil penajaman berbeda signifikan dengan sasaran ST, jelaskan alasan penajaman di Memo SP dan mintakan persetujuan auditor

### Batasan Survey Pendahuluan

- Survey pendahuluan **bukan audit** — tidak menghasilkan temuan, hanya hipotesis dan prioritas
- Jangan menyimpulkan ketidakefektifan/ketidakefisienan di tahap ini — hanya menandai area berisiko
- Jika dokumen survey tidak lengkap → minta auditor sediakan; jangan teruskan ke PKP dengan risiko yang belum terpetakan

---

## Kerangka Audit Kinerja

Audit kinerja menelusuri logika program dari input hingga output:

```
Input (anggaran, SDM) → Proses (pelaksanaan) → Output (hasil langsung)
        ↑                        ↑                      ↑
   Efisiensi:               Efisiensi:             Efektivitas:
   apakah sumber daya      apakah proses           apakah output
   digunakan optimal?      berjalan sesuai          tercapai sesuai
                           proses bisnis?           target & standar?
```

**Pertanyaan yang dijawab:**

| Level | Pertanyaan Audit |
|-------|-----------------|
| **Input** | Apakah anggaran dan SDM tersedia sesuai rencana? Apakah ada hambatan di awal? |
| **Proses** | Apakah tahapan pelaksanaan sesuai proses bisnis/SOP? Adakah tahapan yang terlewat atau terhambat? |
| **Output** | Apakah target output tercapai (kuantitas)? Apakah kualitas output sesuai standar? |
| **Efisiensi** | Berapa biaya per unit output? Apakah serapan anggaran konsisten dengan progres fisik? |

---

## Kerangka Pemeriksaan Multi-Aspek (8 Aspek × 3 Lapis)

Audit kinerja itu luas. Untuk sampai pada simpulan **efektivitas & efisiensi (2E)**, auditor menelusuri **rantai penyampaian program beserta enabler-nya**. 8 aspek berikut adalah **lensa** — memahami DI MANA mencari dan bagaimana menelusuri sebab — bukan daftar yang wajib diperiksa seluruhnya.

**Tiga lapis:**
- **HULU (desain):** 1. Kebijakan & Desain Program
- **ENABLER (pengendali & sumber daya):** 2. Tata Kelola & Organisasi · 3. SDM · 4. Sistem, Proses & Teknologi · 5. Anggaran & Aset
- **HILIR (kinerja):** 6. Pelaksanaan & Output · 7. Hasil & Manfaat (Outcome) · 8. Data Kinerja & Pelaporan

| # | Aspek | Pertanyaan audit inti | Sumber kriteria | Teknik & bukti | Kontribusi 2E |
|---|-------|----------------------|-----------------|----------------|---------------|
| 1 | **Kebijakan & Desain Program** | Tujuan & logika intervensi relevan, jelas, koheren dengan kebijakan di atasnya? Teori perubahan masuk akal? | Renstra/RPJMN, regulasi sektor, TOR/proposal, logframe | Reviu desain, analisis logframe, benchmarking K/L sejenis | Efektivitas (akar) |
| 2 | **Tata Kelola & Organisasi** | Kewenangan, akuntabilitas, koordinasi antarunit/stakeholder & manajemen risiko memadai? | Struktur & tusi, SOP koordinasi, kebijakan SPIP (PP 60/2008) | Walkthrough, wawancara, reviu dokumen tata kelola | Efektivitas + Efisiensi |
| 3 | **SDM** | Jumlah & kompetensi pelaksana cukup untuk capai target? Beban kerja wajar? | Analisis Beban Kerja (ABK), standar kompetensi jabatan, PermenPANRB terkait | Analisis beban kerja, data kepegawaian, wawancara | Efisiensi + Efektivitas |
| 4 | **Sistem, Proses & Teknologi** | Proses bisnis/SOP memadai & benar dijalankan? Sistem informasi & data mendukung? | Proses bisnis, SOP/juknis, kebijakan SPBE/aplikasi internal | Process walkthrough, uji pengendalian, telusur sistem | Efisiensi + Efektivitas |
| 5 | **Anggaran & Aset** | Sumber daya cukup, tepat alokasi & dimanfaatkan optimal? | DIPA/RKA, standar biaya, daftar/laporan aset | Serapan vs progres fisik, biaya per output, utilisasi aset | Efisiensi |
| 6 | **Pelaksanaan & Output** | Kegiatan sesuai rencana? Output tercapai (kuantitas **&** kualitas) sesuai standar? | Rencana/jadwal kerja, standar output, TOR | Uji petik output, BAST, cek lapangan, foto | Efektivitas |
| 7 | **Hasil & Manfaat (Outcome)** | Output berubah jadi outcome & sampai ke penerima manfaat? | Target outcome PK/Renstra, indikator dampak | Survei/konfirmasi penerima manfaat, data outcome, analytical review | Efektivitas |
| 8 | **Data Kinerja & Pelaporan** | IKU valid & terukur? Data kinerja jujur (anti-manipulasi / target terlalu rendah)? | Pedoman SAKIP, definisi operasional IKU | Rekalkulasi IKU, telusur ke data mentah, uji konsistensi antarlaporan | Efektivitas (validitas simpulan) |

> Tidak ada aspek "ekonomis" — lingkup skill ini **2E**. Indikasi kewajaran harga/pengadaan → eskalasi `audit-pengadaan`.

### Aspek ditetapkan oleh KP & PKP (bukan dipilih bebas)

**Ruang lingkup aspek yang diaudit = aspek yang tercermin pada SASARAN di Kartu Penugasan (KP) + LANGKAH KERJA di Program Kerja Pengawasan (PKP).** 8 aspek di atas berperan dua kali:
- **Di hulu (perencanaan):** checklist saat survey pendahuluan merumuskan sasaran & langkah kerja → dituangkan ke KP (oleh PT) dan PKP (oleh KT).
- **Di eksekusi (Task 03/KKP):** lensa pemetaan.

**Langkah wajib di awal KKP — Pemetaan Sasaran/Langkah → Aspek:**
1. Baca sasaran di KP dan langkah kerja di `_PKP/sasaran-assignment.json`.
2. Petakan **tiap sasaran & langkah kerja ke aspek** yang relevan (satu sasaran bisa menyentuh >1 aspek).
3. **Hanya periksa aspek yang tercermin di KP/PKP.** Aspek di luar itu TIDAK diaudit.
4. Bila saat pengujian muncul indikasi material pada aspek di luar KP/PKP → **catat sebagai usulan perluasan ruang lingkup ke PT/KT**, jangan langsung audit (jaga batas penugasan).

### Penelusuran Sebab antaraspek (why-tree)

Saat gap kinerja ditemukan di hilir, telusuri sebabnya mundur menembus lapisan — ini membuat kolom **Sebab** sistematis, bukan berhenti di "kurang pengawasan":

```
Gap Efektivitas (aspek 6–7: output/outcome tak tercapai)
   ↑ mengapa?
Enabler gagal? (aspek 2–5: tata kelola / SDM / sistem-proses / anggaran-aset)
   ↑ mengapa?
Berakar di desain/kebijakan? (aspek 1: logika intervensi lemah / target tak realistis)

Paralel — aspek 8 (data): apakah kinerja yang "dilaporkan" memang nyata?
```

---

## Framework Elemen Temuan (CCSAA)

Setiap temuan audit kinerja WAJIB memiliki 5 elemen lengkap:

```
**TEMUAN [NOMOR]: [JUDUL SINGKAT SPESIFIK — masalah kinerja yang ditemukan]**

**Kondisi:**
[Fakta yang ditemukan — data kuantitatif, perbandingan, dokumen sumber.
Contoh: "Realisasi IKU 'Jumlah pengguna layanan digital' baru mencapai 45.000 dari target 100.000
(45%) per 31 Desember 2025 berdasarkan laporan kinerja B12 Nomor xxx."]

**Kriteria:**
[Target yang seharusnya dicapai + dasar penetapannya.
Contoh: "Berdasarkan PK Tahun 2025 yang ditandatangani [nama], target IKU... adalah 100.000 pengguna.
Perpres 29/2014 mengamanatkan instansi mencapai target yang telah ditetapkan dalam PK."]

**Sebab:**
[Analisis akar masalah — mengapa program tidak efektif/efisien/ekonomis.
Kategorikan: kelemahan desain program, hambatan pelaksanaan, kekurangan sumber daya,
faktor eksternal, atau kombinasi.
Contoh: "Penyebab utama tidak tercapainya target adalah: (1) [sebab spesifik dari data];
(2) [sebab spesifik]; (3) [faktor eksternal jika ada]."]

**Akibat:**
[Dampak nyata dari kondisi — kerugian, risiko, ketidakefisienan.
Untuk audit kinerja: dampak terhadap penerima manfaat, pemborosan anggaran, atau risiko strategis.
Contoh: "Akibat tidak tercapainya target, [X] masyarakat tidak mendapat manfaat program.
Biaya per pengguna yang berhasil dijangkau menjadi Rp [Y]/pengguna, dua kali lebih tinggi
dari yang direncanakan (Rp [Z]/pengguna)."]

**Rekomendasi:**
[Tindakan korektif spesifik — redesain program, penguatan kapasitas, perubahan target,
atau alokasi sumber daya ulang. Sebutkan: siapa bertanggung jawab, apa yang dilakukan, kapan.]
```

---

## Format KKP Audit Kinerja

| No | Judul Temuan | Aspek (1–8) | Dimensi (2E) | Kondisi | Kriteria | Sebab | Akibat |
|----|-------------|-------------|--------------|---------|----------|-------|--------|
| 1 | [Judul] | [aspek terkait] | Efektivitas / Efisiensi | [Fakta] | [Target/Acuan] | [Root cause] | [Dampak] |

> Simpan `aspek` & `dimensi` sebagai field di `temuan.json` (metadata + ditampilkan di narasi KKP). Kolom DOCX hasil `render_kkp.py` tidak wajib berubah — penanda aspek boleh muncul di narasi temuan saja.

---

## Format Output Laporan (LHA Kinerja)

```
Bab 1: PENDAHULUAN
       1.1 Latar Belakang
       1.2 Dasar Penugasan
       1.3 Tujuan Audit
       1.4 Pertanyaan Audit (audit questions yang dijawab)
       1.5 Ruang Lingkup dan Metodologi
       1.6 Batasan Audit
       1.7 Komposisi Tim dan Jangka Waktu

Bab 2: GAMBARAN UMUM PROGRAM
       2.1 Tujuan dan Desain Program
       2.2 Logika Intervensi (Input → Output → Outcome)
       2.3 Anggaran dan Sumber Daya
       2.4 Pelaksana dan Mekanisme

Bab 3: METODOLOGI AUDIT KINERJA
       [Pendekatan 3E, teknik pengumpulan bukti, sumber data]

Bab 4: TEMUAN DAN ANALISIS (dilaporkan per dimensi 2E; tiap temuan ditandai aspeknya)
       4.1 Efektivitas Pencapaian Target
           [Temuan CCSAA per isu efektivitas — sebut aspek terkait (mis. Kebijakan & Desain, Pelaksanaan & Output, Outcome, Data Kinerja)]
       4.2 Efisiensi Penggunaan Sumber Daya
           [Temuan per isu efisiensi — sebut aspek terkait (mis. Anggaran & Aset, Sistem-Proses-Teknologi, SDM)]

Bab 5: SIMPULAN
       [Jawaban atas pertanyaan audit — apakah program efektif, efisien, ekonomis?]

Bab 6: REKOMENDASI
       [Matriks: Temuan | Rekomendasi | Penanggung Jawab | Target Waktu]

Lampiran: Daftar Dokumen Sumber, Matriks Temuan Lengkap, Matriks Aspek (1–8) × Dimensi (2E)
```

---

## Panduan Bahasa

- Selalu sertakan **angka dan data** — audit kinerja bersifat kuantitatif
- Sebut sumber data spesifik: nama laporan, nomor, tanggal
- Untuk sebab: analisis mendalam, jangan berhenti di "kurang pengawasan"
- Untuk akibat: hitung dampak konkret (berapa orang, berapa rupiah)
- Gunakan kalimat aktif: "Program tidak mencapai..." bukan "Ditemukan bahwa..."

---

## Batasan

- **Fokus hanya efektivitas dan efisiensi** — jangan masuk ke penilaian kewajaran harga/pengadaan (domain audit-pengadaan)
- **Kriteria dari dokumen program** — jangan gunakan asumsi sendiri tentang "seharusnya bagaimana"; selalu kaitkan dengan proses bisnis/SOP yang diupload
- **Jangan menyimpulkan kecurangan** — audit kinerja bukan audit investigatif; jika ada indikasi fraud → catat dan eskalasi ke pimpinan
- **Jangan melampaui ruang lingkup ST/KP/PKP** — aspek yang diaudit dibatasi sasaran (KP) & langkah kerja (PKP); aspek di luar itu tidak diaudit. Indikasi material di luar lingkup → usulkan perluasan ke PT/KT, jangan langsung audit
- **Sebab harus berbasis bukti** — jangan spekulatif; jika penyebab tidak dapat diverifikasi, nyatakan sebagai area yang perlu investigasi lebih lanjut
- **Data tidak tersedia = keterbatasan** — jika data kinerja tidak dapat diakses, nyatakan sebagai batasan audit; JANGAN isi dengan estimasi
- **Rekomendasi realistis** — harus dalam kewenangan auditan untuk melaksanakan

---

## Panduan Membangun Sub-Skill Program

Ketika auditor akan membangun sub-skill baru untuk program tertentu, gunakan struktur berikut:

```
audit-kinerja-[nama-program]/
  SKILL.md               → Identitas + ref ke skill induk ini + kriteria spesifik program
  references/
    01-proses-bisnis.md  → Dikonversi dari dokumen proses bisnis yang diupload
    02-sop-[nama].md     → SOP atau juknis spesifik (jika ada, bisa lebih dari 1 file)
    03-target-iku.md     → IKU dan target dari PK tahun berjalan (opsional, bisa diupdate tiap tahun)
```

**Template SKILL.md sub-skill:**
```markdown
---
name: audit-kinerja-[nama-program]
version: 1.0
parent-skill: audit-kinerja
---
# Audit Kinerja: [Nama Program]

## Identitas Program
- Nama program/kegiatan: [...]
- Unit pelaksana: [...]
- IKU utama: [...]
- Periode yang diaudit: [...]

## Kriteria Spesifik Program (organisir per aspek yang relevan dari 8 aspek)
[Diisi dari proses bisnis internal — tahapan kerja, standar output, target. Kelompokkan per aspek yang disasar program ini, mis. Kebijakan & Desain, Sistem-Proses-Teknologi, Pelaksanaan & Output, Outcome, Data Kinerja]

## Referensi
| Dokumen | File |
|---------|------|
| Proses bisnis internal | references/01-proses-bisnis.md |
| SOP [...] | references/02-sop-[nama].md |

## Catatan Khusus Program
[Hal-hal unik yang perlu diperhatikan auditor untuk program ini]
```
