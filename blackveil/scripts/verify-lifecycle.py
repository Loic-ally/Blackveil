#!/usr/bin/env python3

import argparse
import subprocess
import sys
import time
import uuid
from pathlib import Path

from smoke import Client, require

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]
APP = ["aether-gateway", "aether-web", "aether-api", "aether-auth",
       "aether-legacy", "aether-telemetry", "aether-worker", "aether-db",
       "aether-cache", "aether-bus"]


def compose(*args):
    return subprocess.run(COMPOSE + list(args), cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def sql(statement):
    return subprocess.run(COMPOSE + ["exec", "-T", "aether-db", "sh", "-c",
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At'],
        input=statement, cwd=ROOT, check=True, capture_output=True,
        text=True).stdout.strip()


def workers(count):
    compose("up", "-d", "--no-deps", "--scale", f"aether-worker={count}", "aether-worker")


def run(restart_app):
    original_count = len(compose("ps", "-q", "aether-worker").splitlines())
    require(original_count > 0, "start the application before lifecycle verification")
    profiles, clients, jobs = [], [], []
    stopped_app = False
    try:
        suffix = uuid.uuid4().hex
        for index in range(2):
            client = Client()
            status, profile = client.request("/api/auth/register", "POST", {
                "name": "Lifecycle verification", "company": f"Lifecycle {suffix}-{index}",
                "email": f"lifecycle-{suffix}-{index}@example.test",
                "password": "local-lifecycle-verification-password"})
            require(status == 201, f"registration failed: {profile}")
            profiles.append(profile)
            clients.append(client)
            status, asset = client.request("/api/assets", "POST", {
                "code": f"QA-{index}", "name": f"Lifecycle marker {index}",
                "category": "Turbine", "location": "Verification bay"})
            require(status == 201, f"asset creation failed: {asset}")

        compose("stop", "aether-worker")
        for index, client in enumerate(clients):
            for _ in range(12):
                status, report = client.request("/api/reports", "POST", {"type": "asset-inventory"})
                require(status == 202, f"report queue failed: {report}")
                jobs.append((index, report["id"]))
        ids = ",".join(f"'{report_id}'" for _, report_id in jobs)
        require(sql(f"SELECT count(*) FROM reports WHERE id IN ({ids}) AND status='queued' AND attempt_count=0;") == "24",
                "reports were claimed while workers were stopped")

        if restart_app:
            print("Restarting application services with persistent volumes retained.", flush=True)
            stopped_app = True
            compose("stop", *APP)
            compose("up", "-d", "--wait", "--wait-timeout", "180",
                    *[service for service in APP if service != "aether-worker"])
            stopped_app = False
        for index, client in enumerate(clients):
            status, me = client.request("/api/me")
            require(status == 200 and me["id"] == profiles[index]["id"],
                    "persisted session did not resolve its original identity")

        workers(3)
        require(len(compose("ps", "-q", "aether-worker").splitlines()) == 3,
                "expected three running worker replicas")
        deadline = time.monotonic() + 60
        while True:
            completed = sql(f"SELECT count(*) FROM reports WHERE id IN ({ids}) AND status='complete';")
            notices = sql("SELECT count(*) FROM notifications WHERE user_id IN (" +
                          ",".join(f"'{p['id']}'" for p in profiles) +
                          ") AND message='Your AETHER asset-inventory report is ready.';")
            if completed == "24" and notices == "24":
                break
            require(time.monotonic() < deadline,
                    f"competing workers timed out: {completed}/24 reports, {notices}/24 notifications")
            time.sleep(0.3)
        require(sql(f"SELECT count(*) FROM reports WHERE id IN ({ids}) AND attempt_count=1 AND lease_until IS NULL;") == "24",
                "a report was claimed more than once or retained its lease")
        for index, report_id in jobs:
            status, content = clients[index].request(f"/api/reports/{report_id}")
            require(status == 200 and f"QA-{index}" in content and f"QA-{1-index}" not in content,
                    "report content lost its tenant boundary")
            status, _ = clients[1-index].request(f"/api/reports/{report_id}")
            require(status == 404, "another tenant downloaded a lifecycle report")
        print("PASS: 24 durable jobs, three workers, single claims and notifications, session persistence and tenant isolation."
              + (" Application/database restart verified." if restart_app else ""))
    finally:
        if stopped_app:
            compose("up", "-d", "--wait", "--wait-timeout", "180", *APP)
        compose("stop", "aether-worker")
        try:
            for profile in profiles:
                sql(f"DELETE FROM tenants WHERE id='{profile['tenant_id']}';")
        finally:
            workers(original_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart-app", action="store_true",
                        help="also stop/start application and database services (brief downtime)")
    try:
        run(parser.parse_args().restart_app)
    except subprocess.CalledProcessError as error:
        print(error.stderr or error.stdout or str(error), file=sys.stderr)
        raise
