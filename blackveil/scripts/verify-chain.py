#!/usr/bin/env python3
"""Organizer player-path verification (Requirements 3 and 4).

Drives the real HTTP, WebSocket terminal and guest-agent interfaces a player
uses — with no database edits, injected credentials or organizer role grants.
Each stage's privilege/enrollment change is observed through the public API,
and the Stage 03 artifact is proved to be a genuine Stage 05 key by hashing it.

Two explicit scopes (Requirement 3):

  --web   Application-only: Stages 01-05 plus the patched-mode regressions.
          The Linux guest is NOT required. (`make web-chain-verify`)

  (full)  Default: Stages 01-10. The Linux guest and its patched fixture are
          MANDATORY. A missing or unreachable guest is a hard failure that
          names the stages not executed and exits nonzero — it never prints a
          full-chain success message. (`make chain-verify`)

Run against a running stack: `make up` first (and `make vm-up` for the full
scope).
"""
import base64
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from smoke import Client, require, ORIGIN

ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = _load("legacy_check", "verify-legacy.py")
recovery = _load("recovery_check", "verify-recovery.py")
vmverify = _load("vm_verify", "vm-verify.py")

NORTH = "4f3e2d1c-0b9a-4876-9d5c-4b3a29180716"
PLATFORM_INSTALLATION = 4100
RECEIPT_RE = re.compile(r"Recovery receipt: ([0-9a-f]{64})")
ENROLL_RE = re.compile(r"Enrollment receipt: ([0-9a-f]{64})")


def scalar(statement):
    """Read a single value from the database (organizer-side assertions only)."""
    result = subprocess.run(
        legacy.worker.COMPOSE + ["exec", "-T", "aether-db", "sh", "-c",
            'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -v ON_ERROR_STOP=1'],
        input=statement, text=True, cwd=ROOT, check=True, capture_output=True)
    return result.stdout.strip()


def signup(profiles, label):
    client = Client()
    suffix = uuid.uuid4().hex
    status, profile = client.request("/api/auth/register", "POST", {
        "name": f"{label} QA", "company": f"{label} {suffix}",
        "email": f"{label.lower()}-{suffix}@example.test",
        "password": "local-chain-verification-password"})
    require(status == 201, f"signup failed: {profile}")
    profiles.append(profile)
    return client, profile


def enroll(client, tenant, installation, receipt):
    return client.request("/api/v2/tenant/reporting-identity", "POST", {
        "tenant_uuid": tenant, "installation_no": installation, "receipt": receipt})


def operator_recovery(client, tenant, installation, receipt):
    return client.request("/api/v2/lab/operator-recovery", "POST", {
        "tenant_uuid": tenant, "installation_no": installation, "receipt": receipt})


def guest(service, command):
    """Organizer-only: run a command as the guest operator over the VM
    container's loopback SSH. Used solely for independent assertions (the
    patched fixture, which no player terminal reaches) — never for a player
    step. Player steps go through `Terminal`."""
    ssh = ("umask 077; cp /var/lib/aether-vm/operator_ed25519 /tmp/opkey; chmod 600 /tmp/opkey; "
           "exec ssh -i /tmp/opkey -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "
           "-o ConnectTimeout=5 -o LogLevel=ERROR -p 2222 operator@127.0.0.1 " + shlex.quote(command))
    result = subprocess.run(legacy.worker.COMPOSE + ["exec", "-T", service, "sh", "-c", ssh],
                            cwd=ROOT, capture_output=True, text=True, check=True, timeout=20)
    return result.stdout


def agent_archive(service, envelope):
    """Organizer-only independent assertion against a guest's agent."""
    body = shlex.quote(json.dumps(envelope))
    out = guest(service, "curl -s --max-time 5 -H 'Content-Type: application/json' "
                "-d " + body + " http://127.0.0.1:8080/v1/legacy/archive")
    try:
        return json.loads(out)
    except json.JSONDecodeError as error:
        raise AssertionError(f"agent returned invalid JSON: {out!r}") from error


