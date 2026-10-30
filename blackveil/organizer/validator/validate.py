#!/usr/bin/env python3
"""BLACK VEIL final-proof validator (Stage 15) — PRIVATE ORGANIZER SERVICE.

Runs isolated from player infrastructure: a dedicated internal Docker network, no
host-published port, and this code is mounted read-only from `organizer/` so it is
never baked into any player image. It holds the deployment key (AETHER_AGENT_KEY)
and is the ONLY component that can mint the final flag.

It accepts a final proof bundle assembled from the whole chain and verifies each
element against key-derived truth, returning the flag only on a complete, correct
proof — and otherwise which elements are missing or wrong (progressive feedback).
"""
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ["AETHER_VALIDATOR_TOKEN"]
if len(TOKEN) < 32:
    raise RuntimeError("validator token is not configured")

KEY = bytes.fromhex(os.environ["AETHER_AGENT_KEY"])
HARBOR = "9a8b7c6d-5e4f-4321-8abc-def012345678"
VEIL_TAG = "veil/v0"  # the public-site clue; load-bearing in the proof


def _hmac(key, *parts):
    mac = hmac.new(key, b"", hashlib.sha256)
    for part in parts:
        mac.update(part if isinstance(part, bytes) else part.encode())
    return mac.hexdigest()


def expected():
    seed = hmac.new(KEY, b"aether-incident/v0", hashlib.sha256).digest()
    pivot_job = "mig-" + seed.hex()[:8]
    return {
        "attestation": _hmac(seed, b"incident-attestation/v0", pivot_job),
        "veil_tag": VEIL_TAG,
        "manifest": "deploy-4102",
        "pivot_number": 4102,
        "tenant_uuid": HARBOR,
    }


def evaluate(bundle):
    want = expected()
    missing = [field for field, value in want.items() if bundle.get(field) != value]
    if missing:
        return {"black_veil": False}
    flag = "BV{" + _hmac(KEY, b"black-veil-flag/v0")[:24] + "}"
    return {"black_veil": True, "flag": flag,
            "message": "The veil is lifted: one trust model, two identities, end to end."}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self._send(200, {"status": "ok"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/validate":
            return self._send(404, {"error": "not found"})
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + TOKEN):
            return self._send(401, {"error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._send(400, {"error": "invalid proof"})
        if not 0 < length <= 8192:
            return self._send(413, {"error": "invalid proof"})
        self.connection.settimeout(5)
        try:
            bundle = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid proof"})
        self._send(200, evaluate(bundle if isinstance(bundle, dict) else {}))

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
