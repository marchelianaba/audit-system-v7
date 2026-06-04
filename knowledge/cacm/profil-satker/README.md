# Profil Satker untuk CACM Semantic Anomaly Detection

> **STATUS: DRAFT pre-implementation (3 Juni 2026)**
> Folder ini dipersiapkan untuk kriteria CACM kelas 2 (semantic anomaly).
> Lihat rencana di [`docs/rencana-cacm-kriteria.html`](../../../docs/rencana-cacm-kriteria.html) §2.5.1.

Setiap file `<kode>.yaml` di sini = profil 1 Satker auditee, dipakai evaluator CACM
untuk menilai "apakah paket X sesuai dgn tupoksi Direktorat Y?".

## Konvensi kode

- `itjen` — Inspektorat Jenderal (auditor sendiri, tetap diisi untuk konsistensi)
- `ekosdig` — Direktorat Jenderal Pengembangan Ekosistem Digital
- `wasdig` — Direktorat Jenderal Pengawasan Ruang Digital
- (kode Direktorat di bawah Ditjen — tambah saat workshop)

## Field wajib

Lihat `wasdig.yaml` sebagai sample lengkap:
- `kode`, `nama`, `kementerian`, `sumber_profil`, `revisi`
- `tupoksi[]` — bidang inti
- `pengadaan_wajar.{kategori}.[]` — barang/jasa wajar
- `pengadaan_anomali_jelas[]` — anti-pattern (untuk akselerasi MERAH)
- `pengecualian[]` — whitelist khusus

## Source profil

Workshop tim 3-7 Jun 2026 — tarik dari:
- Renstra Komdigi 2025-2029
- Permenkomdigi 1/2025 (SOTK)
- RKA-K/L per Satker (program & kegiatan)
- Notulen rapat unit (kalau ada profil internal)

## Update policy

- Revisi via PR (Git audit trail)
- Major revisi tiap SOTK berubah / TA baru
- Minor revisi: tambah pengecualian / fine-tune anti-pattern setelah false-positive review

---

*Implementasi belum dimulai — file di sini hanya seed/sample untuk fase 2 rilis (lihat ROADMAP).*