GUEST_MISSING = ("full-chain verification requires the Linux guest, but the terminal returned {status}. "
                 "Stages 06, 07 and 08 were NOT executed. Start the guest with `make vm-up` and re-run, "
                 "or run `make web-chain-verify` for the application-only (Stages 01-05) scope. "
                 "Refusing to report full-chain success.")


class Terminal:
    """The player's own browser terminal: one authenticated WebSocket to the
    API's /api/lab/terminal, bridged to the guest operator PTY.

    Each `run` wraps the command in delimiters printed by the shell itself.
    The marker text is assembled by printf from two arguments, so the PTY echo
    of the typed line ("BV_END_ <tag>") can never match the real output line
    ("BV_END_<tag>:<status>"). stdin is closed for the command so it cannot
    swallow later input."""

    def __init__(self, cookie):
        self.socket, status, self.buffered = vmverify.connect_websocket(cookie, ORIGIN)
        if status != 101:
            self.socket.close()
            raise AssertionError(GUEST_MISSING.format(status=status) if status == 503
                                 else f"system_admin terminal handshake returned {status}, expected 101")
        self.output = ""

    def run(self, command, timeout=30):
        tag = uuid.uuid4().hex
        line = (f"printf '\\n%s%s\\n' BV_BEGIN_ {tag}; ( {command} ) </dev/null 2>&1; "
                f"printf '\\n%s%s:%s\\n' BV_END_ {tag} \"$?\"\r")
        require(len(line.encode()) < 4096, "terminal command exceeds the API read limit")
        self.socket.settimeout(min(timeout, 1))
        vmverify.send_websocket_text(self.socket, line)
        end = re.compile(rf"BV_BEGIN_{tag}\n(.*)\nBV_END_{tag}:(\d+)\n", re.S)
        deadline = time.monotonic() + timeout
        while True:
            match = end.search(self.output.replace("\r", ""))
            if match:
                self.output = ""
                return int(match.group(2)), match.group(1)
            require(time.monotonic() < deadline, f"terminal command timed out after {timeout}s: {command!r}")
            try:
                opcode, payload, self.buffered = vmverify.read_frame(self.socket, self.buffered)
            except TimeoutError:
                continue
            if opcode == 8:
                raise AssertionError(f"terminal closed while running {command!r}")
            if opcode in (0, 1, 2):
                self.output += payload.decode("utf-8", "replace")

    def ok(self, command, timeout=30):
        status, out = self.run(command, timeout)
        require(status == 0, f"terminal command exited {status}: {command!r}: {out!r}")
        return out

    def close(self):
        self.socket.close()


AGENT = "http://127.0.0.1:8080"
CAPTURE = "/var/lib/aether-migration/last-archive-request.json"
INDEXER_PORT = 9090
INDEXER_KEY_PATH = "/etc/aether-indexer/transport.key"
HARBOR = "9a8b7c6d-5e4f-4321-8abc-def012345678"


def indexer_probe(tenant_uuid, marker):
    """A single `python3 -c` command that sends one legacy-envelope/0 record to
    the in-guest indexer (127.0.0.1:9090) and prints its raw JSON reply. `marker`
    is a Python byte expression for the trailing origin-marker byte. The program
    is base64-wrapped so it survives the WebSocket terminal and organizer SSH
    without any quoting hazard. This is the record a player crafts after reversing
    the binary; the verifier does not read any organizer secret to build it."""
    prog = (
        "import socket\n"
        f"p=b'{tenant_uuid}'+bytes([{marker}])\n"
        "r=b'AEI\\x00'+bytes([0,1])+len(p).to_bytes(2,'big')+p\n"
        f"s=socket.create_connection(('127.0.0.1',{INDEXER_PORT}),timeout=5)\n"
        "s.sendall(r)\n"
        "d=b''\n"
        "while True:\n"
        " c=s.recv(4096)\n"
        " if not c: break\n"
        " d+=c\n"
        "print(d.decode('utf-8','replace'))\n"
    )
    enc = base64.b64encode(prog.encode()).decode()
    return f"python3 -c \"import base64;exec(base64.b64decode('{enc}'))\""


