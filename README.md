# Audit AI v7 — Inspektorat II Komdigi

Aplikasi web Inspektorat II Kementerian Komunikasi dan Digital berbasis Claude Agent SDK untuk dua skill prioritas: **Reviu RKA-K/L** dan **Reviu Pengadaan**.

Prototype ini membungkus skill V6 (`audit-system-v4`) ke dalam empat agen Claude yang dipanggil lewat browser, tanpa lagi membutuhkan Cowork desktop. Logika analisis V6 **tidak ditulis ulang** — V7 hanya orchestrasi.

> 📦 **Layout perubahan dari spek awal:** V6 sekarang di-embed di `backend/v6/` (bukan sibling folder `audit-system-v4/`). Lihat [Catatan Layout](#catatan-layout-v6) di bawah.

---

## Dua Agen ber-LLM + Ingestion/QC non-agen

| Komponen             | Peran                                                                | Model             | Bentuk |
| -------------------- | -------------------------------------------------------------------- | ----------------- | ------ |
| **Anggota Tim (AT)** | Analisis dokumen + susun KKP                                         | claude-sonnet-4-6 | Agen hardened ✅ |
| **Ketua Tim (KT)**   | Susun draft LHR dari `temuan.json`                                   | claude-sonnet-4-6 | Agen hardened ✅ |
| Ingestion            | Ekstrak PDF/Word → JSON terstruktur                                  | —                 | Worker **deterministik** (`routes/agen._run_ingestion`, panggil script digest V6) |
| QC SAIPI             | Gate kepatuhan SAIPI stage KKP & LHP                                 | —                 | Tool **sinkron** (`run_qc_kkp`/`run_qc_lhp`, panggil `qc_saipi.py` V6) |

> Catatan: Ingestion & QC dulu dirancang sebagai agen LLM (Haiku) tapi nyatanya jalan
> deterministik/sinkron — agen LLM-nya tak pernah dipakai, jadi dihapus (audit 25 Mei 2026).
> Hanya **AT & KT** yang benar-benar agen Claude.

"Hardened" = `tools=[]` (no built-in tools), prompt ketat (no V6 edits, no improvisation), MCP-only access. Lihat [Pipeline V6 Hardening](#pipeline-v6-hardening) di bawah.

---

## Struktur Folder

```
audit-system-v7/
├── README.md                 # file ini (panduan dev lokal)
├── DEPLOY.md                 # panduan deploy Fly.io + Vercel
├── docker-compose.yml        # postgres lokal + backend container (opsional)
├── .env.example              # template variabel environment
├── knowledge/                # aset cowork (audit-system-v4) — di-wire via APP_*_PATH
│   ├── skills/               # registry skill pengawasan (SKILL.md + references) — APP_SKILLS_PATH
│   ├── templates/            # template laporan: _skeleton-lhp/template-lhp-[skill].docx — APP_TEMPLATES_PATH
│   ├── wiki/                 # knowledge base auditor — temuan-patterns/{skill}/ + konteks — APP_WIKI_PATH
│   └── tasks/                # referensi alur cowork (00/01/03/04 + *-bertahap) — TIDAK di-wire (dok)
├── backend/                  # FastAPI + Claude Agent SDK
│   ├── Dockerfile            # python:3.12-slim + Node.js + claude-code CLI
│   ├── fly.toml              # Fly.io app config
│   ├── requirements.txt      # claude-agent-sdk==0.1.81, pydantic==2.11.10, ...
│   ├── .env -> ../.env       # SYMLINK ke .env root (lihat gotcha #1 di bawah)
│   ├── data/                 # output penugasan (gitignored)
│   ├── v6/                   # V6 embedded — TIDAK BOLEH DIEDIT
│   │   ├── scripts/
│   │   ├── skills/
│   │   ├── templates/
│   │   └── checklists/
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models.py        # +CacmRun, EwsFinding, USULAN_CACM
│       ├── schemas.py
│       ├── storage.py       # status derivasi, reset_downstream, context_readiness
│       ├── fixtures/        # sample EWS (demo CACM C1a)
│       ├── templates/       # template-lhp-reviu-rka-kl.docx (LHR app-owned)
│       ├── agents/           # 2 agen Claude (AT + KT). Ingestion=worker, QC=tool sinkron
│       │   ├── base.py       # build_agent_options (tools=[], disallowed_tools=[...])
│       │   ├── anggota_tim.py
│       │   └── ketua_tim.py
│       ├── tools/            # MCP tools (bridge ke V6 scripts)
│       │   ├── v6_bridge.py  # +qc_summary_counts
│       │   ├── pipeline_tools.py  # run_batch_*, read_pdf_page, read_anomalies
│       │   ├── kkp_tools.py  # context-gen, append_temuan, render_kkp, run_qc_kkp
│       │   ├── lhr_tools.py  # render_lhp (per-jenis template), render_lhr_pbj, run_qc_lhp
│       │   ├── skill_tools.py # load_skill, read_skill_reference (registry knowledge/skills)
│       │   └── wiki_tools.py # pattern/konteks + search_wiki/get_wiki_page (vault)
│       ├── prompts/          # system prompts (.md): anggota_tim, ketua_tim
│       └── routes/           # auth, penugasan, dokumen, agen, files, feedback, knowledge, cacm
└── frontend/                 # Next.js 14 + Tailwind
    ├── package.json
    ├── .env.local            # NEXT_PUBLIC_API_BASE=http://localhost:8000
    └── app/
        ├── login/
        ├── penugasan/[id]/   # tabs: Dokumen, Konteks/Setup, Chat, Output & QC
        ├── feedback/  knowledge/  cacm/   # dashboard top-level
```

---

## Quick Start (Dev Lokal)

**Test lapangan: setup dari nol di MacBook butuh ~45 menit + akumulasi 8 hop debug** (lihat [Gotcha Setup](#gotcha-setup) di bawah). README ini sudah memperingatkan semua jebakan tersebut di muka, jadi setup ulang harusnya < 15 menit.

### Prasyarat

| Tool            | Min versi | Install di macOS                           |
| --------------- | --------- | ------------------------------------------ |
| Git             | 2.x       | `brew install git`                         |
| Python          | 3.12+     | `brew install python@3.12`                 |
| Node.js         | 20+       | `brew install node@20` + add to PATH       |
| Docker Desktop  | latest    | `brew install --cask docker`               |
| Claude Code CLI | latest    | `npm install -g @anthropic-ai/claude-code` |

Plus:
- Anthropic API key dari https://console.anthropic.com
- Akun Claude Code (untuk OAuth CLI) atau API key yang sama untuk auth headless

### Langkah Setup

**1. Clone repo**

```bash
git clone https://github.com/irfansihab/audit-system-v7
cd audit-system-v7
```

**2. Setup file `.env`**

```bash
cp .env.example .env
```

Edit `.env`, isi nilai berikut (sesuaikan path absolut dengan mesin Anda):

```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://audit:audit@localhost:5432/audit_v7
APP_ENV=development
APP_SECRET_KEY=<random 32 hex bytes — generate via: openssl rand -hex 32>
APP_DATA_DIR=/path/absolut/ke/audit-system-v7/backend/data
APP_V6_PATH=/path/absolut/ke/audit-system-v7/backend/v6
APP_WIKI_PATH=/path/absolut/ke/audit-system-v7/knowledge/wiki
APP_SKILLS_PATH=/path/absolut/ke/audit-system-v7/knowledge/skills
APP_TEMPLATES_PATH=/path/absolut/ke/audit-system-v7/knowledge/templates
APP_CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

> ⚠️ **GOTCHA #1 — pydantic-settings cari `.env` di cwd uvicorn, bukan project root.**
> Karena uvicorn dijalankan dari `backend/`, pydantic mencari `backend/.env`. `.env` Anda di project root. **Fix wajib:**
>
> ```bash
> cd backend && ln -s ../.env .env
> ```
>
> Tanpa symlink ini, semua nilai `.env` diabaikan dan pakai defaults (termasuk `APP_DATA_DIR=/data` yang invalid di macOS).

**3. Bikin folder data**

```bash
mkdir -p backend/data
```

**4. Setup virtual env Python + install backend deps**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cd ..
```

**5. Jalankan Postgres via Docker**

Buka Docker Desktop dulu, tunggu ikon paus 🐳 di menu bar siap. Lalu:

```bash
docker compose up -d db
docker compose ps  # cek status "Up" dan port 5432:5432
```

**6. Migrasi database**

```bash
cd backend
source .venv/bin/activate
python -m app.init_db   # bikin tabel + seed user dummy
cd ..
```

**7. Auth Claude Code CLI (sekali setup)**

```bash
claude /login   # buka browser → OAuth ke Anthropic
```

> 💡 Alternatif kalau OAuth tidak jalan: export `ANTHROPIC_API_KEY` di shell sebelum jalankan uvicorn. CLI akan inherit env var.

**8. Jalankan backend**

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Test: buka http://localhost:8000/docs untuk Swagger UI.

**9. Jalankan frontend (tab Terminal baru)**

```bash
cd frontend
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000' > .env.local
npm install
chmod +x node_modules/.bin/*   # kalau snapshot lama hilang executable flag
npm run dev
```

Buka http://localhost:3000. **Login cukup pilih peran** — tidak perlu NIP atau password (prototype). Klik salah satu kartu:

| Peran                      | Akun yang dipakai                                   | Hak Akses                                        |
| -------------------------- | --------------------------------------------------- | ------------------------------------------------ |
| **PT** (Pengendali Teknis) | Inspektorat II (`inspektorat2.kominfo.2@gmail.com`) | Buat penugasan baru                              |
| **KT** (Ketua Tim)         | Budi Hartono (`auditor.kt@komdigi.go.id`)           | Setup sasaran, approve KKP, susun LHR            |
| **AT** (Anggota Tim)       | Sarah Aulia (`auditor.at@komdigi.go.id`)            | Upload dokumen, susun KKP, penyempurnaan konteks |

Backend auto-pick user seed pertama yang `role_default == role` yang dipilih.

Untuk tambah/edit user seed: edit `backend/app/init_db.py` lalu jalankan ulang `python -m app.init_db`.

Production nanti diganti SSO Komdigi (OIDC).

---

## Cara Pakai — Workflow Reviu

Alur penugasan, pembagian peran ketat:

```
1. PT buat penugasan
        ↓
2. KT setup sasaran + assign anggota (tab Setup Penugasan)
        ↓
3. AT upload dokumen (AUTO-digest) → Generate Context (AI) + edit → Analisis AI → KKP
        ↓
4. KT approve tiap KKP (status → DISETUJUI_KT)
        ↓
5. KT generate LHR (Chat KT) + QC SAIPI
```

### 1. PT — Buat penugasan baru

Login **PT** → `/penugasan` → **+ Penugasan Baru** → pilih skill (`reviu-pengadaan`/`reviu-rka-kl`) + obyek + **Nomor ST** (disarankan; kosong → diingatkan karena QC akan KRITIS REN-003) → **Buat**. Auto-scaffold: `context.md` (placeholder), `_PKP/sasaran-assignment.json` (kosong), `_KKP/temuan.json` (envelope).

### 2. KT — Setup penugasan (sasaran + assign)

Login **KT** → penugasan → tab **Setup Penugasan**. Fokus Anda: tambah **Sasaran** (ID `S-PBJ-01`/`S-RKA-01`, deskripsi, langkah kerja) dan **assign ke anggota tim**, lalu **Simpan Sasaran**. Sasaran tanpa anggota → diingatkan (QC KRITIS REN-006). **context.md tidak diisi manual** — di-generate AT (langkah 3). Bisa dibantu lewat tab **Chat KT**.

### 3. AT — Upload, Generate Context, Analisis

Login **AT** → penugasan:

**Tab Dokumen:** upload TOR/RAB (RKA-K/L) atau KAK/HPS/RFI/Kontrak (Pengadaan) **+ KP & PKP** (dari INTEGRAL — wajib agar QC tidak BLOKIR). Hanya AT yang boleh upload. **Digest otomatis di background** → `_INGESTED/` (tak ada tombol ingest manual).

> **Digestion dua-tingkat.** (1) **Parser deterministik V6** = jalur utama (gratis/cepat/reproducible). (2) **Fallback LLM tier-2** (opsional, env `DIGEST_LLM_FALLBACK=true`): bila parser kehilangan field kunci (layout tak dikenali), model murah (Haiku) membaca **teks** dokumen & memulihkan field — selektif per dokumen, disimpan di blok `_llm_fallback` pada digest JSON. Asumsi: tidak ada dokumen scan. Untuk **uji** kualitas digest atas banyak dokumen, lihat `backend/scripts/digestion_harness.py` (`--llm-fallback` + deteksi gambar) dan korpus `digest-test-corpus/`.

**Tab Konteks:** klik **✨ Generate Context (AI)** — tombol baru **aktif setelah** (a) KT mengisi sasaran **dan** (b) dokumen ter-digest. AI menyusun `context.md` dari digest + sasaran → **review/edit** (mis. isi Nomor ST, tambah info) → **Simpan Konteks**.

**Tab Chat AT:** ketik *"Mulai analisis [skill] untuk penugasan ini."* Agen: `run_batch_*` (pipeline V6) → `read_anomalies` (telusuri SEMUA anomali) → `read_pdf_page` verifikasi → `append_temuan` → `render_kkp_docx` → `run_qc_kkp` → `submit_feedback`.

### 4. KT — Approve KKP

Login **KT** → tab **Setup Penugasan** (refresh). Sasaran ber-temuan tampil `SELESAI_KKP`. Review di tab **Output & QC** (`KKP-{nama}.docx`, `temuan.json`, `laporan-qa-kkp.md`) → ubah status sasaran ke `DISETUJUI_KT` (atau `DITOLAK_KT` untuk minta revisi) → **Simpan Sasaran**.

### 5. KT — Generate LHR

Setelah semua sasaran `DISETUJUI_KT`, tab **Chat KT** → *"Susun LHR untuk penugasan ini."* Agen: `check_completeness` → `read_temuan_json` → tanya judul/auditi/dasar/gambaran umum/tanggal exit → `write_rekomendasi_json` → **`render_lhr_rka`** (→ `_LHP/LHP-SUBSTANSI-*.docx`, **kompilasi temuan.json yang diapprove**) → `run_qc_lhp` → `submit_feedback`.

### Output Akhir (tab Output & QC)

| Berkas | Lokasi |
|--------|--------|
| KKP Word per anggota | `_KKP/KKP-{nama-anggota}.docx` |
| Temuan JSON | `_KKP/temuan.json` |
| Laporan QA KKP | `_QA-SAIPI/laporan-qa-kkp.md` |
| Rekomendasi JSON | `_LHP/rekomendasi.json` |
| **LHR (kompilasi KKP diapprove)** | `_LHP/LHP-SUBSTANSI-*.docx` ← KT lengkapi nomor + TTD |
| Laporan QA LHP | `_QA-SAIPI/laporan-qa-lhp.md` |
| Feedback agen | `_FEEDBACK-AGEN/feedback-{agent}-{ts}.json` |

---

## Skill yang Diaktifkan

### 1. Reviu RKA-K/L

- Orchestrator V6: `backend/v6/scripts/reviu-rka-kl/run_batch.py`
- 21 rules deterministic (digest TOR + digest RAB → cross-check single + cross-RO)
- Input: **TOR (PDF) + RAB (PDF)** per RO — keduanya wajib PDF format kertas-kerja RKA-K/L. `digest_rab.py` tidak membaca Excel.
- ✅ **Sudah di-test E2E.** `run_batch_rka` otomatis stage TOR/RAB dari `03-perencanaan/` ke `input/objek/{TOR,RAB}/[N] nama.pdf` (pair by urutan nama) sebelum jalankan pipeline V6. Lihat `_stage_rka_inputs` di `backend/app/tools/pipeline_tools.py`.
- Data uji: `dummy-test-docs/` (4 pasang TOR↔RAB format RKA-K/L, regenerate via `_generator.py`). TOR sengaja memuat anomali uji (D.1 dasar hukum tanpa pasal, D.5 MR tak lengkap, D.4 KPI tanpa formula).

### 2. Reviu Pengadaan

- Orchestrator V6: `backend/v6/scripts/reviu-pengadaan/run_batch.py`
- 11 rules + reuse digest dari `audit-pengadaan`
- Input: KAK + HPS + RFI + Kontrak
- Data uji: lihat folder `audit-system-v4/test/uji coba skill reviu pengadaan/` (eksternal)

---

## Pipeline V6 Hardening

Test pertama agen Anggota Tim menghasilkan **94 tool calls** dengan banyak improvisasi: edit V6 scripts, re-implement rules manual, hand-create temuan tanpa pipeline V6. Hasil tidak reproducible — fatal untuk konteks audit.

Setelah lima fix di bawah, run berikutnya: **39 tool calls**, 0 edit ke V6/bridge, QC PASS, semua temuan ter-trace ke halaman PDF. Pola ini di-target replikasi ke 3 agen lain.

| # | Fix | File | Dampak |
|---|-----|------|--------|
| 1 | `tools=[]` di build_agent_options | `app/agents/base.py` | Matikan SEMUA built-in Claude tools (Bash, Edit, Write, Read, Glob, TodoWrite, Agent, Skill). Agen hanya bisa pakai MCP tools yang kita ekspos. |
| 2 | Scaffolding 3 file V6 saat POST `/penugasan` | `app/routes/penugasan.py` | Auto-tulis `context.md` + `_PKP/sasaran-assignment.json` + `_KKP/temuan.json` stub. Agen tidak perlu `Write` file ini sendiri. |
| 3 | Schema transform di `append_temuan` | `app/tools/kkp_tools.py` | `_normalize_temuan_input()` map key sederhana agen (`judul`, `assigned_to`) ke skema V6 (`judul_temuan`, `anggota_tim.nama_lengkap`). |
| 4 | `run_qc_kkp` SYNC menggantikan `request_qc_kkp` async-flag | `app/tools/kkp_tools.py` | Pola lama hanya tulis marker `_pending-kkp.flag` → agen nunggu/improvisasi. Sync version langsung jalankan `qc_saipi.py` dan return hasil. |
| 5 | Prompt anggota_tim.md ketat | `app/prompts/anggota_tim.md` | Daftar tool eksplisit, rule "tidak boleh edit V6/bridge", "pipeline gagal = berhenti, lapor". |

### Invariant Design (jangan dilanggar)

1. **Agen TIDAK BOLEH pakai built-in tools.** `tools=[]` di setiap agen.
2. **Agen TIDAK BOLEH edit V6 atau script bridge.** Kalau ada bug, manusia fix, bukan agen.
3. **Pipeline deterministic V6 = source of truth.** Agen verifikasi & lengkapi, tidak ganti.
4. **Setiap temuan punya `dokumen_sumber` ter-verify lewat `read_pdf_page`.** Anti-halusinasi.
5. **MCP tools harus idempotent dan return ringkas.** Hindari output > 4KB ke agen.

### Isolasi Context & Memori Antar Penugasan

Tidak ada agent state yang bocor antar penugasan, antar run, atau antar user:

**Backend (per invoke `/agen/{name}/run` atau `/agen/{name}/stream`):**
- `AGENT_BUILDERS[name]()` membuat `ClaudeAgentOptions` BARU — fresh MCP server in-process, fresh load prompt dari `.md`
- `ClaudeSDKClient(options=...)` spawn subprocess Claude Code BARU lewat `SubprocessCLITransport`
- Subprocess di-terminate saat context manager exit → tidak ada state yang bertahan
- Lihat comment di `backend/app/routes/agen.py::_stream_agent` dan `::run_agent`

**Penyimpanan state per-penugasan ada di filesystem:**
- `_PKP/sasaran-assignment.json` — sasaran + assignment
- `_KKP/temuan.json` — temuan ter-input
- `_QA-SAIPI/laporan-qa-*.md` — hasil QC
- `_FEEDBACK-AGEN/feedback-*.json` — refleksi agen
- `context.md` — metadata penugasan

Agen baca state dari sini setiap run. Tidak ada caching cross-penugasan.

**Frontend (per komponen tab):**
- Tab components (`DokumenTab`, `SetupPenugasanTab`, `ChatTab`, `OutputTab`) di-mount dengan `key={...-${id}}` — React force unmount + remount saat penugasan ganti. Lihat `frontend/app/penugasan/[id]/page.tsx`.
- State lokal (chat prompt, modal preview, form draft) clean otomatis

---

## Chat History — Persistence Antar Sesi

Setiap kali Anda jalankan agen lewat tab Chat AT atau Chat KT, **percakapan otomatis tersimpan di database**. Saat logout/login lagi atau buka penugasan di hari berikutnya, history percakapan tampil utuh — tidak perlu mulai dari nol.

### Apa yang tersimpan

Per run, di tabel `agent_runs`:
- `input_summary` — prompt user (max 500 char)
- `output_summary` — respons agen (max 2000 char)
- `tool_calls` (JSON) — daftar tool yang dipanggil + arguments
- `status` — `completed` / `failed` / `running`
- `started_at` + `ended_at` — timestamps
- `error_message` — kalau gagal

### Cara akses

Backend endpoint: `GET /agen/{name}/history?penugasan_id=X`  
Frontend: ChatTab auto-load saat mount, render sebagai threaded conversation (prompt → response → audit trail collapsible).

Tombol **"↻ Refresh history"** di ChatTab untuk force re-fetch.

### Isolasi

History di-filter per kombinasi `(penugasan_id, agent_name)`:
- Chat AT penugasan 1 ≠ Chat AT penugasan 2 (terpisah)
- Chat AT ≠ Chat KT (per agent)
- History antar user tidak terlihat di list yang sama (tapi semua user dengan akses penugasan bisa lihat) — desain prototype, untuk produksi bisa di-filter per `user_id`

Implementasi: `backend/app/routes/agen.py` (endpoint) + `frontend/app/penugasan/[id]/page.tsx` (ChatTab).

---

## Wiki / Pattern Library

Folder `wiki/` adalah **knowledge base auditor** yang dapat diakses agen saat menjalankan reviu. Berisi `temuan-patterns/{skill}/` untuk **12 skill spesifik** (~65 pattern) — selaras 1:1 dengan registry `knowledge/skills/`. Pattern adalah "rumus" temuan yang sudah teruji — judul baku, kriteria peraturan, bukti yang harus dicari, format penulisan, dan rekomendasi standar.

> Skill `*-umum` (audit/reviu/pemantauan/evaluasi/konsultansi-umum) **tidak** punya folder pattern — bersifat *criteria-driven* (kriteria diunggah auditor saat penugasan). `list_temuan_patterns` menurunkan skill valid dari folder yang ADA (folder-driven), jadi menambah folder skill = menambah skill tanpa ubah kode.

### Cara kerja

Saat agen Anggota Tim atau Ketua Tim jalan, dia akan:

1. Panggil `list_temuan_patterns(skill)` → dapat daftar pattern relevan (ID, judul, kategori, severity)
2. Untuk pattern yang cocok dengan kondisi yang ditemukan, panggil `get_temuan_pattern(id)` → dapat detail (kondisi, kriteria, akibat, bukti, rekomendasi standar)
3. Pakai sebagai referensi format & checklist — **bukan copy-paste mentah**. Agen tetap menyesuaikan dengan fakta penugasan saat ini.

Tanpa pattern, agen tetap berfungsi (pipeline V6 + judgment LLM). Pattern hanya membuatnya lebih **konsisten** dengan gaya penulisan tim dan **tidak terlewat** mendeteksi kondisi yang sudah pernah ditemukan sebelumnya.

> **Rencana integrasi dua arah (W1–W3).** Selain pattern terkurasi, ada vault pengetahuan penuh
> (`llm-wiki/`, hasil ingest Karpathy via Claude+Obsidian) yang akan tersambung: agen bisa
> **mencari konteks** (profil auditi, riwayat BPK, vendor, regulasi) saat analisis, dan setelah
> penugasan selesai **temuan diusulkan kembali ke wiki**. Detail bertahap di
> **[docs/rencana-cacm-wiki.html](docs/rencana-cacm-wiki.html)** dan [ROADMAP.md §13](ROADMAP.md). Tab `/knowledge` (saat ini scaffold) jadi antarmukanya.

### Cara menambahkan pattern baru

1. Tentukan skill spesifik (mis. `reviu-pengadaan`, `evaluasi-spip`, `audit-kinerja` — salah satu dari 12 folder yang ada)
2. Bikin file `.md` di `wiki/temuan-patterns/{skill}/{ID}-{slug-judul}.md`
3. Isi YAML frontmatter wajib:
   ```yaml
   ---
   id: RP-12                    # unique identifier (prefix per skill: RP-, RKA-, ESP-, ...)
   skill: reviu-pengadaan       # HARUS sama dengan nama folder induk
   kategori: PBJ-METODE         # tag kategori untuk grouping
   severity: HIGH               # CRITICAL | HIGH | MEDIUM | LOW | INFO
   judul: "Metode Pemilihan Tidak Konsisten KAK ↔ Kontrak"
   kriteria_baku: "Perpres 16/2018 Pasal 38"
   tags: [metode, perpres-16, tender]
   ---
   ```
4. Isi body markdown dengan section: Pattern Kondisi, Kriteria, Akibat, Bukti Yang Harus Dicari, Format Temuan, Rekomendasi Standar (opsional)
5. Update tabel index di `wiki/temuan-patterns/{skill}/README.md`
6. Commit ke git supaya tersedia untuk seluruh tim

Lihat contoh:
- `wiki/temuan-patterns/reviu-pengadaan/RP-08-hps-rfi-minimum.md` — pattern HPS hanya 1 sumber harga (Perpres 16 Ps 26.5)
- `wiki/temuan-patterns/reviu-rka-kl/RKA-01-tor-7-blok.md` — pattern TOR tidak lengkap (PMK 107/2024)
- `wiki/temuan-patterns/evaluasi-spip/ESP-35-skor-pm-lebih-tinggi-qa.md` — skor PM > QA (optimism bias, PP 60/2008 + Perka BPKP 5/2021)

Plus tabel skill↔prefix + panduan lengkap di `wiki/README.md`.

### Konfigurasi

Path wiki diatur via env var `APP_WIKI_PATH` di `.env`:

```
APP_WIKI_PATH=/Users/itjen/Downloads/sistem audit v7/knowledge/wiki
```

Bila folder wiki tidak ada atau kosong, agen akan return `WIKI_KOSONG` dan lanjut tanpa pattern.

### Akses dari kode

- Tools: `backend/app/tools/wiki_tools.py` (2 MCP tool: `list_temuan_patterns`, `get_temuan_pattern`)
- Parser frontmatter: built-in, tidak butuh PyYAML
- Cap output: 8 KB per `get_temuan_pattern` untuk hindari context bloat di agen

---

## Feedback Loop — Refleksi Agen Per Run

Setiap kali agen selesai jalan, dia memanggil tool `submit_feedback` yang catat **refleksi retrospective terstruktur** ke `_FEEDBACK-AGEN/feedback-{agent}-{timestamp}.json` per penugasan. Tujuan: bahan perbaikan iteratif baik dari sisi **workflow** (tools, scaffolding, pipeline) maupun **substansi** (false positive rule, pattern wiki yang missing, kondisi yang ambiguous).

### Apa yang dilaporkan agen

| Field | Isi |
|-------|-----|
| `overall_confidence` | HIGH (semua mulus) / MEDIUM (ada hambatan) / LOW |
| `summary` | 1-2 kalimat ringkas pengalaman session |
| `workflow_issues` | array — tools yang error, scaffolding kurang, pipeline gagal. Per item: `{category: tools\|pipeline\|scaffolding\|data\|context, severity: blocker\|major\|minor, description, suggested_action}` |
| `substansi_issues` | array — anomali rule false positive, area sulit di-verify, pattern wiki yang missing. Per item: `{category: false_positive\|missed_pattern\|ambiguous_data\|kriteria_unclear, severity, description, evidence, suggested_action}` |
| `pattern_suggestions` | array — pattern baru yang bagus ada di wiki. Per item: `{id_proposed, judul, rationale}` |
| `notes_freetext` | catatan bebas untuk auditor |

### Siapa yang submit

Semua 4 agen: **Ingestion**, **Anggota Tim**, **Ketua Tim**, **QC SAIPI**. Setiap agen punya panduan di prompt-nya soal apa yang relevan dilaporkan (mis. Ingestion fokus pada workflow PDF/V6, AT pada substansi + pattern, KT pada rekomendasi/akibat).

### Cara auditor akses feedback

1. Buka penugasan di UI → tab **Output & QC**
2. Kategori **"Feedback Agen"** muncul dengan file `feedback-{agent}-{timestamp}.json`
3. Klik **Preview** → JSON ter-render di modal
4. Audit issue per kategori, decide:
   - **Workflow issue blocker** → fix bridge tool atau prompt segera
   - **Substansi issue blocker** → cek temuan ulang, mungkin perlu re-run agen
   - **Pattern suggestion** → kalau berulang muncul, tambahkan ke `wiki/temuan-patterns/`

### Disiplin penggunaan

- Agen diminta **jujur** — feedback HIGH-confidence tanpa issue **lebih bernilai** daripada feedback yang dibuat-buat
- Auditor tidak perlu act pada SEMUA feedback — gunakan pertimbangan untuk prioritas
- Pattern suggestion paling sering dianggap actionable kalau **muncul di ≥2 penugasan** dengan rationale serupa

### Implementasi

- Tool: `backend/app/tools/feedback_tools.py` (`submit_feedback` MCP tool)
- Schema validation: built-in di tool — invalid category/severity di-normalize, tidak crash agen
- Storage: file JSON per run, di `_FEEDBACK-AGEN/` per penugasan
- Visibility: otomatis muncul di Output tab via existing files endpoint

### Phase 2 (future)

Agregasi cross-penugasan: dashboard yang scan semua `_FEEDBACK-AGEN/*.json`, hitung top workflow issues + top pattern suggestions, severity heatmap. Saat ini di TODO Tier 2.

---

## Gotcha Setup

Lima jebakan yang menelan waktu paling banyak saat setup pertama:

1. **`env_file=".env"` di `config.py` adalah path RELATIF terhadap cwd uvicorn.** Symlink `backend/.env -> ../.env` wajib. Tanpa ini, defaults dipakai dan `/data` (read-only di macOS) menyebabkan crash.
2. **V6 embedded di `backend/v6/` (bukan sibling).** Beda dari spek lama README. `APP_V6_PATH` harus absolut ke `backend/v6/`. Struktur subfolder: `scripts/`, `skills/`, `templates/`, `checklists/`.
3. **`claude-agent-sdk==0.1.0` di requirements asli terlalu lama.** Tidak handle message type `rate_limit_event` dari Claude Code CLI modern → `MessageParseError`. Plus `SdkMcpTool` access via `.__name__` (lama) vs `.name` (current dataclass). **Fixed** ke `0.1.81` di requirements.txt + `t.name` di `agents/base.py`.
4. **Claude Code CLI harus di-install global lewat npm + login.** SDK `ClaudeSDKClient` pakai `SubprocessCLITransport` yang shell out ke binary `claude`. Tanpa ini, "Claude Code not found" error.
5. **APP_DATA_DIR dan APP_V6_PATH defaults di `.env.example` = path Docker (`/data`, `/v6`).** Untuk dev lokal harus ganti ke absolute path lokal.

Plus jebakan minor:
- `node_modules/.bin/*` kadang kehilangan executable flag setelah snapshot/zip. `chmod +x node_modules/.bin/*` untuk fix.
- macOS Safari kadang strict CORS — Chrome/Firefox lebih toleran untuk dev.
- `APP_SECRET_KEY` beda di lokal vs production = JWT lama tidak valid. Logout-login fresh setelah ganti.

---

## TODO

### Tier 1 — pipeline core (paling impact)

- [x] **Alur Ketua Tim end-to-end.** ✅ done — UI tab "Setup Penugasan" untuk KT dengan editable form sasaran + context.md. Chat KT Mode A bantu draft sasaran via percakapan. KKP approval lewat status `DISETUJUI_KT` di Setup tab.
- [x] **Apply pola hardening (tools=[], strict prompt) ke 3 agen lain:** Ingestion, KT, QC SAIPI. ✅ done
- [x] **Agen Ingestion otomatis dipanggil saat upload dokumen.** ✅ done (BackgroundTasks di POST /dokumen)
- [x] **Wiki / Pattern Library** dapat diakses agen lewat `list_temuan_patterns` + `get_temuan_pattern`. ✅ done — auditor tinggal populate `wiki/temuan-patterns/`.
- [x] **Feedback loop retrospective** dari agen ke `_FEEDBACK-AGEN/` per penugasan. ✅ done (Phase 1) — Phase 2 dashboard aggregate cross-penugasan masih pending di Tier 2.
- [x] **Workflow refactor PT→KT→AT→KT** ✅ done — role gating ketat (PT-only create, AT-only upload, KT-only sasaran), KKP approval mechanism, frontend isolation per penugasan.
- [x] **Login simplified (no NIP, just role picker)** ✅ done — 3 kartu PT/KT/AT, backend auto-pick user seed.
- [x] **Chat history persistence** ✅ done — backend `GET /agen/{name}/history`, frontend ChatTab auto-load + threaded conversation render.

### Tier 2 — UX & robustness

- [x] **Fix hydration warning di dashboard.** ✅ done — pattern `mounted` state di `/penugasan` + `/penugasan/[id]` + `/feedback` supaya `getSession()` tidak di-call saat SSR. Server-render hanya kembalikan shell `<main>` kosong, session di-baca dari localStorage setelah mount.
- [x] **Streaming response agen (SSE) bukan polling.** ✅ done — ChatTab pakai `EventSource` ke `/agen/{name}/stream`, text + tool_use di-stream real-time, run di-persist ke DB oleh backend, history reload otomatis saat event `done`. Tombol Stop tersedia untuk cancel.
- [x] **Dashboard feedback aggregate (Feedback Phase 2).** ✅ done — backend `GET /feedback/aggregate?days=N` + `GET /feedback/list?days=N` scan semua `_FEEDBACK-AGEN/*.json` cross-penugasan. Frontend `/feedback` dashboard render: KPI total + by_confidence, by_agent, severity heatmap, top 5 workflow/substansi/pattern issues, recent files dengan drill-down link.
- [ ] **Validation: prevent run kalau sasaran-assignment.json kosong.** Saat ini agen "lapor & berhenti" — bagus, tapi UI tidak kasih indikator visual.
- [ ] **Notification antar role** saat handover (PT buat penugasan → KT dapat notif; KT setup done → AT dapat notif; AT KKP done → KT dapat notif untuk approve).

### Tier 3 — deployment & ops

- [x] **Redeploy ke Fly.io** dengan Dockerfile yang include Node.js + claude-code CLI + wiki/. ✅ done (lihat [DEPLOY.md](DEPLOY.md))
- [ ] **Verifikasi `claude` CLI auth headless di container** (via `ANTHROPIC_API_KEY` env, bukan OAuth). Test SSH masuk + `claude --version`.
- [ ] **Migrate `.env` config approach** — pakai absolute env injection di `config.py` agar tidak butuh symlink.
- [ ] **Budget alert** di Anthropic Console + Fly Dashboard.
- [ ] **Populate wiki patterns** — minimal 13 RP + 12 RKA (lihat [ROADMAP.md](ROADMAP.md) W1+W2).

### Tier 4 — fitur cadangan (tahap-2)

- [x] **Tab top-level CACM (`/cacm`) & Knowledge (`/knowledge`)** ✅
- [x] **W1 — baca vault** ✅ `APP_VAULT_PATH` + tool `search_wiki`/`get_wiki_page` (dipakai agen AT/KT) + `GET /knowledge/wiki/search|page` + panel "Cari Wiki".
- [x] **C1a — ingest EWS SIRUP + usulan penugasan** ✅ integrasi dengan delivery EWS tim (`CACM/`, gitignored). Model `CacmRun`/`EwsFinding` + `USULAN_CACM`; `routes/cacm.py` (`/ingest`, `/ingest-sample`, `/runs`, `/findings/{id}/promote|dismiss`, `/usulan/{id}/accept`); UI `/cacm`. Demo: tombol "Muat contoh EWS".
- [x] **C1b — webhook + pull** ✅ `POST /cacm/ews-webhook` (verifikasi HMAC `X-Agent-Signature`) + `POST /cacm/sync` & `/trigger` (REST `X-API-Key`); config `CACM_WEBHOOK_SECRET`/`CACM_AGENT_*`; UI "Sync dari agent" + badge source. Diuji live terhadap agent tim lokal (`run --skip-crawl` di :3100).
- [x] **C2 — otomasi** ✅ sinyal live (webhook/pull) otomatis jadi usulan penugasan untuk finding MERAH (`CACM_AUTO_PROMOTE=off|merah|merah_kuning`), anti-duplikat per satker+kode; `GET /cacm/usulan/pending` + badge notifikasi di nav. Scheduler = milik agent tim (cron tgl 1 & 15 → push webhook).
- [ ] **Wiki W2/W3** — promosi pattern dari feedback + tulis-balik temuan ke vault. Rencana: [docs/rencana-cacm-wiki.html](docs/rencana-cacm-wiki.html) + [ROADMAP.md §13](ROADMAP.md).
- [ ] Auto-inject ke INTEGRAL
- [ ] Multi-tenant (lebih dari Inspektorat II)
- [x] Multi-anggota tim per penugasan ✅ done — 2 seed AT (Sarah Aulia, Citra Lestari), login pemilih orang (`GET /auth/users`), KT assign sasaran per anggota via dropdown nama AT nyata, AT hanya lihat & kerjakan "Sasaran Saya". Tambah user AT lain: edit `backend/app/init_db.py`.
- [ ] Migrasi ke PDN — lihat [DEPLOY.md § Migrasi PDN](DEPLOY.md#migrasi-ke-pdn-tahap-2)

---

## Catatan Layout V6

README asli mengasumsikan struktur:
```
parent/
├── audit-system-v4/    # V6
└── audit-system-v7/    # ini
```
dengan Dockerfile `COPY ../../audit-system-v4/scripts/... v6_scripts/`.

**Layout sekarang** lebih self-contained:
```
audit-system-v7/
└── backend/
    └── v6/             # V6 embedded — semua script/skill/template ada di sini
        ├── scripts/
        ├── skills/
        ├── templates/
        └── checklists/
```

Keuntungan: clone repo = langsung jalan, tidak perlu setup audit-system-v4 terpisah. Dockerfile sekarang `COPY v6/ /v6/` saja. `scripts/deploy-fly.sh` sudah disesuaikan.

Logika V6 di `backend/v6/` ditandai **read-only** secara konvensional. Agen di-block (lewat `tools=[]` + prompt) untuk mengeditnya. Untuk update V6, manusia commit langsung ke folder ini.

---

## Catatan Umum

- V7 **tidak menulis ulang** logika analisis V6. Bridge di `app/tools/` adalah wrapper subprocess yang memanggil `run_batch.py` V6.
- Output kompatibel V6 (`temuan.json`, `KKP-{anggota}.docx`, `LHR-DRAFT.docx`) supaya tahap-2 (auto-inject INTEGRAL) tinggal pakai output yang sama.
- Stack: FastAPI + SQLAlchemy async + Postgres + claude-agent-sdk + Next.js 14 + Tailwind.
- Lisensi: internal Komdigi (belum di-set di repo publik).
- Production deployed: backend di Fly.io Singapore (`audit-ai-v7.fly.dev`), frontend di Vercel (`audit-ai-v7.vercel.app`). Lihat [DEPLOY.md](DEPLOY.md).

---

## Lihat Juga

- [DEPLOY.md](DEPLOY.md) — Panduan deploy ke Fly.io + Vercel + troubleshooting
- [ROADMAP.md](ROADMAP.md) — Desain proyek 4 minggu (wiki populate + CACM integration)
- [ROADMAP.html](ROADMAP.html) — Versi visual interaktif (Gantt + sequence diagram)
- [docs/rencana-cacm-wiki.html](docs/rencana-cacm-wiki.html) — Rencana detail CACM &amp; Wiki (versi visual)
- [wiki/README.md](wiki/README.md) — Panduan menulis pattern temuan
- `backend/app/prompts/{anggota_tim,ketua_tim,ingestion,qc_saipi}.md` — System prompts per agen
- `backend/app/agents/base.py` — Builder pattern + design invariants (`tools=[]`, `disallowed_tools=[...]`)
- `backend/app/routes/agen.py` — Agent runner + isolation guarantee + chat history endpoint
- `backend/app/tools/*.py` — MCP tool bridges (V6 + KKP + LHR + Wiki + Feedback)
