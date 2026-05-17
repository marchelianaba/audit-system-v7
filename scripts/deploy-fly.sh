#!/usr/bin/env bash
# Deployment script untuk Fly.io
# Jalankan dari folder audit-system-v7/

set -euo pipefail

if ! command -v fly &> /dev/null; then
    echo "❌ flyctl belum terinstall. Install dulu: https://fly.io/docs/hands-on/install-flyctl/"
    exit 1
fi

cd "$(dirname "$0")/../backend"

echo "📦 Menyiapkan V6 scripts untuk dimasukkan ke image..."
# Copy script V6 yang dibutuhkan
mkdir -p v6_scripts v6_skills v6_templates v6_checklists

cp -r ../../audit-system-v4/scripts/reviu-rka-kl v6_scripts/
cp -r ../../audit-system-v4/scripts/reviu-pengadaan v6_scripts/
cp -r ../../audit-system-v4/scripts/audit-pengadaan v6_scripts/
cp ../../audit-system-v4/scripts/qc_saipi.py v6_scripts/ 2>/dev/null || true
cp ../../audit-system-v4/scripts/render_kkp.py v6_scripts/ 2>/dev/null || true
cp ../../audit-system-v4/scripts/render_lhp.py v6_scripts/ 2>/dev/null || true
cp ../../audit-system-v4/scripts/validate_kkp_json.py v6_scripts/ 2>/dev/null || true
cp ../../audit-system-v4/scripts/role_check.py v6_scripts/ 2>/dev/null || true
cp ../../audit-system-v4/scripts/sasaran_completeness.py v6_scripts/ 2>/dev/null || true
cp ../../audit-system-v4/scripts/audit_trail.py v6_scripts/ 2>/dev/null || true

cp -r ../../audit-system-v4/skills/reviu-rka-kl v6_skills/
cp -r ../../audit-system-v4/skills/reviu-pengadaan v6_skills/
cp -r ../../audit-system-v4/skills/kepatuhan-saipi v6_skills/
cp -r ../../audit-system-v4/skills/panduan-format-umum v6_skills/
cp -r ../../audit-system-v4/skills/shared-pbj-references v6_skills/

cp ../../audit-system-v4/templates/*.docx v6_templates/ 2>/dev/null || true

mkdir -p v6_checklists
cp ../../audit-system-v4/checklists/reviu-rka-kl.md v6_checklists/ 2>/dev/null || true
cp ../../audit-system-v4/checklists/reviu-pengadaan.md v6_checklists/ 2>/dev/null || true

echo "✅ V6 scripts siap di backend/v6_scripts/"

# Cek apakah app sudah ada di Fly
if fly status --app audit-ai-v7 &> /dev/null; then
    echo "📤 Deploying ke app audit-ai-v7 yang sudah ada..."
    fly deploy --app audit-ai-v7
else
    echo "🆕 App audit-ai-v7 belum ada. Setup pertama kali:"
    echo ""
    echo "1) fly launch --copy-config --no-deploy --name audit-ai-v7 --region sin"
    echo "2) fly postgres create --name audit-ai-v7-db --region sin --vm-size shared-cpu-1x"
    echo "3) fly postgres attach audit-ai-v7-db --app audit-ai-v7"
    echo "4) fly volumes create audit_data --app audit-ai-v7 --size 3 --region sin"
    echo "5) fly secrets set ANTHROPIC_API_KEY=sk-ant-... --app audit-ai-v7"
    echo "6) fly secrets set APP_SECRET_KEY=\$(openssl rand -hex 32) --app audit-ai-v7"
    echo "7) fly secrets set APP_CORS_ORIGINS=https://audit-ai-v7.vercel.app --app audit-ai-v7"
    echo "8) fly deploy --app audit-ai-v7"
    echo ""
    echo "Setelah deploy pertama berhasil, jalankan script ini lagi untuk redeploy."
fi
