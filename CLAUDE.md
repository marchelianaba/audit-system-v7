# Audit AI v7 — Panduan Claude Code

## Cara Menjalankan (Development)

Jalankan empat layanan berikut. Urutan: PostgreSQL → Backend → Frontend → EWS Agent (opsional).

### 1. PostgreSQL (Docker)
```powershell
docker-compose up -d db
```
Health: port 5432

### 2. Backend (FastAPI + uvicorn)
```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Atau pakai script lengkap (set ANTHROPIC_API_KEY otomatis):
```powershell
.\scripts\dev-backend.ps1
```
Health: http://localhost:8000/health → `{"status":"ok"}`

### 3. Frontend (Next.js)
```powershell
cd frontend
npm run dev
```
Health: http://localhost:3000

### 4. EWS Agent (opsional — hanya untuk fitur CACM/EWS)
```powershell
cd CACM
npm run dev
```
Health: http://localhost:3100/api/v1/health

## URL Layanan

| Layanan    | URL                                    | Keterangan                  |
|------------|----------------------------------------|-----------------------------|
| Frontend   | http://localhost:3000                  | Next.js UI                  |
| Backend    | http://localhost:8000                  | FastAPI + docs di /docs     |
| PostgreSQL | localhost:5432                         | Docker container            |
| EWS Agent  | http://localhost:3100                  | CACM/EWS (opsional)         |

## Cek Status Semua Layanan

```powershell
Write-Host "Backend  :" (Invoke-WebRequest -Uri http://localhost:8000/health -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
Write-Host "Frontend :" (Invoke-WebRequest -Uri http://localhost:3000 -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
Write-Host "EWS Agent:" (Invoke-WebRequest -Uri http://localhost:3100/api/v1/health -UseBasicParsing -ErrorAction SilentlyContinue).StatusCode
```

## Prasyarat

- Python 3.12 + venv di `backend/.venv/`
- Node.js 18+ + `npm install` di `frontend/`
- Docker Desktop (untuk PostgreSQL)
- Claude Code desktop app (untuk agen AT/KT — dicari otomatis via `%APPDATA%/Claude/claude-code/`)
- File `.env` di root project (lihat `.env.example`)

## Struktur Singkat

```
sistem audit v7/
├── backend/          # FastAPI — agen AT/KT, routes, tools
│   ├── app/
│   ├── .venv/        # Python venv (tidak di-commit)
│   └── requirements.txt
├── frontend/         # Next.js — UI per tahapan
│   └── app/penugasan/[id]/page.tsx  ← workspace utama
├── CACM/             # EWS Agent (opsional)
├── knowledge/        # Skill definitions + wiki + templates
├── docker-compose.yml
├── .env.example
└── scripts/          # dev-backend.ps1, setup-dev.ps1, dll.
```

## Catatan Windows

- ProactorEventLoop patch sudah ada di `backend/app/main.py` — tidak perlu patch manual.
- Jalankan PowerShell, bukan CMD, untuk aktivasi `.venv`.
- Kalau port 3000 sudah dipakai, Next.js otomatis pindah ke 3001.

## Perintah Umum

```powershell
# Reset DB (hapus semua data, buat ulang tabel)
cd backend && .venv\Scripts\python.exe -m app.init_db

# TypeScript check
cd frontend && npx tsc --noEmit

# Push ke GitHub
git add -A && git commit -m "..." && git push
```
