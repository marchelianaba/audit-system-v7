# Masukan — Prioritas Sasaran, Langkah Kerja, dan Pattern dalam Analisis Agen

> Status: **masukan / bahan diskusi tim** (belum dikodekan ke prompt). 14 Juni 2026.
> Inspektorat II Komdigi · Audit AI v7.

## Pertanyaan yang dijawab
Ada tiga sumber arahan untuk analisis agen: **sasaran** (Kartu Penugasan/KP),
**langkah kerja** (Program Kerja Pengawasan/PKP), dan **pattern temuan** (wiki).
Bagaimana agen memprioritaskan dan menggunakannya?

## Prinsip inti
Ketiganya **bukan tangga prioritas yang saling menggantikan**, melainkan **peran
berbeda dalam satu rantai**. Memperlakukan pattern setara mandat → temuan ngawur;
memperlakukan langkah kerja sebagai plafon → mutu turun ke level penulis PKP.

## Koreksi penting (dari auditor): PKP = LANTAI, bukan tulang punggung
Menjadikan **langkah kerja PKP sebagai tulang punggung berbahaya** — **kualitas PKP
= kualitas auditor penulisnya (KT).** Bila analisis di-anchor ke PKP, mutu ikut
varians manusia; PKP tipis → analisis tipis. Ini membuang keunggulan utama AI:
menerapkan metodologi **konsisten & tinggi** tanpa peduli siapa penulis PKP.

Maka **tulang punggung mutu = standar skill** (`SKILL.md` + references + **pattern
library** + regulasi + standar audit/SAIPI) — baseline profesional yang seragam.
**Langkah kerja PKP = lantai minimum + jejak audit**, bukan plafon.

## Peran tiap sumber

| Sumber | Peran | Otoritas |
|---|---|---|
| **Sasaran (KP)** | Gerbang lingkup — di mana memeriksa, di mana berhenti | Tertinggi untuk **scope** |
| **Langkah kerja (PKP)** | **Lantai minimum + jejak** — wajib dicakup (kepatuhan & ketertelusuran), tidak berhenti di situ | Mengikat sebagai **lantai**, bukan kedalaman |
| **Standar skill + Pattern + Regulasi** | **Tulang punggung mutu** — kedalaman & konsistensi analisis | Penentu **kedalaman/mutu** |
| **Bukti dokumen** | Penentu validitas — temuan sah hanya bila bukti mendukung | Mengalahkan semua (termasuk pattern) |

## Prinsip kunci: AI sebagai *peng-angkat mutu ke atas*
- **Lantai, bukan plafon.** Agen **minimal** mengerjakan semua langkah kerja PKP
  (rencana terlaksana & tertelusur — kepatuhan APIP), **tetapi selalu menganalisis
  ke standar skill penuh**. Output minimal = **standar profesi**, bukan = kualitas penulis PKP.
- **PKP tipis → tetap kerjakan ke standar + tandai.** Bila langkah kerja
  dangkal/kurang dibanding sasaran & standar, agen tetap analisis lengkap **dan
  melaporkan PKP kurang memadai** ke KT/PT — bahkan **mengusulkan langkah kerja
  tambahan**. Loop ini menaikkan mutu PKP lintas waktu, bukan menguncinya.
- **Pattern = hipotesis, bukan vonis.** Pattern mempertajam deteksi (cegah *false
  negative*) + menyeragamkan tulisan (sitasi pasal, severity, rekomendasi). Sebuah
  pattern jadi temuan **hanya** bila bukti dokumen dalam lingkup mengkonfirmasinya
  (cegah *false positive*).

## Prioritas saat bertabrakan
1. **Lingkup → Sasaran menang.** Di luar sasaran (meski material) → usul perluasan ke PT/PM, jangan dikejar.
2. **Mutu → Standar skill menang atas PKP tipis.** AI menaikkan, tidak menurunkan.
3. **Kepatuhan → PKP wajib dicakup** (lantai) + dijejak — tapi tak membatasi kedalaman.
4. **Validitas → Bukti mengalahkan semua**, termasuk pattern.

## Alur (ringkas)
```
SASARAN (KP) — gerbang lingkup
   │  untuk tiap sasaran
   ▼
┌─ LANGKAH KERJA (PKP) ─┐     ┌─ STANDAR SKILL + PATTERN + REGULASI ─┐
│ lantai minimum+jejak  │     │ tulang punggung mutu                 │
└──────────┬────────────┘     └───────────────┬──────────────────────┘
           └──────────────┬──────────────────┘
                          ▼
            ANALISIS ke STANDAR PENUH  (kerjakan ≥ lantai PKP)
              └─ umpan balik: PKP tipis → tandai + usul langkah ke KT/PT
                          │  uji ke bukti dokumen (penentu)
                          ▼
            TEMUAN — tertelusur: sasaran + langkah + standar/pattern + dokumen
```
> Versi visual interaktif dibuat terpisah (SVG `prioritas_sasaran_langkah_pattern_v2`).

## Kondisi sistem sekarang & celah
- ✅ **Sasaran** sudah jadi gerbang (agen STOP bila sasaran kosong; "hanya sasaran milikmu").
- ✅ **Pattern** sudah dipakai sebagai checklist + format + aturan anti-halusinasi.
- ⚠️ **Langkah kerja (PKP)** tersimpan di `sasaran-assignment.json` tetapi belum
  ditegaskan sebagai **lantai yang wajib dicakup + dijejak**; alur AT digerakkan
  anomali V6 + pattern. Yang dibutuhkan: cakup langkah kerja sebagai lantai
  *sambil* tetap analisis ke standar (bukan menjadikannya plafon).

## Rekomendasi (untuk diimplementasikan nanti — belum dikerjakan)
1. Prompt AT: **standar skill = tulang punggung**; **langkah kerja PKP = lantai
   wajib + jejak**; tiap temuan menyebut **langkah kerja** + **`pattern_id`** + **dokumen_sumber**.
2. Bila PKP tipis: tetap analisis ke standar + **catat "PKP kurang memadai" & usul langkah** (umpan balik ke KT/PT).
3. Tutup tiap langkah dengan status "dikerjakan / tidak bisa (alasan)".

## Kaitan ke harness eval (P1)
- **Recall** diukur terhadap **golden/standar** (apa yang *seharusnya* ketahuan untuk
  sasaran+skill — ditetapkan auditor senior), **bukan terhadap PKP** → PKP tipis yang
  melewatkan isu muncul sebagai **recall rendah** (mutu rendah terdeteksi, bukan tersembunyi).
- **Precision** = pattern tidak melahirkan temuan tak berbukti.
- **Grounding** = tiap temuan tertelusur ke bukti.
