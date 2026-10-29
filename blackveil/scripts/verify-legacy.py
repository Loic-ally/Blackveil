#!/usr/bin/env python3
"""Private organizer verification of stage 01 in both API modes."""
import importlib.util
import os
import subprocess
import time
import uuid
from pathlib import Path
from smoke import Client, require

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("worker_check",Path(__file__).with_name("verify-worker.py"))
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def switch(mode):
    environment=dict(os.environ,AETHER_IDENTITY_MODE=mode)
    subprocess.run(worker.COMPOSE+["up","-d","--no-deps","--wait","aether-api"],cwd=ROOT,env=environment,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(worker.COMPOSE+["exec","-T","aether-gateway","nginx","-s","reload"],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def report(client,tenant,number):
    status,item=client.request("/api/v2/reports/historical","POST",{"tenant_uuid":tenant,"legacy_tenant_no":number})
    require(status==202,f"historical queue failed: {item}")
    deadline=time.monotonic()+30
    while True:
        _,items=client.request("/api/reports")
        current=next(r for r in items if r["id"]==item["id"])
        if current["status"] in ("complete","failed"): break
        require(time.monotonic()<deadline,"historical worker timed out");time.sleep(.3)
    require(current["status"]=="complete",f"historical worker failed: {current}")
    status,content=client.request(f"/api/reports/{item['id']}")
    require(status==200,"CSV unavailable")
    return item["id"],content


def verify(mode):
    client=Client();suffix=uuid.uuid4().hex
    status,profile=client.request("/api/auth/register","POST",{"name":"Historical QA","email":f"historical-{suffix}@example.test","company":f"Historical QA {suffix}","password":"historical-verification-password"})
    require(status==201,"signup failed")
    uid,tenant=profile["id"],profile["tenant_id"]
    try:
        foreign="9a8b7c6d-5e4f-4321-8abc-def012345678"
        status,_=client.request("/api/v2/reports/historical","POST",{"tenant_uuid":foreign,"legacy_tenant_no":4102})
        require(status==403,"modern tenant boundary failed")
        rid,csv=report(client,tenant,4102)
        if mode=="challenge":
            require("Harbor Process" in csv and foreign in csv,"challenge identity mismatch did not disclose bounded migration record")
        else:
            require(len(csv.strip().splitlines())==1,"patched unenrolled workspace received foreign archive")
        _,events=client.request("/api/audit")
        event=next(e for e in events if e["object_id"]==rid and e["action"]=="historical.queued")
        require(event["detail"]["tenant_uuid"]==tenant,"audit lost canonical tenant")
        expected=4102 if mode=="challenge" else 0
        require(event["detail"]["legacy_tenant_no"]==expected,"audit selector disagrees with selected mode")
        # Verify legitimate archive access without granting administrative privileges.
        north="4f3e2d1c-0b9a-4876-9d5c-4b3a29180716"
        worker.sql(f"UPDATE users SET tenant_id='{north}' WHERE id='{uid}';")
        _,csv=report(client,north,4101)
        require("North Works" in csv,"legitimate historical report regressed")
        if mode=="patched":
            _,csv=report(client,north,4102)
            require("North Works" in csv and "Harbor Process" not in csv,"patched enrolled workspace did not use canonical identity")
        print(f"PASS: stage 01 {mode}: UUID boundary, async historical CSV, canonical patched resolution, and audit evidence.")
    finally:
        worker.sql(f"DELETE FROM audit_events WHERE object_id IN (SELECT id::text FROM reports WHERE requested_by='{uid}') OR user_id='{uid}'; DELETE FROM reports WHERE requested_by='{uid}'; DELETE FROM users WHERE id='{uid}'; DELETE FROM tenants WHERE id='{tenant}';")


def main():
    original=os.environ.get("AETHER_IDENTITY_MODE","")
    if not original:
        original=next((line.split("=",1)[1] for line in (ROOT/".env").read_text().splitlines() if line.startswith("AETHER_IDENTITY_MODE=")),"challenge")
    try:
        for mode in ("challenge","patched"):
            switch(mode);verify(mode)
    finally:
        switch(original)


if __name__=="__main__":main()
