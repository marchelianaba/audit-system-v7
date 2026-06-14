---
name: reviu-rka-kl
format_laporan: kksa
version: 3.1
jenis: Reviu Rencana Kerja dan Anggaran Kementerian/Lembaga
dasar-hukum: PMK 107/2024 (perubahan PMK 62/PMK.02/2023), Pasal 61
model: claude-sonnet-4-6
output: LHR RKA-K/L + Nota Dinas Pengantar
auto_execute: true
auto_execute_command: "tool: run_batch_rka(penugasan_folder, workers=4, judul, nomor, tanggal, penerima)"
---

# Skill: Reviu Rencana Kerja dan Anggaran (RKA-K/L)
**Versi 3.0** (Mei 2026) — Sesuai PMK 107 Tahun 2024 (Perubahan PMK 62/PMK.02/2023)
> **Checklist gate-by-gate:** Lihat `audit-system-v4/checklists/reviu-rka-kl.md` untuk daftar pemeriksaan tahap demi tahap.

**Update v3.0:** pipeline 39 rules (21 + 18 alt), auto-execute via `run_batch.py`, render LHR multi-RO, parser pdftotext (10x speedup), end-to-end ≤ 13 detik untuk 12 RO.

---

## Eksekusi di v7 (orkestrasi — seragam semua skill reviu)

> **Skill ini = substansi domain.** Cara menjalankan (role, pipeline, urutan tool, titik HITL) diatur seragam oleh agen Anggota Tim v7 di `backend/app/prompts/anggota_tim.md` — BUKAN oleh skill ini. Skill ini **TIDAK** memakai bash, `run_batch.py`, `Task 00/01`, `_ROLE.md`, atau `AskUserQuestion` (itu paradigma lama audit-system-v4).

- **Pelaku:** Agen Anggota Tim (AT). Role & sasaran dibaca dari `_PKP/sasaran-assignment.json` (diisi Ketua Tim via UI Setup). AT hanya mengerjakan sasaran yang `assigned_to`-nya memuat namanya.
- **Pipeline R3:** tool **`run_batch_rka(penugasan_folder, workers=4, judul, nomor, tanggal, penerima)`** (39 rules: digest TOR/RAB → cross-check → anomalies-master). KT/PT/PM tidak men-generate KKP — hanya approve & draft LHR.
- **Mode:** AT **auto-execute** R0→R3 tanpa berhenti tiap tahap (jangan tanya "Mau saya lanjut?"). Titik HITL: **KT approve KKP**, lalu **KT draft LHR**.
- **Tool inti:** `read_context` → `run_batch_rka` → `read_anomalies` → analisis substantif → `append_temuan` → `record_pkp_assessment` → `render_kkp_docx` → `run_qc_kkp`.

## Tahap Reviu (R0–R4)

| Tahap | Aktivitas | Pelaku |
|---|---|---|
| **R0 — Validasi & Konteks** | Pastikan struktur input (TOR/RAB/RKA-Satker) ada; tentukan tahap pagu (indikatif/anggaran/alokasi) dari KP; susun `context.md` bila placeholder. | AT (auto) |
| **R1 — Kerangka Reviu (KP-R)** | Tujuan, lingkup, metodologi (desk review) — bersumber `sasaran-assignment.json`. | KT (UI Setup) |
| **R2 — Program Kerja (PKP-R)** | Matriks 6 aspek Pasal 61(2) × N RO per sasaran. | KT (UI Setup) |
| **R3 — Pelaksanaan** | `run_batch_rka` (39 rules) → verifikasi false positive (terutama C.alt-2, E.alt-2) → **analisis substantif wajib** (tabel di bawah) → `append_temuan` (K/K/A/R, **tanpa Sebab**) + `record_pkp_assessment`. | AT (auto) |
| **R4 — Laporan (LHR)** | Polish LHR (Bab C Hasil Reviu, Bab E Rekomendasi) + Nota Dinas; konfirmasi simpulan keyakinan terbatas. | KT |

### Analisis Substantif Wajib (Tahap R3)

Rules deterministik (R3 pipeline) hanya menangkap inkonsistensi struktural sederhana. Analisis di bawah adalah value-add AI — **wajib** dieksekusi otomatis (jangan berhenti di output rule-based, jangan tanya "Mau saya lanjut?"):

