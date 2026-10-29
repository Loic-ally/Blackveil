#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

python3 - <<'PY'
from pathlib import Path
import secrets

env_file = Path(".env")
text = env_file.read_text()
placeholder = "replace-with-a-long-local-only-password"
if placeholder in text:
    env_file.write_text(text.replace(placeholder, secrets.token_hex(32)))

text = env_file.read_text()
agent_placeholder = "replace-with-a-random-32-byte-hex-key"
if agent_placeholder in text:
    env_file.write_text(text.replace(agent_placeholder, secrets.token_hex(32)))
elif "AETHER_AGENT_KEY=" not in text:
    env_file.write_text(text.rstrip() + "\nAETHER_AGENT_KEY=" + secrets.token_hex(32) + "\n")
PY

mkdir -p gateway/certs
if [ ! -s gateway/certs/privkey.pem ] || [ ! -s gateway/certs/fullchain.pem ]; then
  openssl req -x509 -nodes -newkey rsa:3072 -days 365 \
    -keyout gateway/certs/privkey.pem \
    -out gateway/certs/fullchain.pem \
    -subj '/CN=aether.blackveil.test' \
    -addext 'subjectAltName=DNS:aether.blackveil.test'
  chmod 600 gateway/certs/privkey.pem
fi

if ! grep -q 'aether.blackveil.test' /etc/hosts 2>/dev/null; then
  cat <<'EOF'
Add this local host entry, then open https://aether.blackveil.test:

  127.0.0.1 aether.blackveil.test

The development TLS certificate is self-signed. Trust gateway/certs/fullchain.pem
in your local browser/OS if you want to remove the browser warning.
EOF
fi
echo 'Local certificate ready. Continue with: make up'
