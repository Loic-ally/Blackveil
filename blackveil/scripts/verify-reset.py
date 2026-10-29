#!/usr/bin/env python3
"""Destructive reset / restart verification in a DISPOSABLE environment.

Never touches the organizer's running `blackveil` project. The script copies the
tracked tree into a temporary directory, generates fresh local secrets there,
and runs it as a separate Compose project (own containers, networks, volumes and
host port). Every destructive command runs inside that copy only.

Scenarios, each followed by the full player-path verifier (Stages 01-08) and an
identity-material assertion:

  fresh        first deployment from empty volumes
  guest-restart  restart both guest containers (QEMU reboot, disks kept)
  agent-restart  restart only the agent using a narrowly scoped sudo rule
                 injected into the DISPOSABLE build, never the source guest.
  vm-reset     scripts/vm-reset.sh — guest disks and keys regenerated, app data kept
  full-reset   scripts/reset.sh — all data regenerated; .env secrets kept

Usage: python3 scripts/verify-reset.py [--port 18443] [--keep]
"""
import argparse
import json
import os
import secrets
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
GUESTS = ("aether-linux-vm", "aether-linux-vm-patched")
CAPTURE = "/var/lib/aether-migration/last-archive-request.json"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class Env:
    def __init__(self, port):
        self.project = "bvreset" + secrets.token_hex(3)
        require(self.project != "blackveil", "refusing to run destructive tests on the main project")
        self.base = Path(tempfile.mkdtemp(prefix="blackveil-reset-"))
        self.root = self.base / "blackveil"
        files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=SOURCE,
                               check=True, capture_output=True, text=True).stdout.split("\0")
        for name in filter(None, files):
            if "__pycache__" in name or not (SOURCE / name).is_file():
                continue
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, target)
        # A test-only control channel, restricted to restarting this one unit.
        # Production cloud-init and the player's operator permissions stay unchanged.
        renderer = self.root / "vm/render-cloud-init.py"
        source = renderer.read_text()
        anchor = '    files = ['
        require(anchor in source, "cloud-init fixture injection point missing")
        renderer.write_text(source.replace(anchor, anchor + '\n        block("/etc/sudoers.d/99-reset-test", "operator ALL=(root) NOPASSWD: /usr/bin/systemctl restart aether-agent\\n", "0440"),', 1))
        shutil.copy(self.root / ".env.example", self.root / ".env")
        self.sh("./scripts/setup-local.sh")
        with open(self.root / ".env", "a") as env:
            env.write(f"BLACKVEIL_PROJECT={self.project}\nBLACKVEIL_HTTPS_PORT={port}\n")
        self.environ = dict(os.environ, AETHER_SMOKE_URL=f"https://127.0.0.1:{port}")
        self.environ.pop("AETHER_IDENTITY_MODE", None)
        for key in list(self.environ):
            if key.startswith(("COMPOSE_", "BLACKVEIL_", "AETHER_")) and key != "AETHER_SMOKE_URL":
                self.environ.pop(key)
        self.environ["COMPOSE_PROJECT_NAME"] = self.project
        print(f"disposable environment: project={self.project} port={port} dir={self.root}", flush=True)

    def sh(self, *args, stdin=None, capture=False):
        result = subprocess.run(list(args), cwd=self.root, env=getattr(self, "environ", None), input=stdin,
                                text=True, check=True, capture_output=capture)
        return result.stdout if capture else None

    def compose(self, *args, capture=False):
        return self.sh("docker", "compose", "--env-file", ".env", "-f", "compose.yaml",
                       "--profile", "vm", "--profile", "vm-verify", *args, capture=capture)

    def up(self):
        self.compose("up", "-d", "--build", "--wait", "--wait-timeout", "900")
        self.compose("exec", "-T", "aether-gateway", "nginx", "-s", "reload")

    def guest(self, service, command):
        """Organizer SSH as the guest operator — infrastructure assertion only."""
        ssh = ("umask 077; cp /var/lib/aether-vm/operator_ed25519 /tmp/k; exec ssh -i /tmp/k "
               "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=ERROR "
               "-o ConnectTimeout=5 -p 2222 operator@127.0.0.1 " + shlex.quote(command))
        return self.compose("exec", "-T", service, "sh", "-c", ssh, capture=True).strip()

    def sql(self, statement):
        return self.compose("exec", "-T", "aether-db", "sh", "-c",
                            'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -v ON_ERROR_STOP=1 -c '
                            + shlex.quote(statement), capture=True).strip()

    def snapshot(self, marker):
        state = {"agent_key": next(line for line in (self.root / ".env").read_text().splitlines()
                                   if line.startswith("AETHER_AGENT_KEY="))}
        for service in GUESTS:
            capture = json.loads(self.guest(service, f"cat {CAPTURE}"))
            state[service] = {
                "operator_key": self.compose("exec", "-T", service, "cat", "/var/lib/aether-vm/operator_ed25519.pub", capture=True).strip(),
                "host_key": self.compose("exec", "-T", service, "cat", "/var/lib/aether-vm/guest_host_ed25519.pub", capture=True).strip(),
                "capture": (capture["job_id"], capture["signature"]),
                "boot_id": self.guest(service, "cat /proc/sys/kernel/random/boot_id"),
                "agent_invocation": self.guest(service, "systemctl show -p InvocationID --value aether-agent"),
                "agent_active": self.guest(service, "systemctl is-active aether-agent"),
            }
            require(state[service]["agent_active"] == "active", f"{service} agent is not active")
        state["receipts"] = self.sql(
            "SELECT string_agg(encode(token_hash,'hex'), ',' ORDER BY encode(token_hash,'hex')) FROM ("
            "SELECT token_hash FROM administrator_recovery_receipts UNION ALL "
            "SELECT token_hash FROM platform_operator_recovery_receipts UNION ALL "
            "SELECT token_hash FROM reporting_enrollment_receipts) r")
        state["marker_user"] = self.sql(f"SELECT count(*) FROM users WHERE email='{marker}'")
        return state

    def chain(self):
        self.sh("make", "chain-verify")

    def destroy(self):
        subprocess.run(["docker", "compose", "--env-file", ".env", "-f", "compose.yaml", "--profile", "vm",
                        "--profile", "vm-verify", "down", "--volumes", "--remove-orphans"],
                       cwd=self.root, env=self.environ, check=True)
        shutil.rmtree(self.base, ignore_errors=True)


def compare(before, after, service_fields, top_fields):
    """service_fields/top_fields: {field: True if it must be preserved, False if regenerated}."""
    for field, preserved in top_fields.items():
        require((before[field] == after[field]) == preserved,
                f"{field} {'changed' if preserved else 'was not regenerated'}")
    for service in GUESTS:
        for field, preserved in service_fields.get(service, {}).items():
            a, b = before[service][field], after[service][field]
            require((a == b) == preserved,
                    f"{service} {field} {'changed' if preserved else 'was not regenerated'}: {a!r} -> {b!r}")
