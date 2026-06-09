---
jenis: pkp_template
skill: reviu-rka-kl
versi: 1.0
output_format: docx
field_required:
  - judul_program
  - sasaran_utama
  - langkah_kerja_list
  - tim_anggota_assignment
field_optional:
  - referensi_kp
  - risk_profile
  - timeline_per_langkah
---

# Program Kerja Pengawasan (PKP) — Reviu RKA-K/L

## Identitas

Detail dari Kartu Penugasan: {{nomor_st}} ({{tanggal_st}}).

**Judul Program**: {{judul_program}}

## Sasaran Utama Pengawasan

{{sasaran_utama}}

Sasaran baku untuk skill `reviu-rka-kl`:
- Mengevaluasi tor dan rab kegiatan untuk tahun anggaran tertentu.
- Mengidentifikasi temuan substantif sesuai PANDUAN skill reviu-rka-kl
- Memberikan rekomendasi perbaikan

## Langkah Kerja & Penanggung Jawab

{{#langkah_kerja_list}}
- **Langkah {{nomor}}**: {{deskripsi_langkah}}
  - Penanggung jawab: {{anggota_assigned}}
  - Timeline: {{timeline}}
  - Output: {{output_expected}}
{{/langkah_kerja_list}}

## Assignment Tim Anggota

{{tim_anggota_assignment}}

## Risk Profile (Opsional — dari Survey Pendahuluan)

{{risk_profile}}

## Catatan Ketua Tim

[Diisi KT bila ada catatan khusus untuk tim]

---

*Template ini diisi oleh Ketua Tim (KT) saat tahapan 2 penugasan baru. PKP merupakan detail operasional dari Kartu Penugasan (KP).*
