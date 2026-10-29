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
import os
import re
import subprocess
import uuid
from pathlib import Path

from smoke import Client, require

ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = _load("legacy_check", "verify-legacy.py")
recovery = _load("recovery_check", "verify-recovery.py")

NORTH = "4f3e2d1c-0b9a-4876-9d5c-4b3a29180716"
PLATFORM_INSTALLATION = 4100
RECEIPT_RE = re.compile(r"Recovery receipt: ([0-9a-f]{64})")


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
        print("PASS: challenge chain signup → stage 01 → stage 02 → stage 03; "
              "platform-operator receipt reconstructed and hash-verified, no privilege gained.", flush=True)

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