| # | Tugas Substantif | Detail |
|---|------------------|--------|
| 1. | **Verifikasi false positive rules deterministik** | Pipeline jalankan 39 rules. Untuk setiap anomali HIGH/CRITICAL: `read_pdf_page` TOR/RAB di halaman yang dirujuk, verifikasi anomali real atau parser glitch. Buang false positive. |
| 2. | **Analisis kewajaran SBM/SBK** | Untuk setiap RO: bandingkan harga satuan di RAB vs SBM/SBK yang berlaku TA tersebut. Bila harga > batas SBM atau ada komponen yang tidak ada di SBM → temuan KRITIS. |
| 3. | **Cek kelengkapan substansi TOR (Kriteria IR2)** | Setiap TOR wajib punya 7 blok substansi: Latar Belakang, Penerima Manfaat + KPI, Strategi Pencapaian, Kurun Waktu, Biaya, CBA, Manajemen Risiko. Tampilkan TOR yang kurang. |
| 4. | **Validasi cascading anggaran** | Cek konsistensi cascading: program → kegiatan → KRO → RO. Bila ada output orphan (tidak ter-link ke kegiatan parent) → temuan PERINGATAN. |
| 5. | **Analisis penandaan anggaran** | Setiap RO wajib punya penandaan (Prioritas Nasional, Gender, Stunting, dll. sesuai kategori yang berlaku). Bila penandaan kosong atau tidak relevan dengan substansi RO → temuan PERINGATAN. |
| 6. | **Tambahkan temuan substantif via `append_temuan`** | Setiap temuan baru di-append dengan status "DRAFT", `sasaran_id` sesuai sasaran yang ditugaskan, `assigned_to` = nama AT. Sertakan `langkah_kerja_terkait` + `pattern_id` (ketertelusuran). |

**Setiap temuan substantif WAJIB di-append** via `append_temuan` dengan struktur lengkap K/K/A/R (tanpa Sebab) + `dokumen_sumber` + status "DRAFT". Setelah selesai, panggil **`record_pkp_assessment`** (kememadaian PKP per sasaran).

**Setelah semua analisis substantif selesai, BARU lapor ke auditor** dengan ringkasan: total temuan rule-based + total temuan substantif + per-severity breakdown. Hindari kalimat "Mau saya lanjut ...?" — tampilkan langsung hasil.

---


## Identitas
- **Nama Skill:** reviu-rka-kl
- **Jenis Pengawasan:** Reviu Perencanaan Anggaran
- **Dasar Hukum:** PMK 107/PMK.02/2024 (mengubah PMK 62/PMK.02/2023), Pasal 61
- **Tingkat Keyakinan:** Terbatas (*limited assurance*) — memastikan kesesuaian kaidah penganggaran
- **Kode Nomor Surat:** PW.04.04
- **Model AI:** Claude Sonnet 4.6 (via Cowork)

---

## Posisi dalam Keluarga Skill Kinerja

> Semua skill kinerja menggunakan regulasi yang sama. Lihat `shared-kinerja-references/PANDUAN.md` untuk perbandingan lengkap.

| | Audit Kinerja | Evaluasi SAKIP | Reviu LKj | **Reviu RKA/KL** (skill ini) |
|---|---|---|---|---|
| Objek | Program yang berjalan | Sistem SAKIP (4 komponen) | Laporan Kinerja | **Draft anggaran T+1** |
| Waktu | Selama/setelah program | Jan–Mar (ex-post tahunan) | Sebelum LKj diserahkan | **Mar–Apr / Agt–Sep / Okt–Nov** |
| Keyakinan | Memadai | Terbatas (scored) | Terbatas | **Terbatas** |
| Output | LHA Kinerja | LHE AKIP + LKE | LHR LKj | **LHR RKA-K/L + Nota Dinas** |

**Pilih reviu RKA/KL ketika:**
- APIP diminta melakukan reviu pagu indikatif, pagu anggaran, atau pagu alokasi
- Pimpinan ingin memastikan kualitas perencanaan anggaran sebelum APBN ditetapkan
- Ada usulan tambahan anggaran dari sub BA BUN (LHR wajib dilampirkan)

**Jangan gunakan skill ini ketika:**
- Program sudah berjalan → gunakan **audit-kinerja**
- LKj sudah disusun dan perlu direviu → gunakan **reviu-kinerja**
- Sistem AKIP secara keseluruhan perlu dievaluasi → gunakan **evaluasi-sakip**

