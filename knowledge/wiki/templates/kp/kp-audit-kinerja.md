---
jenis: kp_template
skill: audit-kinerja
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

# Kartu Penugasan — Audit Kinerja

## Identitas Penugasan

- **Nomor Surat Tugas**: {{nomor_st}}
- **Tanggal Surat Tugas**: {{tanggal_st}}
- **Judul Penugasan**: {{judul_penugasan}}

## Dasar Hukum & Referensi Regulasi

Permenpan RB tentang Akuntabilitas Kinerja, Permenpan RB 53/2014

{{#referensi_regulasi}}
Tambahan referensi yang dirujuk auditor: {{referensi_regulasi}}
{{/referensi_regulasi}}

## Tujuan Pengawasan

{{tujuan_pengawasan}}

Tujuan baku skill ini: Memperoleh keyakinan memadai atas pencapaian sasaran strategis & efisiensi penggunaan sumber daya.

## Ruang Lingkup

{{ruang_lingkup}}

Ruang lingkup baku: Renja, PK, LKjIP unit kerja periode yang ditentukan.

## Jadwal Pelaksanaan

- **Mulai**: {{jadwal_mulai}}
- **Selesai**: {{jadwal_selesai}}

## Tim Pengawasan

{{tim_pengawasan}}

## Catatan Pengendali Teknis

{{catatan_pt}}

---

*Template ini diisi oleh Pengendali Teknis (PT) saat tahapan 1 penugasan baru. Setelah disimpan, KT akan mendetailkan menjadi Program Kerja Pengawasan (PKP).*
