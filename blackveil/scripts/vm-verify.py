#!/usr/bin/env python3
import base64
import argparse
import http.cookiejar
import json
import os
import socket
import ssl
import subprocess
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]
BASE = os.environ.get("AETHER_SMOKE_URL", "https://127.0.0.1")
PORT = urllib.parse.urlsplit(BASE).port or 443


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def read_frame(connection: ssl.SSLSocket, buffered: bytearray) -> tuple[int, bytes, bytearray]:
    def fill(size: int) -> None:
        while len(buffered) < size:
            chunk = connection.recv(max(4096, size - len(buffered)))
            if not chunk:
                raise RuntimeError("WebSocket closed before the shell response arrived")
            buffered.extend(chunk)

    fill(2)
    first, second = buffered[0], buffered[1]
    offset = 2
    length = second & 0x7f
    if length == 126:
        fill(offset + 2)
        length = int.from_bytes(buffered[offset:offset + 2], "big")
        offset += 2
    elif length == 127:
        fill(offset + 8)
        length = int.from_bytes(buffered[offset:offset + 8], "big")
        offset += 8
    mask = b""
    if second & 0x80:
        fill(offset + 4)
        mask = bytes(buffered[offset:offset + 4])
        offset += 4
    fill(offset + length)
    payload = bytes(buffered[offset:offset + length])
    del buffered[:offset + length]
    if mask:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return first & 0x0f, payload, buffered


def connect_websocket(cookie: str, origin: str) -> tuple[ssl.SSLSocket, int, bytearray]:
    raw = socket.create_connection(("127.0.0.1", PORT), timeout=10)
    tls = ssl._create_unverified_context().wrap_socket(raw, server_hostname="aether.blackveil.test")
    tls.settimeout(10)
    nonce = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET /api/lab/terminal HTTP/1.1\r\n"
        "Host: aether.blackveil.test\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {nonce}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Origin: {origin}\r\n"
        f"Cookie: aether_session={cookie}\r\n\r\n"
    )
    tls.sendall(request.encode("ascii"))
    response = bytearray()
    while b"\r\n\r\n" not in response:
        chunk = tls.recv(4096)
        if not chunk:
            tls.close()
            raise RuntimeError("Gateway closed before the terminal handshake completed")
        response.extend(chunk)
    headers, remainder = response.split(b"\r\n\r\n", 1)
    status = int(headers.split(b"\r\n", 1)[0].split()[1])
    return tls, status, bytearray(remainder)


def send_websocket_text(connection: ssl.SSLSocket, value: str) -> None:
    payload = value.encode("utf-8")
    if len(payload) < 126:
        header = bytes((0x81, 0x80 | len(payload)))
    elif len(payload) <= 65535:
        header = bytes((0x81, 0xfe)) + len(payload).to_bytes(2, "big")
    else:
        raise ValueError("verification terminal command is too large")
    mask = os.urandom(4)
    connection.sendall(header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(payload)))