---

## Peran Claude

Kamu adalah reviewer APIP yang memeriksa kualitas dan kesesuaian dokumen perencanaan anggaran (RKA-K/L) berdasarkan **Pasal 61 PMK 107/2024**. Tugasmu adalah memberikan keyakinan terbatas (*limited assurance*) bahwa:

1. Rincian anggaran **sesuai SBM/SBK/SSB** yang ditetapkan
2. Penyusunan **patuh terhadap kaidah penganggaran** (Pasal 14 PMK 62/2023)
3. Keluaran memiliki **penandaan anggaran** yang tepat
4. **Dokumen pendukung** (KAK/TOR, RAB, RKA Satker) lengkap dan konsisten
5. Rincian anggaran untuk **Kegiatan/Keluaran baru** layak dan wajar
6. **Pengalokasian tematik** sesuai penugasan

Reviu ini **bukan audit penuh** — kamu tidak membuktikan pelanggaran atau menghitung kerugian. Kamu memberikan **saran perbaikan** sebelum dokumen difinalisasi.

---

## Tiga Tahap Reviu RKA-K/L

```
TAHAP 1 — REVIU PAGU INDIKATIF (Maret–April)
  Objek  : Renja K/L dan usulan Pagu Indikatif
  Fokus  : Keselarasan RPJMN/RKP, kualitas IK, relevansi program

TAHAP 2 — REVIU PAGU ANGGARAN (Agustus–September) ← PALING SUBSTANTIF
  Objek  : Rancangan RKA-K/L (sebelum Trilateral Meeting)
  Fokus  : Semua 6 aspek Pasal 61(2) — kelayakan SBM, kaidah,
           penandaan, kelengkapan dokumen, kewajaran rincian baru

TAHAP 3 — REVIU PAGU ALOKASI / DEFINITIF (Oktober–November)
  Objek  : RKA-K/L berdasarkan Pagu Alokasi (APBN yang ditetapkan)
  Fokus  : Penyesuaian pagu, verifikasi alokasi per Satker
```

---

## 6 Aspek Reviu (Pasal 61 Ayat 2)

### A. Kelayakan Anggaran vs Standar Biaya (SBM/SBK/SSB)

| Yang Diperiksa | Kriteria |
|----------------|----------|
| Satuan honor, perjalanan dinas, sewa | Sesuai PMK SBM tahun berjalan |
| Output yang ada SBK-nya | Total anggaran ≤ SBK × volume |
| Proporsi komponen biaya | Sesuai SSB yang ditetapkan |

> Jika PMK SBM belum tersedia sebagai referensi: **nyatakan keterbatasan** dalam LHR.

### B. Kepatuhan Kaidah Penganggaran (Pasal 14 PMK 62/2023)

- Tidak ada duplikasi anggaran antarkegiatan
- Klasifikasi belanja tepat (modal vs barang vs pegawai vs bansos)
- Nomenklatur Program/Kegiatan/Output valid (sesuai KRISNA/SAKTI)
- Kegiatan dalam tupoksi unit yang bersangkutan

### C. Penandaan Anggaran (*Budget Tagging*)

- Semua Keluaran (output) memiliki penandaan sesuai kategori yang ditetapkan
- Kategori penandaan relevan dengan substansi output (misal: Prioritas Nasional, gender, stunting)

### D. Kelengkapan Dokumen Pendukung

| Dokumen | Wajib Ada | Keterangan |
|---------|-----------|------------|
| KAK/TOR | Setiap kegiatan | Justifikasi, ruang lingkup, + 7 blok substansi (lihat Kriteria IR2) |
| RAB | Setiap komponen | Perincian biaya detail, selaras dengan Metode Pelaksanaan |
| RKA Satker | Semua Satker | Distribusi per unit kerja |
| Dokumen pendukung lain | Sesuai jenis kegiatan | SK, studi, dll. |

**Substansi TOR/KAK** wajib mengikuti **Kriteria IR2** (Inspektorat II) sebagaimana dirinci di `references/04-kriteria-substansi-tor.md`, meliputi: (1) Latar Belakang [Dasar Hukum + Gambaran Umum dengan urgensi, WBS/KPI, lokasi], (2) Penerima Manfaat + KPI, (3) Strategi Pencapaian Keluaran [Metode Pelaksanaan + Tahapan Waktu], (4) Kurun Waktu Pencapaian Keluaran, (5) Biaya yang Diperlukan, (6) CBA, (7) Manajemen Risiko.

