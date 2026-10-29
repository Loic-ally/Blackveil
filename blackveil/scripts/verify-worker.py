#!/usr/bin/env python3
"""Organizer-only live worker verification. Requires the application and VM up."""
import subprocess
import time
import uuid
from pathlib import Path
from smoke import Client, require

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]


def sql(statement):
    subprocess.run(COMPOSE + ["exec", "-T", "aether-db", "sh", "-c",
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'],
        input=statement, text=True, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def wait_for_report(client, report_id, label):
    deadline = time.monotonic() + 30
    while True:
        _, reports = client.request("/api/reports")
        current = next(item for item in reports if item["id"] == report_id)
        if current["status"] in ("complete", "failed"):
            break
        require(time.monotonic() < deadline, f"{label} timed out")
        time.sleep(0.3)
    require(current["status"] == "complete", f"{label} failed: {current}")
    return current


def run():
    suffix = uuid.uuid4().hex
    profiles = []
    clients = []
    try:
        for name in ("archive", "outsider"):
            client = Client()
            status, profile = client.request("/api/auth/register", "POST", {
                "name": "Archive verification", "company": f"Archive QA {suffix}",
                "email": f"{name}-{suffix}@example.test", "password": "local-archive-verification-password"})
            require(status == 201, f"signup failed: {profile}")
            profiles.append(profile)
            clients.append(client)
        owner, outsider = clients
        status, _ = outsider.request("/api/reports", "POST", {"type": "legacy-archive"})
        require(status == 403, "unenrolled tenant queued an archive job")
        # Grant only the archive tenant membership prerequisite; no admin role.
        sql(f"UPDATE users SET tenant_id='4f3e2d1c-0b9a-4876-9d5c-4b3a29180716' WHERE id='{profiles[0]['id']}';")
        status, me = owner.request("/api/me")
        require(status == 200 and me["archive_enabled"] and me["role"] == "operator", "archive enrollment contract failed")
        status, report = owner.request("/api/reports", "POST", {"type": "legacy-archive"})
        require(status == 202, f"archive queue failed: {report}")
        wait_for_report(owner, report["id"], "archive job")
        status, content = owner.request(f"/api/reports/{report['id']}")
        require(status == 200 and "north-works" in content and "4101" in content, "native archive CSV missing")
        status, _ = outsider.request(f"/api/reports/{report['id']}")
        require(status == 404, "foreign tenant downloaded archive")
        status, events = owner.request("/api/audit")
        event = next(item for item in events if item["action"] == "archive.resolved" and item["object_id"] == report["id"])
        require(event["detail"]["tenant_uuid"] == me["tenant_id"] and len(event["detail"]["signature"]) == 64, "archive provenance missing")
        _, notices = owner.request("/api/notifications")
        require(any("legacy-archive report is ready" in n["message"] for n in notices), "archive notification missing")

        # Simulate a worker dying after the database claim but before delivery.
        status, recovery = owner.request("/api/reports", "POST", {"type": "asset-inventory"})
        require(status == 202, f"recovery report queue failed: {recovery}")
        subprocess.run(COMPOSE + ["stop", "aether-worker"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        sql(f"UPDATE reports SET status='running',lease_until=now()-interval '1 second',attempt_count=1 WHERE id='{recovery['id']}';")
        subprocess.run(COMPOSE + ["start", "aether-worker"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        wait_for_report(owner, recovery["id"], "expired-lease recovery")
        _, rows = owner.request(f"/api/reports/{recovery['id']}")
        require("asset_code" in rows, "recovered report content missing")
        attempts = subprocess.run(COMPOSE + ["exec", "-T", "aether-db", "sh", "-c",
            f"psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atc \"SELECT attempt_count FROM reports WHERE id='{recovery['id']}'\""],
            cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        require(attempts == "2", f"expired report lease was not reclaimed exactly once: attempts={attempts}")
        print("PASS: HTTPS archive delivery, provenance and tenant isolation; expired report lease recovers after worker interruption.")
    finally:
        subprocess.run(COMPOSE + ["start", "aether-worker"], cwd=ROOT, check=False, stdout=subprocess.DEVNULL)
        for profile in profiles:
            uid, tenant = profile["id"], profile["tenant_id"]
            sql(f"DELETE FROM audit_events WHERE object_id IN (SELECT id::text FROM reports WHERE requested_by='{uid}') OR user_id='{uid}'; DELETE FROM reports WHERE requested_by='{uid}'; DELETE FROM users WHERE id='{uid}'; DELETE FROM tenants WHERE id='{tenant}';")


if __name__ == "__main__":
    run()
