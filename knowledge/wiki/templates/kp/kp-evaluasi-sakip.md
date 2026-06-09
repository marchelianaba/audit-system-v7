---
jenis: kp_template
skill: evaluasi-sakip
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

# Kartu Penugasan — Evaluasi SAKIP

## Identitas Penugasan

- **Nomor Surat Tugas**: {{nomor_st}}
- **Tanggal Surat Tugas**: {{tanggal_st}}
- **Judul Penugasan**: {{judul_penugasan}}

## Dasar Hukum & Referensi Regulasi

Permenpan RB 88/2021 tentang Evaluasi AKIP

{{#referensi_regulasi}}
Tambahan referensi yang dirujuk auditor: {{referensi_regulasi}}
{{/referensi_regulasi}}

## Tujuan Pengawasan

{{tujuan_pengawasan}}

Tujuan baku skill ini: Memberikan penilaian atas implementasi SAKIP unit kerja sesuai Permenpan RB 88/2021.

## Ruang Lingkup

{{ruang_lingkup}}

Ruang lingkup baku: LKE SAKIP unit kerja periode yang dievaluasi.

## Jadwal Pelaksanaan

- **Mulai**: {{jadwal_mulai}}
- **Selesai**: {{jadwal_selesai}}

## Tim Pengawasan

{{tim_pengawasan}}

## Catatan Pengendali Teknis

{{catatan_pt}}

---

*Template ini diisi oleh Pengendali Teknis (PT) saat tahapan 1 penugasan baru. Setelah disimpan, KT akan mendetailkan menjadi Program Kerja Pengawasan (PKP).*
