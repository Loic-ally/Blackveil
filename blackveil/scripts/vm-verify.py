#!/usr/bin/env python3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]


def run(args: list[str]) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    if not (ROOT / ".env").is_file():
        raise SystemExit("Run make setup first so the local agent key is generated.")
    run(COMPOSE + ["--profile", "vm", "--profile", "vm-verify", "up", "-d", "--build", "--wait", "--wait-timeout", "480", "aether-linux-vm", "aether-linux-vm-patched"])
    try:
        shell = subprocess.run(
            COMPOSE + [
                "exec", "-T", "aether-linux-vm", "ssh",
                "-i", "/var/lib/aether-vm/operator_ed25519",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "StrictHostKeyChecking=no",
                "-p", "2222", "operator@127.0.0.1",
                "sh -c 'id -u; id -nG; test ! -r /etc/aether-agent/worker.key; if command -v sudo >/dev/null 2>&1; then ! sudo -n true; fi'",
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
