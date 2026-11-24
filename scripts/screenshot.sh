#!/bin/sh
# Capture the plate at 1440x1100 into screenshot.png at the repo root.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/screenshot.png}"
URL="${2:-http://127.0.0.1:8000/}"
google-chrome \
  --headless=new \
  --disable-gpu \
  --hide-scrollbars \
  --force-device-scale-factor=2 \
  --window-size=1440,1280 \
  --screenshot="$OUT" \
  "$URL"
echo "wrote $OUT"