PROV_SOCKET = "aether-prov"


def provisioner_probe(socket_epoch, request_json):
    """A single `python3 -c` command that connects to the provisioner's per-boot
    abstract unix socket (@aether-prov.<socket_epoch>) and sends one JSON request
    line, printing the reply. base64-wrapped for the terminal and SSH."""
    prog = (
        "import socket\n"
        f"a='\\0{PROV_SOCKET}.{socket_epoch}'\n"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
        "s.settimeout(5)\n"
        "s.connect(a)\n"
        f"s.sendall({json.dumps(request_json)}.encode()+b'\\n')\n"
        "d=b''\n"
        "while True:\n"
        " c=s.recv(4096)\n"
        " if not c: break\n"
        " d+=c\n"
        "print(d.decode('utf-8','replace'))\n"
    )
    enc = base64.b64encode(prog.encode()).decode()
    return f"python3 -c \"import base64;exec(base64.b64decode('{enc}'))\""


def boot_epoch(text):
    """First 8 hex of a boot_id string (the provisioner's handshake epoch)."""
    line = text.strip().splitlines()[-1].strip() if text.strip() else ""
    return line.replace("-", "")[:8]


def reach_tenant_admin(player, tenant):
    """Stage 01 → Stage 02: ordinary signup to tenant_admin via discoverable evidence."""
    _, csv = legacy.report(player, tenant, 4101)
    match = RECEIPT_RE.search(csv)
    require(match is not None and NORTH in csv, "stage 01 handover evidence missing")
    status, _ = recovery.redeem(player, tenant, match.group(1), 4101)
    require(status == 204, f"stage 02 recovery failed: {status}")
    _, me = player.request("/api/me")
    require(me["role"] == "tenant_admin", "stage 02 did not promote to tenant_admin")


