# Standardisasi Catatan Direktorat di Vault (untuk CACM Semantic Anomaly)

> **STATUS: DRAFT pre-implementation (3 Juni 2026, revisi)**
> Dokumen ini menggantikan rancangan awal `knowledge/cacm/profil-satker/<kode>.yaml`
> setelah feedback tim: lebih baik tupoksi disimpan di vault `llm-wiki/wiki/` (yang
> sudah dipakai agen via `search_wiki`/`get_wiki_page`) daripada di YAML terstruktur
> terpisah. Lihat [`docs/rencana-cacm-kriteria.html`](../../docs/rencana-cacm-kriteria.html) §2.5.1.

## Mengapa wiki (.md) + agen, bukan YAML?

- **Single source of truth.** Vault `llm-wiki/wiki/` sudah memuat catatan kaya
  per Direktorat (mis. `direktorat-jenderal-pengawasan-ruang-digital.md` yang
  berisi fungsi, kepemimpinan, sumber pembiayaan, sejarah, dst). YAML terpisah
  → duplikasi & drift.
- **Multi-purpose.** Catatan yang sama dipakai agen reviu pengadaan (susun
  temuan), Ketua Tim (susun LHR), graduasi skill (deteksi domain), dan CACM
  (relevance check). YAML kelas 2 hanya untuk CACM.
- **Kekayaan konteks.** Renstra/Renja/profil narasi tidak muat di YAML kering.
  Vault `.md` menampung Renstra + IKU + sejarah + kepemimpinan + sumber dana.
- **Tools agen sudah ada.** `search_wiki(query, limit)` + `get_wiki_page(name)`
  wired ke AT, KT, dan tools shared. Tidak butuh tool baru.
- **Akurasi LLM lebih tinggi** dgn konteks vault yang kaya (~95% Sonnet, ~92%
  Haiku) vs YAML profil kering (~90% Haiku).

## Section yang perlu ditambahkan ke catatan Direktorat di vault

Setiap catatan `direktorat-*.md` di `llm-wiki/wiki/` ditambah 3 section ini
(di samping fungsi/program/dst yang sudah ada):

### `## Pengadaan Wajar`

Daftar kategori barang/jasa yang RELEVAN dgn tupoksi Direktorat — agen pakai
sebagai whitelist saat menilai relevansi paket pengadaan dgn nama Direktorat.

```markdown
## Pengadaan Wajar

Berikut kategori barang/jasa yang **relevan dengan tupoksi** Wasdig dan
biasa muncul di rencana pengadaan unit ini:

- **Infrastruktur keamanan**: lisensi firewall next-gen (FortiGate, Palo Alto),
  monitoring tools (SIEM, IDS/IPS, EDR), HSM, PKI infrastructure, load balancer,
  DDoS protection.
- **Jasa konsultansi siber**: audit keamanan informasi (ISO 27001), penetration
  testing, kajian regulasi PSE/TTE, manajemen risiko keamanan.
- **Pelatihan & sertifikasi**: CISA, CISM, CISSP, CEH, ISO 27001 LA/LI, PKI
  engineering, pengawasan konten & moderasi.
- **Langganan software**: threat intelligence feed, vulnerability scanner,
  certificate management platform.
- **Perjalanan dinas**: rapat koordinasi ruang digital, supervisi penyedia PSE,
  konferensi siber nasional/internasional.
```

### `## Anti-Pattern Pengadaan`

Daftar jenis pengadaan yang ANEH bila muncul di Direktorat ini — agen akan
flag MERAH saat ketemu pola ini.

```markdown
## Anti-Pattern Pengadaan

Berikut jenis pengadaan yang **kemungkinan tidak sesuai tupoksi** Wasdig.
Bila muncul di SIRUP/RKA, perlu klarifikasi mendalam:

- Pelatihan tata boga / kuliner / hospitality
- Renovasi gedung non-data-center (Wasdig tidak mengelola gedung publik)
- Konsultansi pemasaran ritel / branding
- Pengadaan kendaraan operasional > 5 unit
- Perabot kantor mewah
- Event hiburan / corporate gathering skala besar
- ATK skala besar di luar kebutuhan normal
```

