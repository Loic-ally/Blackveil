#!/usr/bin/env bash
# Build and run Obscura. Serves on http://127.0.0.1:5003  — INTENTIONALLY VULNERABLE, localhost only.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t watson-obscura .
echo "Obscura on http://127.0.0.1:5003  (Ctrl-C to stop)"
docker rm -f watson-obscura >/dev/null 2>&1 || true
docker run --rm -p 127.0.0.1:5003:5000 --name watson-obscura watson-obscura
