# Audit AI v7 — Prototype

Aplikasi web Inspektorat II Kementerian Komunikasi dan Digital berbasis Claude Agent SDK untuk dua skill prioritas: **Reviu RKA-K/L** dan **Reviu Pengadaan**.

Prototype ini membungkus skill V6 (`audit-system-v4`) ke dalam empat agen Claude yang dipanggil lewat browser, tanpa lagi membutuhkan Cowork desktop.

## Empat Agen

| Agen | Peran | Model |
|------|-------|-------|
| Ingestion | Ekstrak PDF/Word → JSON terstruktur (deterministic + Haiku fallback) | claude-haiku-4-5 |
| Anggota Tim (AT) | Analisis dokumen + susun KKP | claude-sonnet-4-6 |
| QC SAIPI | Gate kepatuhan SAIPI stage KKP & LHP | claude-haiku-4-5 |
| Ketua Tim (KT) | Susun draft LHR dari temuan.json | claude-sonnet-4-6 |

## Struktur

```
audit-system-v7/
├── README.md                 # file ini
├── docker-compose.yml        # untuk dev lokal (backend + db)
├── .env.example
├── backend/                  # FastAPI + Claude Agent SDK
│   ├── Dockerfile
│   ├── fly.toml
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── schemas.py
│       ├── agents/           # 4 agen Claude
│       ├── tools/            # tool wrappers untuk V6 scripts
│       ├── prompts/          # system prompts
│       └── routes/
└── frontend/                 # Next.js + Tailwind
    ├── package.json
    ├── next.config.js
    ├── vercel.json
    └── app/
        ├── login/
        └── penugasan/
```

## Quick Start (Dev Lokal)

### Prasyarat
- Python 3.12+
- Node 20+
- Docker Desktop (untuk Postgres lokal)
- Anthropic API key (dari https://console.anthropic.com)
- V6 (`audit-system-v4`) tersedia di parent folder

### 1. Setup environment

```bash
cd audit-system-v7
cp .env.example .env
# Edit .env, isi ANTHROPIC_API_KEY
```

### 2. Jalankan database (Postgres lokal via Docker)

```bash
docker-compose up -d db
```

### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
# atau pakai uv: uv pip install -r requirements.txt
```

### 4. Migrasi database

```bash
cd backend
alembic upgrade head
# atau pakai script init:
python -m app.init_db
```

### 5. Jalankan backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Test: buka http://localhost:8000/docs untuk Swagger UI.

### 6. Install + jalankan frontend

```bash
cd frontend
npm install
npm run dev
```

Buka http://localhost:3000.

### 7. Login dummy

Untuk prototype, gunakan kredensial test:
- Email: `auditor.at@komdigi.go.id` (Anggota Tim)
- Email: `auditor.kt@komdigi.go.id` (Ketua Tim)
- NIP: 18 digit apa saja

## Deployment ke Fly.io + Vercel

### Backend → Fly.io

```bash
cd backend
fly launch --copy-config --no-deploy
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set DATABASE_URL="postgres://..."   # dari fly postgres create
fly volumes create audit_data --size 3 --region sin
fly deploy
```

### Frontend → Vercel

```bash
cd frontend
npx vercel
# Set env var NEXT_PUBLIC_API_BASE = https://audit-ai-v7.fly.dev
```

## Skill yang Diaktifkan

### 1. Reviu RKA-K/L
- Orchestrator V6: `audit-system-v4/scripts/reviu-rka-kl/run_batch.py`
- 39 rules deterministic
- Input: TOR (PDF) + RAB (PDF/Excel) per RO
- Data uji: folder `audit-system-v4/penugasan/DIT. PENGENDALIAN/`

### 2. Reviu Pengadaan
- Orchestrator V6: `audit-system-v4/scripts/reviu-pengadaan/run_batch.py`
- 11 rules + reuse digest dari `audit-pengadaan`
- Input: KAK + HPS + RFI + Kontrak
- Data uji: folder `audit-system-v4/test/uji coba skill reviu pengadaan/`

## Catatan

- v7 **tidak menulis ulang** logika analisis V6. Ia memanggil `run_batch.py` V6 sebagai tool dari agen.
- Output identik dengan V6 (`temuan.json`, `KKP-{anggota}.docx`, `LHR-DRAFT.docx`) supaya kompatibel saat tahap-2 menambahkan auto-inject INTEGRAL.
- Tidak ada scheduler, tidak ada CACM, tidak ada auto-inject — fitur cadangan untuk tahap-2.
