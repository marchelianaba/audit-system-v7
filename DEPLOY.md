# Panduan Deployment Audit AI v7

## Arsitektur Deployment

```
┌─────────────────────┐       ┌───────────────────────┐
│   Vercel (frontend) │ ───►  │  Fly.io / Singapore   │
│   Next.js 14         │  SSE  │  FastAPI + Agent SDK  │
│   audit-ai-v7        │ ◄───  │  + Fly Postgres       │
│   .vercel.app        │       │  + Fly Volume (3 GB)  │
└─────────────────────┘       └───────────────────────┘
                                       │
                                       ▼
                              ┌─────────────────────┐
                              │  Anthropic API       │
                              │  (Sonnet + Haiku)    │
                              └─────────────────────┘
```

## Persiapan

- Akun Fly.io: https://fly.io/app/sign-up
- Akun Vercel: https://vercel.com/signup
- Anthropic API key: https://console.anthropic.com
- Install `flyctl`: https://fly.io/docs/hands-on/install-flyctl/
- Install `vercel` CLI: `npm i -g vercel`

## Langkah Pertama (sekali setup)

### 1. Setup backend di Fly.io

```bash
cd audit-system-v7/backend

# (a) Login
fly auth login

# (b) Launch app (TIDAK deploy dulu)
fly launch --copy-config --no-deploy --name audit-ai-v7 --region sin

# (c) Create Postgres database
fly postgres create --name audit-ai-v7-db --region sin --vm-size shared-cpu-1x
fly postgres attach audit-ai-v7-db --app audit-ai-v7

# (d) Create volume untuk data audit
fly volumes create audit_data --app audit-ai-v7 --size 3 --region sin

# (e) Set secrets
fly secrets set ANTHROPIC_API_KEY=sk-ant-... --app audit-ai-v7
fly secrets set APP_SECRET_KEY=$(openssl rand -hex 32) --app audit-ai-v7
fly secrets set APP_CORS_ORIGINS=https://audit-ai-v7.vercel.app --app audit-ai-v7

# (f) Copy V6 scripts ke folder backend (akan masuk ke image)
bash ../scripts/deploy-fly.sh
```

### 2. Setup frontend di Vercel

```bash
cd audit-system-v7/frontend

# (a) Login
vercel login

# (b) Link project (pilih: Create new)
vercel

# (c) Set environment variable
vercel env add NEXT_PUBLIC_API_BASE production
# Isi: https://audit-ai-v7.fly.dev

# (d) Deploy ke production
vercel --prod
```

### 3. Verifikasi

- Buka https://audit-ai-v7.fly.dev/health → harus `{"status":"ok"}`
- Buka https://audit-ai-v7.fly.dev/docs → Swagger UI
- Buka https://audit-ai-v7.vercel.app → halaman landing

### 4. Login dummy

- Email: `auditor.at@komdigi.go.id` (Anggota Tim)
- NIP: `198501012010011001`

## Redeploy

### Backend

```bash
cd audit-system-v7
bash scripts/deploy-fly.sh
```

### Frontend

```bash
cd audit-system-v7
bash scripts/deploy-vercel.sh
```

## Monitoring Biaya

Set budget alert di:

- **Anthropic Console** → Settings → Limits → Daily spend limit
- **Fly.io Dashboard** → Billing → Spending alerts

Rekomendasi untuk prototype:
- Anthropic: USD 5/hari (Rp 80rb)
- Fly.io: USD 10/bulan (Rp 160rb)

## Troubleshooting

### `fly deploy` gagal saat build

- Pastikan `v6_scripts/`, `v6_skills/`, `v6_templates/`, `v6_checklists/` sudah di-generate via `scripts/deploy-fly.sh`.
- Cek `fly logs --app audit-ai-v7` untuk error spesifik.

### Frontend tidak bisa connect ke backend

- Pastikan `NEXT_PUBLIC_API_BASE` di Vercel sudah benar.
- Cek CORS di backend: `APP_CORS_ORIGINS` harus mencantumkan URL Vercel.

### SSE stream terputus

- Vercel Hobby tidak mendukung response > 10s untuk Edge runtime; tapi frontend kita pakai EventSource langsung ke Fly.io (bypass Vercel) — seharusnya tidak ada masalah.
- Cek `fly logs` untuk timeout.

### Agen Claude error "tool not found"

- Pastikan `claude-agent-sdk` versi yang ter-install kompatibel dengan kode (lihat `requirements.txt`).
- Periksa `mcp_servers` registered dengan benar di `app/agents/base.py`.

## Migrasi ke PDN (Tahap-2)

Bila ke depannya wajib pindah ke PDN:

1. Setup VM di PDN (mis. server Pusdatin Komdigi).
2. Build image backend dari Dockerfile yang sama.
3. Restore database dari `pg_dump audit-ai-v7-db`.
4. Pindahkan data file dari Fly Volume (snapshot) ke storage PDN.
5. Update DNS — pointing ke server PDN.

Karena seluruh kode portable (FastAPI + Postgres + filesystem), migrasi terbatas pada infrastruktur, bukan rewrite.