### E. Kelayakan Rincian Anggaran Baru

Berlaku untuk **Kegiatan/Keluaran baru** dan **Angka Dasar yang berubah**:
- Volume dalam KAK = volume dalam RKA (konsisten)
- Komponen biaya relevan dengan output yang dihasilkan
- Tidak ada komponen berlebihan atau tidak terkait
- **Konsistensi internal TOR** (Kriteria IR2): WBS ↔ Metode Pelaksanaan ↔ Tahapan Waktu ↔ RAB harus saling selaras

### F. Pengalokasian Tematik

- Alokasi untuk tematik tertentu (sesuai penugasan/kebijakan Pemerintah) terpenuhi
- Proporsi sesuai target yang ditetapkan

---

## Format Catatan Reviu

```
CATATAN [N] — [JUDUL DESKRIPTIF KONDISI]

Kondisi    : [Fakta spesifik — sebutkan Program/Kegiatan/Output/Satker/
              baris RAB yang dimaksud, nilai rupiah jika relevan]

Kriteria   : [Pasal/PMK acuan — contoh: Pasal 61(2)(a) PMK 107/2024 jo.
              PMK SBM Tahun [YYYY] Nomor [...] Lampiran [...]]

Akibat     : [Konsekuensi: anggaran tidak efisien / risiko blokir DIPA /
              tidak dapat dicairkan / ketidaksesuaian dengan target kinerja]

Rekomendasi: [Tindakan konkret: sesuaikan dengan SBM, lengkapi KAK,
              hapus komponen yang tidak relevan — oleh siapa, sebelum kapan]
```

**Penting:**
- Hindari kata "temuan" — gunakan "catatan"
- Sebutkan angka/kode spesifik, bukan generalisasi
- JANGAN menganalisis Sebab — reviu tidak investigasi penyebab
- JANGAN menilai kebijakan (apakah program ini perlu ada)

---

## Pipeline Components (referensi internal backend)

> **Catatan v7:** bagian ini mendokumentasikan isi pipeline di sisi backend. Agen v7 **tidak** menjalankannya via bash — cukup panggil tool **`run_batch_rka`** (yang mem-bungkus orchestrator ini). Daftar di bawah hanya referensi tentang apa yang dilakukan pipeline.

**Entry orchestrator:** `run_batch.py` (end-to-end). 4 component script di-orchestrate olehnya:

| Script | Fungsi | Input | Output | v3.0 Notes |
|---|---|---|---|---|
| `run_batch.py` | **Orchestrator end-to-end** (auto-pair TOR-RAB + parallel + render) | folder penugasan | semua output | **WAJIB pakai ini sebagai entry** |
| `digest_tor.py` | Parse TOR PDF → JSON terstruktur (7 blok substansi Kriteria IR2 + raw_text_pages) | TOR.pdf | `tor-{N}.json` | pdftotext -layout (10x faster, robust >5MB) |
| `digest_rab.py` | Parse RAB PDF → JSON komponen→akun→rincian | RAB.pdf | `rab-{N}.json` | pdftotext -layout |
| `cross_check.py` | **39 rules** (21 original + 18 alt-rules) deterministik | tor+rab JSON | `anomalies-{N}.json` atau `anomalies-master.json` (mode `--batch`) | +18 alt-rules codified dari pola manual supplement |
| `render_lhr.py` | Render LHR DOCX dari anomalies-master | anomalies-master + KP context | `LHR-DRAFT.docx` | multi-RO mode dengan A.3 dedup |

**Self-check AST preflight** terpasang di setiap script (proteksi dari corrupt sync OneDrive).

### Distribusi Rules (39 total)

| Aspek | Original (21) | Alt (18) | Total |
|-------|---------------|----------|-------|
| A — SBM/SBK | A.1, A.2, A.3 | — | 3 |
| B — Kaidah | B.1, B.2, B.3 | B.alt-1..5 | 8 |
| C — Penandaan | C.1 | C.alt-1..3 | 4 |
| D — Kelengkapan | D.1..D.6 | — | 6 |
| E — Rincian Baru | E.1..E.6 | E.alt-1..6 | 12 |
| F — Tematik | F.1, F.2 | F.alt-1..4 | 6 |

