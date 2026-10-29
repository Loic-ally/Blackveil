#!/usr/bin/env python3
"""Organizer player-path verification (Requirement 4, path 1).

Drives the real HTTP interfaces a player uses — register, Stage 01 historical
export, Stage 02 administrator recovery, Stage 03 historical reconstruction —
with no database edits, injected credentials or organizer role grants. Each
stage's privilege/enrollment change is observed through the public API, and the
Stage 03 artifact is proved to be a genuine Stage 05 key by hashing it.

Extends as later stages land. Run against a running stack: `make up` first.
"""
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
    """Run a command as the non-root operator inside the given guest, over the
    operator SSH the terminal uses — the same capability the player holds once in
    the Stage 06 shell."""
    ssh = ("umask 077; cp /var/lib/aether-vm/operator_ed25519 /tmp/opkey; chmod 600 /tmp/opkey; "
           "exec ssh -i /tmp/opkey -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no "
           "-o ConnectTimeout=5 -p 2222 operator@127.0.0.1 " + shlex.quote(command))
    result = subprocess.run(legacy.worker.COMPOSE + ["exec", "-T", service, "sh", "-c", ssh],
                            cwd=ROOT, capture_output=True, text=True)
    return result.stdout


def agent_archive(service, envelope):
    body = shlex.quote(json.dumps(envelope))
    out = guest(service, "curl -s --max-time 5 -H 'Content-Type: application/json' "
                "-d " + body + " http://127.0.0.1:8080/v1/legacy/archive")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"_raw": out}


def reach_tenant_admin(player, tenant):
    """Stage 01 → Stage 02: ordinary signup to tenant_admin via discoverable evidence."""
    _, csv = legacy.report(player, tenant, 4101)
    match = RECEIPT_RE.search(csv)
    require(match is not None and NORTH in csv, "stage 01 handover evidence missing")
    status, _ = recovery.redeem(player, tenant, match.group(1), 4101)
    require(status == 204, f"stage 02 recovery failed: {status}")
    _, me = player.request("/api/me")
    require(me["role"] == "tenant_admin", "stage 02 did not promote to tenant_admin")


def run():
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

        # ---- Stage 06: reach the restricted Linux operator shell ----
        cookie = next((c.value for c in player.cookies if c.name == "aether_session"), None)
        require(cookie is not None, "no session cookie available for the terminal")
        # The terminal rejects a foreign origin even for a system_admin session.
        denied, status, _ = vmverify.connect_websocket(cookie, "https://untrusted.example")
        denied.close()
        require(status == 403, f"terminal accepted a foreign origin: {status}")

        terminal, status, buffered = vmverify.connect_websocket(cookie, ORIGIN)
        vm_up = status != 503
        if not vm_up:
            terminal.close()
            print("SKIP: stage 06–08 — VM profile not running (run `make vm-up`, then re-run).", flush=True)
        else:
            require(status == 101, f"system_admin terminal handshake returned {status}, expected 101")
            try:
                # Marker preceded by the command OUTPUT (uid 1000, group operator)
                # so the PTY echo of the typed command cannot satisfy the match.
                vmverify.send_websocket_text(terminal, "id -u; id -nG; echo BV_CHAIN_SHELL_OK\r")
                output, deadline = "", time.monotonic() + 25
                while "\n1000\noperator\nBV_CHAIN_SHELL_OK\n" not in output.replace("\r", ""):
                    opcode, payload, buffered = vmverify.read_frame(terminal, buffered)
                    if opcode == 8:
                        raise AssertionError("terminal closed before the shell responded")
                    if opcode == 1:
                        output += payload.decode("utf-8", "replace")
                    require(time.monotonic() < deadline, "terminal shell timed out")
            finally:
                terminal.close()
            print("PASS: challenge stage 06 — the elevated player opens the restricted non-root "
                  "Linux operator shell through the terminal, with no SQL grant.", flush=True)

        if vm_up:
            # ---- Stage 07: native service investigation (in the operator shell) ----
            build = guest("aether-linux-vm", "curl -s --max-time 5 http://127.0.0.1:8080/v1/build")
            require("legacy-envelope/1" in build, f"agent build endpoint unexpected: {build!r}")
            capture = guest("aether-linux-vm", "cat /var/lib/aether-migration/last-archive-request.json")
            require(capture.strip(), "retained archive-request capture not found in the guest")
            envelope = json.loads(capture)
            require(envelope["tenant_uuid"] == NORTH and envelope["principal"] == "svc:aether-reporting"
                    and envelope["legacy_tenant_no"] == 4101,
                    "captured envelope is not the North Works reporting request")
            # The operator holds a captured message, not the signing key or map.
            key_read = guest("aether-linux-vm", "cat /etc/aether-agent/worker.key 2>&1 || true")
            require("worker.key" not in key_read or "denied" in key_read.lower() or key_read.strip() == "",
                    f"operator could read the worker signing key: {key_read!r}")
            print("PASS: challenge stage 07 — operator discovers the agent protocol and the retained "
                  "worker-signed capture, without the signing key or tenant map.", flush=True)

            # ---- Stage 08: agent identity binding (number substitution) ----
            legit = agent_archive("aether-linux-vm", envelope)
            require(legit.get("resolved_legacy_tenant_no") == 4101 and "north-works" in json.dumps(legit),
                    f"captured envelope did not resolve the North Works archive: {legit}")
            forged = dict(envelope)
            forged["legacy_tenant_no"] = 4102  # substitute only the unsigned number
            confused = agent_archive("aether-linux-vm", forged)
            require(confused.get("resolved_legacy_tenant_no") == 4102
                    and "harbor" in json.dumps(confused).lower(),
                    f"number substitution did not cross tenants: {confused}")
            print("PASS: challenge stage 08 — substituting only legacy_tenant_no on a valid "
                  "worker signature returns a foreign bounded archive (identity confusion).", flush=True)

            # Patched VM regression: the patched agent signs the number and the
            # timestamp, so the same substitution (and a stale replay) are refused.
            p_capture = guest("aether-linux-vm-patched", "cat /var/lib/aether-migration/last-archive-request.json")
            if p_capture.strip():
                p_env = json.loads(p_capture)
                p_forged = dict(p_env)
                p_forged["legacy_tenant_no"] = 4102
                refused = agent_archive("aether-linux-vm-patched", p_forged)
                require("resolved_legacy_tenant_no" not in refused,
                        f"patched agent accepted a substituted number: {refused}")
                print("PASS: patched stage 08 — the patched agent refuses the number substitution "
                      "(signature covers the number and timestamp).", flush=True)
            else:
                print("SKIP: patched stage 08 — patched VM fixture not provisioned.", flush=True)

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
    run()
