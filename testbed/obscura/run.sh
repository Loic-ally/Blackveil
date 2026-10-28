#!/usr/bin/env bash
# Build and run Obscura. Serves on http://127.0.0.1:5003  — INTENTIONALLY VULNERABLE, localhost only.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t metsec-obscura .
echo "Obscura on http://127.0.0.1:5003  (Ctrl-C to stop)"
docker run --rm -p 127.0.0.1:5003:5000 --name metsec-obscura metsec-obscura
