---
jenis: kp_template
skill: reviu-pengadaan
versi: 1.0
output_format: docx
field_required:
  - nomor_st
  - tanggal_st
  - judul_penugasan
  - tujuan_pengawasan
  - ruang_lingkup
  - jadwal_mulai
  - jadwal_selesai
  - tim_pengawasan
field_optional:
  - referensi_regulasi
  - dasar_penugasan_tambahan
  - catatan_pt
---

# Kartu Penugasan — Reviu Pengadaan

## Identitas Penugasan

- **Nomor Surat Tugas**: {{nomor_st}}
- **Tanggal Surat Tugas**: {{tanggal_st}}
- **Judul Penugasan**: {{judul_penugasan}}

## Dasar Hukum & Referensi Regulasi

Perpres 16/2018 jo. Perpres 12/2021

{{#referensi_regulasi}}
Tambahan referensi yang dirujuk auditor: {{referensi_regulasi}}
{{/referensi_regulasi}}

## Tujuan Pengawasan

{{tujuan_pengawasan}}

Tujuan baku skill ini: Memberikan keyakinan terbatas atas perencanaan pengadaan & kewajaran HPS.

## Ruang Lingkup

{{ruang_lingkup}}

Ruang lingkup baku: Dokumen perencanaan pengadaan: KAK, HPS, RFI vendor, rancangan kontrak.

## Jadwal Pelaksanaan

- **Mulai**: {{jadwal_mulai}}
- **Selesai**: {{jadwal_selesai}}

## Tim Pengawasan

{{tim_pengawasan}}

## Catatan Pengendali Teknis

{{catatan_pt}}

---

*Template ini diisi oleh Pengendali Teknis (PT) saat tahapan 1 penugasan baru. Setelah disimpan, KT akan mendetailkan menjadi Program Kerja Pengawasan (PKP).*
