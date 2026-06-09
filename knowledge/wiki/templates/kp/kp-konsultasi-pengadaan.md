---
jenis: kp_template
skill: konsultasi-pengadaan
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

# Kartu Penugasan — Pendampingan Pengadaan

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

Tujuan baku skill ini: Mendampingi unit kerja secara berkelanjutan dalam proses pengadaan (advisory).

## Ruang Lingkup

{{ruang_lingkup}}

Ruang lingkup baku: Sesuai permintaan unit kerja — kegiatan pendampingan terjadwal/insidentil.

## Jadwal Pelaksanaan

- **Mulai**: {{jadwal_mulai}}
- **Selesai**: {{jadwal_selesai}}

## Tim Pengawasan

{{tim_pengawasan}}

## Catatan Pengendali Teknis

{{catatan_pt}}

---

*Template ini diisi oleh Pengendali Teknis (PT) saat tahapan 1 penugasan baru. Setelah disimpan, KT akan mendetailkan menjadi Program Kerja Pengawasan (PKP).*
