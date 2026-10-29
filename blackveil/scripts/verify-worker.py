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
        deadline = time.monotonic() + 30
        while True:
            status, reports = owner.request("/api/reports")
            current = next(item for item in reports if item["id"] == report["id"])
            if current["status"] in ("complete", "failed"):
                break
            require(time.monotonic() < deadline, "archive job timed out")
            time.sleep(0.3)
        require(current["status"] == "complete", f"worker failed: {current}")
        status, content = owner.request(f"/api/reports/{report['id']}")
        require(status == 200 and "north-works" in content and "4101" in content, "native archive CSV missing")
        status, _ = outsider.request(f"/api/reports/{report['id']}")
        require(status == 404, "foreign tenant downloaded archive")
        status, events = owner.request("/api/audit")
        event = next(item for item in events if item["action"] == "archive.resolved" and item["object_id"] == report["id"])
        require(event["detail"]["tenant_uuid"] == me["tenant_id"] and len(event["detail"]["signature"]) == 64, "archive provenance missing")
        _, notices = owner.request("/api/notifications")
        require(any("legacy-archive report is ready" in n["message"] for n in notices), "archive notification missing")
        print("PASS: HTTPS archive queue -> real worker -> VM agent -> CSV, provenance, notification; enrollment and tenant isolation enforced.")
    finally:
        for profile in profiles:
            uid, tenant = profile["id"], profile["tenant_id"]
            sql(f"DELETE FROM audit_events WHERE object_id IN (SELECT id::text FROM reports WHERE requested_by='{uid}') OR user_id='{uid}'; DELETE FROM reports WHERE requested_by='{uid}'; DELETE FROM users WHERE id='{uid}'; DELETE FROM tenants WHERE id='{tenant}';")


if __name__ == "__main__":
    run()