### `## Pengecualian Tupoksi`

Whitelist yang sekilas anomali tapi sebenarnya wajar — supaya agen tidak
false-positive flag MERAH.

```markdown
## Pengecualian Tupoksi

Beberapa pengadaan yang sekilas tampak di luar tupoksi tapi sebenarnya wajar:

- **Konsultansi tata kelola TI** → termasuk pengawasan keamanan informasi,
  bagian dari tupoksi Wasdig.
- **Outsourcing operator monitoring** → penyediaan SDM operator 24/7 untuk
  Security Operations Center adalah praktek standar dan wajar.
- **Konsultansi penyusunan SOP/IK** → bila terkait dgn tupoksi pengawasan.
```

## Cara agen pakai

Saat evaluator CACM perlu menilai apakah paket SIRUP X cocok dgn Direktorat Y:

1. **Mode `vault_lookup_keyword`** (gratis, deterministik): cari catatan
   direktorat via `search_wiki("direktorat-<kode>")`, parse section
   `## Pengadaan Wajar` + `## Anti-Pattern Pengadaan`, tokenize, hitung Jaccard
   match `nama_paket` vs kedua list. Hasil: skor 0-1.

2. **Mode `vault_lookup_haiku`** (~$0.001/paket, ~92% akurasi): panggil
   `get_wiki_page("direktorat-<kode>")`, kirim Haiku template prompt dgn
   isi penuh catatan + nama paket → minta skor 0-100 + alasan.

3. **Mode `vault_lookup_sonnet`** (~$0.01/paket, ~95% akurasi): sama dgn Mode 2
   tapi pakai Sonnet untuk on-demand deep-dive auditor (button "Analisis
   Relevansi" di UI CACM finding).

## Daftar catatan Direktorat yang perlu di-update

Catatan vault existing yang perlu ditambah 3 section di atas:

- [ ] `direktorat-jenderal-pengawasan-ruang-digital.md` (Wasdig) — workshop W1 prioritas
- [ ] `direktorat-jenderal-ekosistem-digital.md` (Ekosdig) — workshop W1 prioritas
- [ ] `direktorat-pengembangan-ekosistem-digital.md` (Dit. Pengembangan) — workshop W1
- [ ] `inspektorat-jenderal-kemkomdigi.md` (Itjen) — diisi terakhir, lower priority
- [ ] Tambah catatan Direktorat di bawah Ditjen yg belum ada (Dir PSTE, Dir Penyidikan,
      dst untuk Wasdig; Dir Ekonomi Digital dst untuk Ekosdig)

Workshop kalibrasi tim 3-7 Juni 2026 — sekalian standardisasi format.

## Source tupoksi

Untuk mengisi section "Pengadaan Wajar" / "Anti-Pattern" / "Pengecualian",
tarik dari:

1. **Permenkomdigi 1/2025** (SOTK) — fungsi & tanggung jawab masing-masing unit.
2. **Renstra Komdigi 2025-2029** — program & sasaran strategis.
3. **RKA-K/L per Satker** — kegiatan & output (RO) yang sudah disetujui.
4. **Riwayat pengadaan 2024-2025** — paket yang lulus QC (tidak di-flag) jadi
   indikasi pengadaan wajar; paket bermasalah jadi indikasi anti-pattern.

## Versioning & Revisi

- Catatan vault berbasis Obsidian/Git — revisi via PR atau edit langsung
  (audit trail di git log llm-wiki).
- Tiap revisi mayor (SOTK berubah, TA baru), tambah baris di section
  "Last updated: YYYY-MM-DD" yang sudah jadi konvensi vault.
- Section "Pengadaan Wajar" / "Anti-Pattern" boleh di-update setiap kali ada
  false-positive / false-negative dari evaluator CACM (continuous calibration).

---

*Dokumen ini adalah panduan tim untuk standardisasi catatan Direktorat di vault
sebelum kriteria CACM kelas 2 (semantic anomaly) di-rilis. Implementasi
evaluator menunggu workshop selesai.*