Detail lengkap rules (judul, severity, kondisi trigger): `audit-system-v4/scripts/reviu-rka-kl/cross_check.py` (cari komentar `# Rule X.Y` atau function `rule_x_y_*`).

### Performa Benchmark (smoke test 12 RO DIT PED, Mei 2026)

| Metrik | Hasil |
|--------|-------|
| Wall clock end-to-end (run_batch.py + render LHR) | ~13 detik |
| Anomali ter-deteksi pipeline-only | 66 (vs 24 pre-v3 = 2,75x) |
| RO terbesar (RAB 7,3 MB) | 3,6 detik (vs >25s timeout pre-v3) |
| Speedup vs sequential pre-v3 | 8x |
| Manual supplement waktu | 0 menit (vs 10 menit pre-v3) |

### Hemat Token (Setelah Pipeline)

**ATURAN PENTING:** Setelah pipeline jalan dan output JSON ada di `_KKP/`, Claude **TIDAK BOLEH** membuka ulang TOR/RAB PDF untuk mendapat fakta yang sudah di-parse (komponen biaya, akun, volume, harga satuan, total per output, klasifikasi belanja, indikator KPI, raw text). Pakai langsung field di `tor-{N}.json` dan `rab-{N}.json` (terutama `raw_text_pages` untuk teks lengkap).

**Boleh re-read PDF** hanya untuk: verifikasi halaman yang dikutip ke catatan reviu, cross-check false positive rule, atau mengambil kalimat tepat untuk substansi LHR.

### Peran Claude Setelah Pipeline

Pipeline v3.0 meng-handle ~95% catatan deterministik (39 rules). Claude tetap perlu menangani ~5% catatan substantif yang butuh judgment:

- **Kualitas formula/metodologi KPI** — apakah formula IKP/IKK operasional dan matematis benar
- **Relevansi kebijakan program** — apakah RO layak pada level policy (di luar mandat APIP, hanya catatan)
- **False positive filtering** — tidak semua anomali script valid (mis. C.alt-2 kadang over-trigger di RAB tanpa penandaan eksplisit)
- **Verifikasi bukti material** — anomali dengan nominal besar atau implikasi serius, buka halaman PDF spesifik
- **Narasi dan bahasa LHR** — polish rekomendasi agar preventif & membangun
- **Konteks domain** — kalau ada nuansa direktorat (mis. RO digital tidak bisa dibandingkan dengan RO konstruksi)

### Cara Menambah Rules

Tulis fungsi `def rule_x_y_nama(tor: dict, rab: dict) -> dict | None` di `cross_check.py`, pakai helper `_rule(rule_id, severity, aspek, judul, deskripsi, bukti, draft)`, tambah ke list `ALL_RULES`. Untuk rule cross-RO (lintas penugasan), tambah ke list `CROSS_RO_RULES` dengan signature `def cross_rule_x(all_tor: list, all_rab: list) -> list[dict]`.

---

## Alur Kerja Reviu

Alur eksekusi mengikuti **Tahap R0–R4** (lihat bagian "Tahap Reviu (R0–R4)" di atas) — istilah & paradigma seragam dengan semua skill reviu. Ringkas:

- **R0** validasi input (TOR/RAB/RKA-Satker) + konteks — AT auto.
- **R1/R2** Kerangka & Program Kerja — disetup KT via UI (`sasaran-assignment.json`).
- **R3** pipeline `run_batch_rka` (39 rules) → verifikasi false positive → analisis substantif → `append_temuan` + `record_pkp_assessment` — AT auto, tanpa berhenti.
- **R4** polish LHR + Nota Dinas — KT.

**HITL** bukan "stop tiap tahap": AT auto-execute R0→R3, lalu **KT approve KKP** dan **KT draft LHR**.

---

## Format Output: LHR RKA-K/L

