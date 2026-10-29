#!/usr/bin/env bash
# Build and run the Watson Linux lab. Serves on http://127.0.0.1:5001
# INTENTIONALLY VULNERABLE — localhost only.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t watson-linux-lab .
echo "Lab on http://127.0.0.1:5001  (Ctrl-C to stop)"
docker rm -f watson-linux-lab >/dev/null 2>&1 || true
docker run --rm -p 127.0.0.1:5001:5000 --name watson-linux-lab watson-linux-lab
