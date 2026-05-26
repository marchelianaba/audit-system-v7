# Wiki — Audit AI v7

Knowledge base yang dapat diakses agen Anggota Tim (AT) dan Ketua Tim (KT) saat menjalankan reviu. Folder ini ditujukan untuk **diisi & dikelola oleh auditor manusia** sebagai pengetahuan kumulatif tim Inspektorat II.

## Dua jenis isi

1. **Pattern temuan** (`temuan-patterns/`) — "rumus" temuan yang sudah pernah teruji. Tiap pattern memuat format judul, kondisi, kriteria peraturan, akibat, dan bukti yang harus dicari.
2. **Konteks pendukung** (`konteks/`) — pola temuan berulang, glossary istilah Komdigi, regulasi & pasal kunci. Tujuannya **mengurangi halusinasi agen** (cegah salah definisi istilah, ngarang sitasi pasal, atau memaksakan pola).

## Cara agen pakai wiki

Saat agen menjalankan analisis, dia akan (urutan disarankan):

1. **`list_konteks()` + `get_konteks(kategori)`** — wajib di awal, baca pola-berulang + glossary + regulasi untuk re-orientasi.
2. **`list_temuan_patterns(skill)`** — dapat daftar pattern untuk skill (tersedia untuk 12 skill spesifik; lihat tabel di bawah).
3. **`get_temuan_pattern(pattern_id)`** — baca pattern spesifik yang relevan, pakai sebagai **referensi format & checklist** (bukan template copy-paste).

## Skill yang punya pattern (selaras dengan registry `knowledge/skills/`)

Tiap **skill spesifik** punya 1 folder pattern (1:1 dengan skill di `knowledge/skills/`).
Skill **`*-umum`** (audit/reviu/pemantauan/evaluasi/konsultansi-umum) **tidak** punya
folder pattern — bersifat *criteria-driven* (kriteria diunggah auditor saat penugasan),
jadi tak butuh pustaka pattern.

| Skill | Prefix ID | Skill | Prefix ID |
|-------|-----------|-------|-----------|
| `reviu-rka-kl` | `RKA-` | `evaluasi-spip` | `ESP-` |
| `reviu-pengadaan` | `RP-` | `evaluasi-sakip` | `ESA-` |
| `audit-pengadaan` | `AP-` | `evaluasi-manajemen-risiko` | `EMR-` |
| `audit-kinerja` | `AK-` | `evaluasi-reformasi-birokrasi` | `ERB-` |
| `konsultasi-pengadaan` | `KP-` | `kepatuhan-saipi` | `KS-` |
| `pemantauan-pengadaan` | `PP-` | `pemantauan-tindak-lanjut` | `PTL-` |

> Daftar di atas indikatif — sumber kebenaran adalah folder yang ADA di
> `temuan-patterns/`. `list_temuan_patterns` menurunkan skill valid dari folder
> (folder-driven), jadi **menambah folder skill = menambah skill** tanpa ubah kode.

## Struktur folder

```
wiki/
├── README.md                          # file ini
├── temuan-patterns/
│   ├── <skill>/                       # 1 folder per skill spesifik (lihat tabel)
│   │   ├── README.md                  # index pattern skill itu
│   │   ├── <ID>-<slug-judul>.md       # mis. RP-08-hps-rfi-minimum.md
│   │   └── ...
│   └── ...                            # 12 folder skill (~65 pattern total)
└── konteks/
    ├── README.md
    ├── pola-temuan-berulang.md        # 9 akar masalah lintas LHP/LHR 2025-2026
    ├── glossary-komdigi.md            # akronim + profil vendor mitra
    └── regulasi-kunci.md              # pasal baku + kutipan inti
```

## Format file pattern

Setiap pattern adalah file `.md` dengan YAML frontmatter di atas, lalu konten markdown. Skema minimal:

```markdown
---
id: RP-08
skill: reviu-pengadaan
kategori: PBJ-HPS
severity: CRITICAL
judul: "HPS Tidak Didukung Minimum 2 Sumber Harga Independen"
kriteria_baku: "Perpres 16/2018 jo. Perpres 12/2021 Pasal 26 ayat (5)"
tags: [hps, rfi, perpres-16]
---

# RP-08: HPS Tidak Didukung Minimum 2 Sumber Harga Independen

## Pattern Kondisi
Deskripsi pola kondisi yang menjadi indikator temuan...

## Kriteria
Peraturan yang dilanggar, lengkap dengan pasal & ayat...

## Akibat
Risiko yang muncul bila kondisi tidak diperbaiki...

## Bukti Yang Harus Dicari
- Dokumen HPS: section "Sumber Penjajakan Harga"
- Dokumen RFI per vendor: pastikan berisi penawaran harga, bukan surat penolakan
- ...

## Contoh Kasus Sebelumnya
(opsional) Anonimkan kasus historis untuk konteks
```

**Field wajib** di frontmatter:
- `id` — unique identifier (mis. `RP-08`, `RKA-15`, `ESP-35`)
- `skill` — nama skill spesifik; HARUS sama dengan nama folder induk (mis. `reviu-pengadaan`, `evaluasi-spip`)
- `kategori` — bebas (PBJ-HPS, RKA-TOR, SPIP-MATURITAS, dll)
- `severity` — `CRITICAL` | `HIGH` | `MEDIUM` | `LOW` | `INFO`
- `judul` — string

**Field opsional:**
- `kriteria_baku` — peraturan inti yang dilanggar
- `tags` — array string untuk pencarian

## Penamaan file

Pola: `{ID}-{slug-judul-pendek}.md`

Contoh:
- `RP-08-hps-rfi-minimum.md` ✓
- `RKA-15-sbm-tahun-anggaran.md` ✓
- `pattern-hps.md` ✗ (tidak ada ID prefix, sulit dilacak)

## Cara menambahkan pattern baru

1. Tentukan ID yang belum dipakai (cek README.md per skill)
2. Buat file `.md` di subfolder skill yang sesuai
3. Isi frontmatter + konten
4. Update README.md per skill (tambah baris di tabel index)
5. Commit ke git supaya tim lain bisa pakai

## Diakses oleh

- Agen Anggota Tim (`anggota_tim`) saat susun KKP
- Agen Ketua Tim (`ketua_tim`) saat susun LHR + rekomendasi

Path resolusi via env var `APP_WIKI_PATH` di `.env`.

## Lihat juga

- `backend/app/tools/wiki_tools.py` — implementasi bridge agen → wiki
- `../README.md` § "Wiki / Pattern Library"