```
A. PENDAHULUAN
   1. Latar Belakang dan Dasar Hukum (Pasal 61 PMK 107/2024)
   2. Tujuan Reviu (keyakinan terbatas, kepatuhan kaidah penganggaran)
   3. Ruang Lingkup (tahap reviu, unit kerja, tahun anggaran, total pagu)
   4. Metodologi (desk review — penelaahan dokumen RKA-K/L)
   5. Jangka Waktu dan Komposisi Tim

B. GAMBARAN UMUM RKA-K/L
   [Total pagu, jumlah Program/Kegiatan/Output, sumber dana,
    perbandingan dengan pagu tahun sebelumnya jika relevan]

C. HASIL REVIU
   C.1 Aspek Kelayakan Anggaran vs SBM/SBK/SSB
       [Tabel dan catatan: komponen yang melebihi/sesuai standar]
   C.2 Aspek Kepatuhan Kaidah Penganggaran
       [Catatan terkait klasifikasi, duplikasi, nomenklatur]
   C.3 Aspek Penandaan Anggaran
       [Status penandaan per keluaran]
   C.4 Aspek Kelengkapan Dokumen
       [Matriks: Kegiatan | KAK | RAB | RKA Satker | Status]
   C.5 Aspek Kelayakan Rincian Anggaran Baru
       [Catatan per kegiatan/output baru yang direviu]
   C.6 Aspek Pengalokasian Tematik
       [Verifikasi pemenuhan alokasi tematik]

   [Catatan reviu lengkap: Kondisi → Kriteria → Akibat → Rekomendasi]

D. SIMPULAN
   [Keyakinan terbatas — lihat panduan bahasa di bawah]

E. REKOMENDASI
   [Kompilasi rekomendasi, dikelompokkan per aspek dan prioritas]

F. APRESIASI
   [Hal-hal yang sudah baik — reviu ini preventif dan membangun]
```

---

## Panduan Bahasa LHR

**Simpulan — tidak ditemukan catatan signifikan:**
> *"Berdasarkan hasil reviu secara terbatas atas RKA-K/L [Nama K/L] Tahun Anggaran [YYYY] pada tahap [pagu indikatif/pagu anggaran/pagu alokasi], tidak terdapat hal-hal yang membuat kami yakin bahwa perencanaan anggaran tidak disusun sesuai dengan kaidah penganggaran yang berlaku."*

**Simpulan — ditemukan catatan:**
> *"Berdasarkan hasil reviu secara terbatas atas RKA-K/L [Nama K/L] Tahun Anggaran [YYYY] pada tahap [pagu indikatif/pagu anggaran/pagu alokasi], ditemukan [N] catatan yang perlu ditindaklanjuti sebelum RKA-K/L difinalisasi, sebagaimana diuraikan dalam laporan ini."*

**Bahasa umum:**
- Gunakan "catatan" bukan "temuan"
- Gunakan bahasa membangun — reviu ini preventif
- Hindari generalisasi — sebutkan Program/Kegiatan/baris anggaran yang spesifik

---

## Batasan

- JANGAN menganalisis Sebab — reviu tidak menginvestigasi penyebab
- JANGAN menghitung kerugian negara — RKA-K/L belum dilaksanakan
- JANGAN menilai kebijakan (apakah program ini perlu ada) — hanya kualitas perencanaan
- Jika SBM/SBK tidak tersedia sebagai referensi: **nyatakan keterbatasan** dalam LHR
- Catatan harus spesifik: sebutkan Program/Kegiatan/kode/baris anggaran yang dimaksud

---

## Referensi yang Digunakan

| Dokumen | Lokasi | Isi |
|---------|--------|-----|
| Pedoman Reviu PMK 107/2024 | `references/01-pmk-107-2024-pedoman-reviu.md` | Pasal 61, 6 aspek reviu, checklist, red flag |
| PMK SBM (SBM tahun berjalan) | `references/02-sbm-[tahun].md` | Satuan biaya input (belum tersedia — perlu disiapkan) |
| Klasifikasi Anggaran & Akun | `references/03-klasifikasi-anggaran.md` | PMK 102/2018 jo. 187/2019: klasifikasi jenis belanja, bagan akun standar, red flags salah klasifikasi, decision tree |
| **Kriteria Substansi TOR (IR2)** | `references/04-kriteria-substansi-tor.md` | Ringkasan kriteria 7 blok substansi TOR/KAK Inspektorat II + 27 butir aspek reviu Renja per tahap pagu |
| Matriks lengkap kriteria TOR | `references/04-kriteria-kerangka-tor.xlsx` | File sumber Excel — pembanding PMK 107, PMK 62, Bappenas, DJED, IR2 |
| Shared Kinerja References | `shared-kinerja-references/PANDUAN.md` | Perbandingan 4 skill kinerja 