#!/usr/bin/env bash
# Deployment script untuk Vercel
# Jalankan dari folder audit-system-v7/

set -euo pipefail

cd "$(dirname "$0")/../frontend"

if ! command -v vercel &> /dev/null; then
    echo "📦 Install Vercel CLI..."
    npm install -g vercel
fi

echo ""
echo "Sebelum lanjut, pastikan env var sudah di-set di Vercel:"
echo "  NEXT_PUBLIC_API_BASE = https://audit-ai-v7.fly.dev"
echo ""
echo "Atau set di sini:"
echo "  vercel env add NEXT_PUBLIC_API_BASE production"
echo ""

read -p "Tekan Enter untuk deploy ke production, atau Ctrl+C untuk batal..."

vercel --prod
