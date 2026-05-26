# Korpus Ujicoba Digestion

Tempat menaruh dokumen untuk menguji pipeline **digestion** (TOR/RAB/KAK/HPS/RFI/KONTRAK → JSON).

## Cara pakai
1. **Taruh PDF** di subfolder sesuai jenisnya:
   ```
   digest-test-corpus/
   ├── tor/        ← TOR / KAK perencanaan (digest_tor, per-file)
   ├── rab/        ← RAB (digest_rab, per-file)
   ├── kak/        ← KAK pengadaan ┐
   ├── hps/        ← HPS           │ digest_pengadaan (folder-level,
   ├── rfi/        ← RFI vendor    │ KAK+HPS+RFI+Kontrak digabung)
   └── kontrak/    ← Kontrak       ┘
   ```
   (Boleh juga flat di root korpus bila nama file diawali `TOR-/RAB-/KAK-/HPS-/RFI-/KONTRAK-`.)
2. **Jalankan**: `./digest-test-corpus/run.sh`  (atau lihat `backend/scripts/README.md`).
3. Baca ringkasan konsol + `_digest-test/report.md`. Fokus ke bagian **"PERLU PERHATIAN"**:
   gagal / kosong (PDF scan → perlu OCR) / field kunci hilang / golden meleset.

## golden.json (opsional — ukur akurasi)
Anotasi nilai-harapan untuk **sebagian** dokumen → harness menilai akurasi ekstraksi
(substring, case-insensitive, dicocokkan ke JSON digest). Edit `golden.json` di folder ini.
Template lengkap: `backend/scripts/golden.example.json`.

## Catatan
- Dokumen di folder ini **tidak di-commit** (lihat `.gitignore`) — aman untuk dokumen
  internal/rahasia. Hanya struktur folder + README + golden.json yang ter-track.
- Output `_digest-test/` juga tidak di-commit.
