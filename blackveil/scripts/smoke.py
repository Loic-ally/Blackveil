#!/usr/bin/env python3
"""Black-box integration check for the ordinary AETHER workspace workflows."""

from __future__ import annotations

import http.cookiejar
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid


BASE = os.environ.get("AETHER_SMOKE_URL", "https://127.0.0.1")
HOST = "aether.blackveil.test"
ORIGIN = "https://aether.blackveil.test"


class Client:
    def __init__(self) -> None:
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
        )

    def request(self, path: str, method: str = "GET", body: object | None = None):
        headers = {"Host": HOST, "Origin": ORIGIN, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        value = json.loads(raw) if "application/json" in content_type and raw else raw.decode()
        return response.status, value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    anon = Client()
    deadline = time.monotonic() + 30
    while True:
        try:
            status, _ = anon.request("/healthz")
            if status == 200:
                break
        except (urllib.error.URLError, TimeoutError):
            pass
        if time.monotonic() >= deadline:
            raise AssertionError("AETHER gateway did not become ready within 30 seconds")
        time.sleep(0.5)

    status, _ = anon.request("/api/me")
    require(status == 401, f"anonymous session should be denied, got {status}")

    suffix = uuid.uuid4().hex[:12]
    alice = Client()
    password = "local-test-password-2026"
    email = f"avery-{suffix}@example.test"
    status, profile = alice.request("/api/auth/register", "POST", {
        "name": "Avery Operator", "email": email,
        "company": f"Northstar Works {suffix}", "password": password,
    })
    require(status == 201, f"registration failed: {profile}")
    status, me = alice.request("/api/me")
    require(status == 200 and me["role"] == "operator", "registration should create an ordinary operator")
    status, _ = alice.request("/api/lab/terminal")
    require(status == 403, "ordinary operators must not enter the restricted Linux lab")

    status, dashboard = alice.request("/api/dashboard")
    require(status == 200 and dashboard["assets_total"] == 3, "new tenant should receive three assets")
    asset = dashboard["assets"][0]
    status, history = alice.request(f"/api/assets/{asset['id']}/telemetry?hours=24")
    require(status == 200 and len(history) >= 48, f"asset telemetry history should be populated (status={status}, result={len(history) if isinstance(history, list) else history})")

    status, created = alice.request("/api/assets", "POST", {
        "code": "T-900", "name": "Smoke-test turbine", "category": "Turbine", "location": "Test bay",
    })
    require(status == 201, f"equipment creation failed: {created}")
    status, incident = alice.request("/api/incidents", "POST", {
        "asset_id": asset["id"], "title": "Seal pressure drift", "description": "Observed during test",
        "severity": "medium",
    })
    require(status == 201, f"incident creation failed: {incident}")
    status, changed = alice.request(f"/api/incidents/{incident['id']}", "PATCH", {"status": "acknowledged"})
    require(status == 200 and changed["status"] == "acknowledged", "incident status transition failed")

    for report_type, expected in (("asset-inventory", "T-900"), ("maintenance-summary", "Seal pressure drift")):
        status, report = alice.request("/api/reports", "POST", {"type": report_type})
        require(status == 202, f"report request failed: {report}")
        current = None
        for _ in range(50):
            time.sleep(0.4)
            status, reports = alice.request("/api/reports")
            current = next((item for item in reports if item["id"] == report["id"]), None)
            if current and current["status"] in ("complete", "failed"):
                break
        require(current is not None and current["status"] == "complete", f"background report did not complete: {current}")
        status, csv_body = alice.request(f"/api/reports/{report['id']}")
        require(status == 200 and expected in csv_body, f"{report_type} should contain its workspace record")
        if report_type == "asset-inventory":
            require("P-101" in csv_body, "inventory should include seeded equipment")

    status, notices = alice.request("/api/notifications")
    require(status == 200 and any("report is ready" in item["message"] for item in notices), "worker should notify the requester")
    status, events = alice.request("/api/audit")
    require(status == 200 and any(item["action"] == "incident.status_changed" for item in events), "audit log should record incident changes")

    bob = Client()
    status, _ = bob.request("/api/auth/register", "POST", {
        "name": "Morgan Operator", "email": f"morgan-{suffix}@example.test",
        "company": f"Riverside Energy {suffix}", "password": "local-test-password-2026",
    })
    require(status == 201, "second tenant registration failed")
    status, bob_dashboard = bob.request("/api/dashboard")
    require(status == 200 and bob_dashboard["assets_total"] == 3, "second tenant workspace was not created")
    require(all(item["id"] != asset["id"] for item in bob_dashboard["assets"]), "dashboard returned another tenant's asset")
    status, _ = bob.request(f"/api/reports/{report['id']}")
    require(status == 404, "report lookup must be tenant-scoped")
    status, foreign_history = bob.request(f"/api/assets/{asset['id']}/telemetry?hours=24")
    require(status == 200 and foreign_history == [], "telemetry query must not disclose another tenant's data")
    status, _ = bob.request("/api/incidents", "POST", {
        "asset_id": asset["id"], "title": "Cross-tenant probe", "severity": "low",
    })
    require(status == 404, "incident creation must reject another tenant's equipment")

    status, _ = alice.request("/api/auth/logout", "POST", {})
    require(status == 204, "logout failed")
    status, _ = alice.request("/api/me")
    require(status == 401, "logout must revoke the session")
    status, _ = alice.request("/api/auth/login", "POST", {"email": email, "password": password})
    require(status == 200, "valid login should create a new session")
    status, _ = alice.request("/api/me")
    require(status == 200, "newly authenticated session should be usable")
    status, _ = alice.request("/api/auth/logout", "POST", {})
    require(status == 204, "second logout failed")
    print("PASS: signup/login/logout, tenant isolation, assets, telemetry, incidents, audit, notifications, async reports")


if __name__ == "__main__":
    run()