def verify_browser_terminal() -> None:
    suffix = uuid.uuid4().hex[:16]
    email = f"vm-terminal-{suffix}@example.test"
    company = f"Black Veil terminal verification {suffix}"
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
    )
    body = json.dumps({
        "name": "Linux Lab Verification",
        "email": email,
        "company": company,
        "password": "blackveil-vm-verify-password",
    }).encode()
    request = urllib.request.Request(
        BASE + "/api/auth/register",
        data=body,
        headers={
            "Host": "aether.blackveil.test",
            "Origin": "https://aether.blackveil.test",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with opener.open(request, timeout=10) as response:
        if response.status != 201:
            raise RuntimeError(f"terminal test account registration failed: {response.status}")
    cookie = next((item.value for item in cookies if item.name == "aether_session"), None)
    if not cookie:
        raise RuntimeError("registration did not create a browser session")

    settings = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            settings[name] = value
    user = settings.get("AETHER_POSTGRES_USER", "aether")
    database = settings.get("AETHER_POSTGRES_DB", "aether")
    try:
        sql = f"UPDATE users SET role='system_admin' WHERE email='{email}'"
        run(COMPOSE + ["exec", "-T", "aether-db", "psql", "-U", user, "-d", database, "-v", "ON_ERROR_STOP=1", "-c", sql])
        denied, status, _ = connect_websocket(cookie, "https://untrusted.example")
        denied.close()
        if status != 403:
            raise RuntimeError(f"cross-origin terminal handshake returned {status}, expected 403")

        terminal, status, buffered = connect_websocket(cookie, "https://aether.blackveil.test")
        if status != 101:
            terminal.close()
            raise RuntimeError(f"authorized terminal handshake returned {status}, expected 101")
        try:
            send_websocket_text(terminal, "id -u; id -nG; echo BV_TERMINAL_OK\r")
            output = ""
            while "\n1000\noperator\nBV_TERMINAL_OK\n" not in output.replace("\r", ""):
                opcode, payload, buffered = read_frame(terminal, buffered)
                if opcode == 8:
                    raise RuntimeError("Linux terminal closed before running the shell check")
                if opcode == 1:
                    output += payload.decode("utf-8", "replace")
            normalized = output.replace("\r", "")
            if "1000" not in normalized or "operator" not in normalized:
                raise RuntimeError(f"browser terminal reached an unexpected identity: {normalized!r}")
        finally:
            terminal.close()
    finally:
        cleanup = f"DELETE FROM tenants WHERE id=(SELECT tenant_id FROM users WHERE email='{email}')"
        run(COMPOSE + ["exec", "-T", "aether-db", "psql", "-U", user, "-d", database, "-v", "ON_ERROR_STOP=1", "-c", cleanup])
    print("PASS: browser terminal requires a system_admin session, rejects foreign origins, pins guest SSH, and opens only the non-root operator shell.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-only", action="store_true", help="Verify the already running gateway, auth, API and guest terminal")
    args = parser.parse_args()
    if not (ROOT / ".env").is_file():
        raise SystemExit("Run make setup first so the local agent key is generated.")
    if args.terminal_only:
        verify_browser_terminal()
        return
    try:
        run(COMPOSE + ["--profile", "vm", "--profile", "vm-verify", "up", "-d", "--build", "--wait", "--wait-timeout", "480", "aether-api", "aether-gateway", "aether-linux-vm", "aether-linux-vm-patched"])
        run(COMPOSE + ["exec", "-T", "aether-gateway", "nginx", "-s", "reload"])
        run(COMPOSE + ["exec", "-T", "aether-api", "sh", "-c", "test -r /var/lib/aether-vm/operator_ed25519 && test -r /var/lib/aether-vm/guest_host_ed25519.pub && test ! -w /var/lib/aether-vm/operator_ed25519 && test ! -r /var/lib/aether-vm/user-data && test ! -r /var/lib/aether-vm/seed.iso && test ! -r /var/lib/aether-vm/overlay.qcow2"])
        shell = subprocess.run(
            COMPOSE + [
                "exec", "-T", "aether-linux-vm", "sh", "-c",
                "umask 077; cp /var/lib/aether-vm/operator_ed25519 /tmp/operator_ed25519; exec ssh -i /tmp/operator_ed25519 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -p 2222 operator@127.0.0.1 'sh -c \"id -u; id -nG; test ! -r /etc/aether-agent/worker.key; if command -v sudo >/dev/null 2>&1; then ! sudo -n true; fi\"'",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        lines = shell.stdout.splitlines()
        if len(lines) < 2 or lines[0] == "0" or "sudo" in lines[1].split():
            raise SystemExit(f"Operator privilege check failed: {lines!r}")
        check = (ROOT / "vm" / "verify-agent.py").read_text()
        run(COMPOSE + ["exec", "-T", "aether-linux-vm", "python3", "-c", check])
        verify_browser_terminal()
    finally:
        subprocess.run(
            COMPOSE + ["--profile", "vm-verify", "stop", "aether-linux-vm-patched"],
            cwd=ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    main()
