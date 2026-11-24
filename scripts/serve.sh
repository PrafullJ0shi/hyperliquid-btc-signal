#!/bin/sh
# Serve the static plate locally (after a sweep has written site/data/signal.json).
cd "$(dirname "$0")/../site"
exec python3 -m http.server 8000 --bind 127.0.0.1
