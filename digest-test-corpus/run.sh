#!/usr/bin/env bash
# Jalankan harness ujicoba digestion atas korpus ini.
# Argumen tambahan diteruskan ke harness (mis. --workers 8).
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

VENV="$PWD/backend/.venv/bin"
if [ ! -x "$VENV/python" ]; then
  echo "venv backend tidak ditemukan di $VENV — buat dulu (lihat README)."; exit 1
fi

GOLDEN_ARG=()
if [ -s digest-test-corpus/golden.json ]; then
  GOLDEN_ARG=(--golden digest-test-corpus/golden.json)
fi

PATH="$VENV:$PATH" PYTHONPATH="$PWD/backend" "$VENV/python" \
  backend/scripts/digestion_harness.py \
    --corpus digest-test-corpus \
    --workers 4 \
    "${GOLDEN_ARG[@]}" "$@"
