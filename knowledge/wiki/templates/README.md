# Templates Wiki — KP & PKP

Template ini dipakai oleh:
- **PT (Pengendali Teknis)** saat mengisi Kartu Penugasan (KP) di tahapan 1
- **KT (Ketua Tim)** saat mendetailkan KP menjadi Program Kerja Pengawasan (PKP) di tahapan 2

## Struktur

- `kp/kp-<skill>.md` — Template Kartu Penugasan per skill
- `pkp/pkp-<skill>.md` — Template Program Kerja Pengawasan per skill

## Format

Template pakai placeholder `{{field_name}}` yang akan diisi via form UI INTEGRAL AI Workspace.

Field metadata di frontmatter:
- `field_required`: list field yang wajib diisi
- `field_optional`: field opsional
- `output_format`: format hasil render (umumnya `docx`)

## Skill yang ter-cover (7 + 1 default)

1. audit-pengadaan
2. audit-kinerja
3. reviu-rka-kl
4. reviu-pengadaan
5. evaluasi-sakip
6. konsultasi-pengadaan
7. default — fallback untuk skill umum (audit-umum, reviu-umum, evaluasi-umum, dst.)

Untuk skill di luar list ini, gunakan template `default` lalu adaptasi field tujuan/lingkup sesuai PANDUAN skill spesifik.
