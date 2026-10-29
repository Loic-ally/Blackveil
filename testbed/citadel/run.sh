#!/usr/bin/env bash
# Build and run the Citadel box. Serves on http://127.0.0.1:5002
# INTENTIONALLY VULNERABLE — localhost only.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t watson-citadel .
echo "Citadel on http://127.0.0.1:5002  (Ctrl-C to stop)"
docker rm -f watson-citadel >/dev/null 2>&1 || true
docker run --rm -p 127.0.0.1:5002:5000 --name watson-citadel watson-citadel
