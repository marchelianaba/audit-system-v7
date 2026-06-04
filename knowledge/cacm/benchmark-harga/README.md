# Benchmark Harga untuk CACM Unit-Cost Evaluation

> **STATUS: DRAFT pre-implementation (3 Juni 2026)**
> Folder ini dipersiapkan untuk kriteria CACM kelas 3 (benchmark unit-cost).
> Lihat rencana di [`docs/rencana-cacm-kriteria.html`](../../../docs/rencana-cacm-kriteria.html) §2.5.2.

Setiap file `<kategori>.yaml` di sini = benchmark distribusi harga untuk 1 kategori barang/jasa,
dipakai evaluator CACM untuk menilai "apakah harga per unit paket X wajar?".

## Konvensi kategori

Format `<jenis>-<varian>` lowercase + dash. Contoh: `laptop-developer`, `server-rack-1u`,
`lisensi-firewall-enterprise`, `jasa-konsultansi-iso27001`.

## Field wajib

Lihat `laptop-developer.yaml` sebagai sample lengkap:
- `kategori_kode`, `kategori_nama`, `satuan`, `periode_berlaku`, `revisi`
- `sumber[]` — referensi (e-katalog, historis, survei pasar)
- `harga.{min, p25, median, p75, max}` — distribusi rupiah
- `threshold_deviasi[]` — MERAH/KUNING/HIJAU condition
- `keyword_pemicu[]` — match dgn `nama_paket`
- `keyword_exclude[]` — anti-match

## Source benchmark (urutan prioritas)

1. **e-Katalog LKPP** — kategori standar. Scraping by-kategori, semi-manual.
2. **Historis pengadaan Komdigi 2024-2025** — paket yang lulus QC (tidak di-flag MERAH).
3. **SBM Kemenkeu** — untuk komponen umum (honorarium, transport).
4. **Survei pasar (Tokopedia/Bhinneka)** — top vendor B2B Indonesia.

## Lifecycle

- **Seed awal:** workshop tim 3-7 Jun 2026 isi 20-30 kategori paling sering.
- **Update periodik:** quarterly, auditor PT/PM review p25/p75 vs realita.
- **Auto-update (Fase 3+):** setelah 6-12 bulan data SPSE terkumpul, build moving-window median (rolling 18 bulan) sebagai sumber baru.

## Limitasi diketahui

- SIRUP publik tidak ada unit_count + unit_cost — hanya pagu total paket.
  Kriteria benchmark AKTIF saat **F3 SPSE** hidup (rincian kontrak) atau saat
  auditor input rincian manual via reviu pengadaan.
- Override per-Satker mungkin diperlukan (mis. Wasdig butuh workstation high-end
  untuk forensik — threshold MERAH naik). Field `override_per_satker` bisa
  ditambah saat Fase 5 UI editor hidup.

---

*Implementasi belum dimulai — file di sini hanya seed/sample untuk fase 3 rilis (lihat ROADMAP).*
