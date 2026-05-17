#!/usr/bin/env bash
# Setup lokal pengembangan
# Jalankan dari folder audit-system-v7/

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🔧 Setup audit-system-v7 untuk dev lokal..."

# 1. .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ .env dibuat dari .env.example — silakan edit dan isi ANTHROPIC_API_KEY"
else
    echo "ℹ️  .env sudah ada, skip"
fi

# 2. Docker Postgres
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker tidak berjalan. Mulai Docker Desktop dulu."
    exit 1
fi

docker compose up -d db
echo "⏳ Menunggu Postgres siap..."
sleep 5

# 3. Backend deps
cd backend
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Init DB
export DATABASE_URL="postgresql+asyncpg://audit:audit@localhost:5432/audit_v7"
python -m app.init_db
deactivate

# 5. Frontend deps
cd ../frontend
npm install
if [ ! -f .env.local ]; then
    cp .env.example .env.local
fi

echo ""
echo "✅ Setup selesai."
echo ""
echo "Untuk menjalankan dev server:"
echo "  Terminal 1: cd backend && source .venv/bin/activate && uvicorn app.main:app --reload"
echo "  Terminal 2: cd frontend && npm run dev"
echo ""
echo "Buka http://localhost:3000"