def run(web=False):
    original = os.environ.get("AETHER_IDENTITY_MODE") or next(
        (line.split("=", 1)[1] for line in (ROOT / ".env").read_text().splitlines()
         if line.startswith("AETHER_IDENTITY_MODE=")), "challenge")
    profiles = []
    try:
        # ---- Challenge mode: the playable chain ----
        legacy.switch("challenge")
        player, profile = signup(profiles, "Chain")
        tenant, uid = profile["tenant_id"], profile["id"]

        # Stage 03 is administrator-only: an ordinary operator cannot read migration history.
        status, _ = player.request(f"/api/v2/tenant/migration?legacy_tenant_no={PLATFORM_INSTALLATION}")
        require(status == 403, "stage 03 migration endpoint open to ordinary operators")

        reach_tenant_admin(player, tenant)

        # Stage 03a: own settings view discloses only the caller's canonical identity.
        status, settings = player.request("/api/v2/tenant")
        require(status == 200 and settings["tenant_uuid"] == tenant, "tenant settings unavailable")
        require(settings["archive_enabled"] is False, "fresh workspace already archive-enrolled")
        own_number = settings["legacy_tenant_no"]
        require(own_number >= 4102, f"player tenant number {own_number} collides with archive identifiers")

        # Stage 03b: unbound migration read reconstructs the platform-operator artifact.
        status, body = player.request(f"/api/v2/tenant/migration?legacy_tenant_no={PLATFORM_INSTALLATION}")
        require(status == 200 and body["records"], "stage 03 disclosed no platform-operator record")
        detail = body["records"][0]["detail"]
        require(body["records"][0]["principal"] == "svc:aether-reporting"
                and body["records"][0]["tenant_uuid"] == NORTH,
                "stage 03 record lost the reporting principal / UUID mapping")
        match = RECEIPT_RE.search(detail)
        require(match is not None, "platform-operator recovery receipt not reconstructable")
        po_receipt = match.group(1)

        # Organizer-side proof: the reconstructed receipt is the real Stage 05 key.
        stored = scalar(f"SELECT encode(token_hash,'hex') FROM platform_operator_recovery_receipts WHERE installation_no={PLATFORM_INSTALLATION};")
        require(hashlib.sha256(po_receipt.encode()).hexdigest() == stored,
                "reconstructed receipt does not match the stored platform-operator hash")

        # Stage 03c: reading the caller's own number discloses nothing foreign.
        status, own = player.request(f"/api/v2/tenant/migration?legacy_tenant_no={own_number}")
        require(status == 200 and own["records"] == [], "player's own migration history unexpectedly populated")

        # The reconstruction grants no privilege and no enrollment.
        _, me = player.request("/api/me")
        require(me["role"] == "tenant_admin", "stage 03 changed the caller's role")
        status, _ = player.request("/api/lab/terminal")
        require(status == 403, "stage 03 granted terminal access")

        _, events = player.request("/api/audit")
        reads = [e for e in events if e["action"] == "tenant.migration_read"]
        require(any(e["detail"]["legacy_tenant_no"] == PLATFORM_INSTALLATION for e in reads),
                "stage 03 migration read not audited")
        require(po_receipt not in str(events), "audit copied the platform-operator secret")
        print("PASS: challenge stage 03 — signup → stage 01 → stage 02 → stage 03; "
              "platform-operator receipt reconstructed and hash-verified, no privilege gained.", flush=True)

        # ---- Stage 04: reporting-identity enrollment ----
        # Reconstruct the reporting-enrollment receipt from installation 4101 (Stage 03 flaw).
        status, body = player.request("/api/v2/tenant/migration?legacy_tenant_no=4101")
        require(status == 200 and body["records"], "stage 04 reporting record not reconstructable")
        reporting_receipt = next((ENROLL_RE.search(r["detail"]).group(1)
                                  for r in body["records"]
                                  if r["revision"] == "RP-22" and ENROLL_RE.search(r["detail"])), None)
        require(reporting_receipt is not None, "reporting enrollment receipt not found in installation 4101")

        # Before enrollment, the worker→agent archive path is closed.
        status, _ = player.request("/api/reports", "POST", {"type": "legacy-archive"})
        require(status == 403, "unenrolled workspace could queue legacy-archive")

        # Input boundaries: invalid receipt and wrong installation are refused.
        require(enroll(player, tenant, 4101, "0" * 64)[0] == 403, "enrollment accepted an invalid receipt")
        require(enroll(player, tenant, 9999, reporting_receipt)[0] == 403, "enrollment accepted a wrong installation")

        # Challenge enrollment with North Works' receipt succeeds for the player's own tenant.
        status, _ = enroll(player, tenant, 4101, reporting_receipt)
        require(status == 204, f"stage 04 enrollment failed: {status}")

        status, settings = player.request("/api/v2/tenant")
        require(settings["archive_enabled"] is True, "stage 04 did not enroll the workspace")
        _, me = player.request("/api/me")
        require(me["archive_enabled"] is True and me["role"] == "tenant_admin",
                "stage 04 changed role or did not enroll")

        # legacy-archive is now queueable; the slot is empty, so queueability is the gate.
        status, _ = player.request("/api/reports", "POST", {"type": "legacy-archive"})
        require(status == 202, "enrolled workspace could not queue legacy-archive")

        # Enrollment is single-use per workspace.
        require(enroll(player, tenant, 4101, reporting_receipt)[0] == 409, "workspace enrolled twice")

        # Terminal is still denied: enrollment grants no role.
        status, _ = player.request("/api/lab/terminal")
        require(status == 403, "stage 04 granted terminal access")

        _, events = player.request("/api/audit")
        enrolled = [e for e in events if e["action"] == "reporting.enrolled"]
        require(len(enrolled) == 1 and enrolled[0]["detail"]["source_tenant_uuid"] == NORTH
                and enrolled[0]["detail"]["tenant_uuid"] == tenant, "enrollment provenance missing")
        require(reporting_receipt not in str(events), "audit copied the enrollment secret")
        print("PASS: challenge stage 04 — reporting-identity enrollment via a foreign installation "
              "receipt; svc:aether-reporting enrolled, legacy-archive opened, no role gained.", flush=True)

        # ---- Stage 05: operator recovery (tenant_admin → system_admin) ----
        # Ordinary operators cannot call operator recovery at all.
        stray, stray_profile = signup(profiles, "Stray")
        require(operator_recovery(stray, stray_profile["tenant_id"], PLATFORM_INSTALLATION, po_receipt)[0] == 403,
                "operator recovery open to ordinary operators")

        # Stage 04 is a real prerequisite: a tenant_admin that reconstructed the
        # receipt (Stage 03) but did not enroll (Stage 04) is refused.
        player_b, profile_b = signup(profiles, "NoEnroll")
        reach_tenant_admin(player_b, profile_b["tenant_id"])
        require(operator_recovery(player_b, profile_b["tenant_id"], PLATFORM_INSTALLATION, po_receipt)[0] == 403,
                "operator recovery succeeded without the reporting identity (stage 04)")

        # Input boundaries with the enrolled player.
        require(operator_recovery(player, tenant, PLATFORM_INSTALLATION, "0" * 64)[0] == 403,
                "operator recovery accepted an invalid receipt")
        require(operator_recovery(player, tenant, 9999, po_receipt)[0] == 403,
                "operator recovery accepted a wrong installation")

        # Terminal is denied immediately before elevation.
        require(player.request("/api/lab/terminal")[0] == 403, "tenant_admin unexpectedly held terminal access")

        # Challenge elevation via the foreign platform-operator receipt.
        status, _ = operator_recovery(player, tenant, PLATFORM_INSTALLATION, po_receipt)
        require(status == 204, f"stage 05 operator recovery failed: {status}")
        _, me = player.request("/api/me")
        require(me["role"] == "system_admin", "stage 05 did not elevate to system_admin")

        # The terminal authorization gate now distinguishes challenge completion:
        # it no longer returns 403 (503/400/101 depend on VM/websocket, all != 403).
        require(player.request("/api/lab/terminal")[0] != 403,
                "system_admin still denied by the terminal authorization gate")

        # Single-use per account.
        require(operator_recovery(player, tenant, PLATFORM_INSTALLATION, po_receipt)[0] == 409,
                "operator recovery redeemed twice by one account")

        _, events = player.request("/api/audit")
        recovered = [e for e in events if e["action"] == "operator.recovered"]
        require(len(recovered) == 1 and recovered[0]["detail"]["source_tenant_uuid"] == NORTH
                and recovered[0]["detail"]["tenant_uuid"] == tenant
                and recovered[0]["detail"]["role"] == "system_admin", "operator recovery provenance missing")
        require(po_receipt not in str(events), "audit copied the operator recovery secret")
        print("PASS: challenge stage 05 — operator recovery requires Stage 03 receipt + Stage 04 "
              "enrollment, elevates once to system_admin, and opens the terminal authz gate.", flush=True)

        if web:
            # Application-only scope: the Linux guest (Stages 06-08) is out of
            # scope by request, not skipped by failure. `make chain-verify`
            # covers the full chain and requires the guest.
            print("NOTE: web scope — Stages 06-08 (Linux guest) are not part of this run; "
                  "use `make chain-verify` with the guest up for the full chain.", flush=True)
        else:
            # ---- Stage 06: reach the restricted Linux operator shell ----
            cookie = next((c.value for c in player.cookies if c.name == "aether_session"), None)
            require(cookie is not None, "no session cookie available for the terminal")
            # The terminal rejects a foreign origin even for a system_admin session.
            denied, status, _ = vmverify.connect_websocket(cookie, "https://untrusted.example")
            denied.close()
            require(status == 403, f"terminal accepted a foreign origin: {status}")

            # Stages 06-08 run entirely inside this one player terminal session.
            terminal = Terminal(cookie)
            try:
                out = terminal.ok("id -u; id -nG")
                require(out.split()[:2] == ["1000", "operator"], f"terminal reached an unexpected identity: {out!r}")
                print("PASS: challenge stage 06 — the elevated player opens the restricted non-root "
                      "Linux operator shell through the terminal, with no SQL grant.", flush=True)

                # ---- Stage 07: native service investigation (in the player's shell) ----
                build = terminal.ok(f"curl -sS --max-time 5 {AGENT}/v1/build")
                require("legacy-envelope/1" in build, f"agent build endpoint unexpected: {build!r}")
                envelope = json.loads(terminal.ok(f"cat {CAPTURE}"))
                require(envelope["tenant_uuid"] == NORTH and envelope["principal"] == "svc:aether-reporting"
                        and envelope["legacy_tenant_no"] == 4101,
                        "captured envelope is not the North Works reporting request")
                # The operator holds a captured message, not the signing key or map.
                for secret in ("/etc/aether-agent/worker.key", "/etc/aether-agent/tenant-map.csv"):
                    status, out = terminal.run(f"cat {secret}")
                    require(status != 0 and "denied" in out.lower(), f"operator could read {secret}: {out!r}")
                print("PASS: challenge stage 07 — operator discovers the agent protocol and the retained "
                      "worker-signed capture, without the signing key or tenant map.", flush=True)

                # ---- Stage 08: agent identity binding (number substitution) ----
                post = f"curl -sS --max-time 5 -H 'Content-Type: application/json' --data-binary @- {AGENT}/v1/legacy/archive"
                legit = json.loads(terminal.ok(f"cat {CAPTURE} | {post}"))
                require(legit.get("resolved_legacy_tenant_no") == 4101 and "north-works" in json.dumps(legit),
                        f"captured envelope did not resolve the North Works archive: {legit}")
                # Substitute only the unsigned number; the signature is untouched.
                confused = json.loads(terminal.ok(
                    f"sed 's/\"legacy_tenant_no\": 4101/\"legacy_tenant_no\": 4102/' {CAPTURE} | {post}"))
                require(confused.get("resolved_legacy_tenant_no") == 4102
                        and "harbor" in json.dumps(confused).lower(),
                        f"number substitution did not cross tenants: {confused}")
                print("PASS: challenge stage 08 — substituting only legacy_tenant_no on a valid "
                      "worker signature returns a foreign bounded archive (identity confusion).", flush=True)

                # ---- Stage 09: the forgotten binary (legacy indexer compat bypass) ----
                # Containment: the indexer transport key is not operator-readable,
                # so the player cannot forge a modern signed record.
                status, out = terminal.run(f"cat {INDEXER_KEY_PATH}")
                require(status != 0 and "denied" in out.lower(),
                        f"operator could read the indexer transport key: {out!r}")
                # The crafted legacy-envelope/0 record with the trusted-transport
                # marker resolves a descriptor with no key (the Stage 09 defect).
                bypass = json.loads(terminal.ok(indexer_probe(NORTH, "0xA7")))
                require(bypass.get("resolved_tenant_uuid") == NORTH
                        and bypass.get("provisioner", {}).get("service") == "aether-provisioner",
                        f"legacy marker did not resolve a provisioning descriptor: {bypass}")
                # Without the marker the same record is refused: it is the marker
                # bypass, not an open endpoint.
                nomark = json.loads(terminal.ok(indexer_probe(NORTH, "0x00")))
                require(nomark.get("error") == "origin marker",
                        f"indexer resolved a record without the trusted marker: {nomark}")
                require(bypass.get("provisioner", {}).get("service") == "aether-provisioner",
                        "stage 09 descriptor did not name the provisioner (stage 10 entry)")
                print("PASS: challenge stage 09 — reversing the legacy indexer, a crafted "
                      "legacy-envelope/0 record carrying the trusted-transport marker resolves a "
                      "provisioning descriptor with no signing key (compat-shim bypass).", flush=True)

                # ---- Stage 10: namespace labyrinth (reach the confined provisioner) ----
                # Correlate three world-readable observations: the Stage 09
                # descriptor (names the provisioner), the boot epoch, and the
                # abstract socket in /proc/net/unix.
                epoch = boot_epoch(terminal.ok("cat /proc/sys/kernel/random/boot_id"))
                require(len(epoch) == 8, f"could not read the guest boot epoch: {epoch!r}")
                unix = terminal.ok("cat /proc/net/unix")
                require(f"@{PROV_SOCKET}.{epoch}" in unix,
                        "provisioner abstract socket not discoverable in /proc/net/unix")
                # The provisioner runs in a private mount namespace: its mountinfo
                # differs from the operator's (a Linux-internals confirming signal).
                desc = json.loads(terminal.ok(provisioner_probe(epoch, json.dumps({"op": "describe", "epoch": epoch}))))
                require(desc.get("ok") is True and desc.get("provision", {}).get("next") == "false-root",
                        f"provisioner handshake did not return the Stage 11 reference: {desc}")
                wrong = json.loads(terminal.ok(provisioner_probe(epoch, json.dumps({"op": "describe", "epoch": "00000000"}))))
                require(wrong.get("error") == "handshake",
                        f"provisioner accepted a wrong boot epoch: {wrong}")
                # Containment: the patched-mode ticket is not operator-readable.
                status, out = terminal.run("cat /etc/aether-provisioner/ticket")
                require(status != 0 and "denied" in out.lower(),
                        f"operator could read the provisioner ticket: {out!r}")
            finally:
                terminal.close()
            print("PASS: challenge stage 10 — correlating the descriptor, the boot epoch and "
                  "/proc/net/unix reaches the confined provisioner over its abstract socket; "
                  "a wrong epoch is refused and the ticket stays unreadable.", flush=True)

            # Patched VM regression (organizer independent assertion — no player
            # terminal reaches this fixture): the patched agent signs the number and the
            # timestamp, so the same substitution is refused (freshness is tested independently).
            # The patched guest is mandatory for the full chain — a missing fixture
            # is a hard failure, not a skip.
            p_capture = guest("aether-linux-vm-patched", "cat /var/lib/aether-migration/last-archive-request.json")
            require(p_capture.strip(),
                    "patched Linux guest (aether-linux-vm-patched) is required for full-chain "
                    "verification but is not provisioned. Start it with the vm-verify profile and re-run.")
            p_env = json.loads(p_capture)
            p_forged = dict(p_env)
            p_forged["legacy_tenant_no"] = 4102
            refused = agent_archive("aether-linux-vm-patched", p_forged)
            require(refused.get("error") == "service signature rejected",
                    f"patched agent accepted a substituted number: {refused}")
            print("PASS: patched stage 08 — the patched agent refuses the number substitution "
                  "(signature covers the number and timestamp).", flush=True)

            # Patched Stage 09 (organizer independent assertion against the patched
            # guest): the patched indexer decommissions the legacy transport, so the
            # crafted legacy-envelope/0 record is refused outright.
            refused9 = guest("aether-linux-vm-patched", indexer_probe(NORTH, "0xA7"))
            require("decommissioned" in refused9,
                    f"patched indexer served a legacy-transport record: {refused9!r}")
            print("PASS: patched stage 09 — the patched indexer decommissions the legacy "
                  "transport; the crafted record is refused.", flush=True)

            # Patched Stage 10 (organizer assertion on the patched guest): the
            # patched provisioner ignores the world-readable boot epoch and requires
            # a ticket, so the correlation shortcut no longer authorizes describe.
            p_epoch = boot_epoch(guest("aether-linux-vm-patched", "cat /proc/sys/kernel/random/boot_id"))
            require(len(p_epoch) == 8, f"could not read patched guest boot epoch: {p_epoch!r}")
            p_desc = guest("aether-linux-vm-patched",
                           provisioner_probe(p_epoch, json.dumps({"op": "describe", "epoch": p_epoch})))
            require('"handshake"' in p_desc,
                    f"patched provisioner honored the epoch shortcut: {p_desc!r}")
            print("PASS: patched stage 10 — the patched provisioner ignores the boot epoch "
                  "and requires a ticket; the world-readable shortcut is closed.", flush=True)

        # ---- Patched mode: the Stage 03 disclosure is closed ----
        legacy.switch("patched")
        status, body = player.request(f"/api/v2/tenant/migration?legacy_tenant_no={PLATFORM_INSTALLATION}")
        require(status == 200, f"patched migration read failed: {status}")
        require(all(RECEIPT_RE.search(r["detail"]) is None for r in body["records"]),
                "patched mode still disclosed a foreign platform-operator receipt")
        require(all(r["tenant_uuid"] != NORTH for r in body["records"]),
                "patched mode resolved a foreign installation number")
        status, settings = player.request("/api/v2/tenant")
        require(status == 200 and settings["tenant_uuid"] == tenant, "patched settings view regressed")
        print("PASS: patched stage 03 resolves only the caller's canonical number; "
              "no foreign migration record or receipt is disclosed.", flush=True)

        # Patched Stage 04: a foreign installation's receipt cannot enroll the
        # caller (the binding check precedes the single-use conflict, so an
        # already-enrolled player still proves the gate fired with 403).
        require(enroll(player, tenant, 4101, reporting_receipt)[0] == 403,
                "patched mode enrolled the caller from a foreign installation receipt")
        print("PASS: patched stage 04 binds the enrollment receipt's installation "
              "to the caller and refuses a foreign receipt.", flush=True)

        # Patched Stage 05: a foreign platform-operator receipt cannot elevate the
        # caller (binding check precedes redemption, so 403 even for the already-
        # elevated player — the gate fired, not a role/redemption conflict).
        require(operator_recovery(player, tenant, PLATFORM_INSTALLATION, po_receipt)[0] == 403,
                "patched mode elevated from a foreign platform-operator receipt")
        print("PASS: patched stage 05 binds the platform-operator receipt to the "
              "destination workspace and refuses a foreign receipt.", flush=True)

        if web:
            print("OK: application-only chain verified — Stages 01-05 (challenge) and the "
                  "patched 03/04/05 regressions. Linux Stages 06-08 not in scope.", flush=True)
        else:
            print("OK: full chain verified — Stages 01-10 (challenge) through the real player "
                  "interfaces, plus the patched 03/04/05/08/09/10 regressions.", flush=True)
    finally:
        try:
            for profile in profiles:
                uid, tenant = profile["id"], profile["tenant_id"]
                legacy.worker.sql(
                    f"DELETE FROM audit_events WHERE user_id='{uid}' "
                    f"OR object_id IN (SELECT id::text FROM reports WHERE requested_by='{uid}'); "
                    f"DELETE FROM reports WHERE requested_by='{uid}'; "
                    f"DELETE FROM users WHERE id='{uid}'; "
                    f"DELETE FROM tenants WHERE id='{tenant}';")
        finally:
            legacy.switch(original)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", action="store_true",
                        help="Application-only scope (Stages 01-05); the Linux guest is not required.")
    run(web=parser.parse_args().web)
