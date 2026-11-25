#!/bin/sh
# Capture the plate into a PNG. Default output is docs/signal.png.
# The README stills are cropped from the live tabs; pass a path to override.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/docs/signal.png}"
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
