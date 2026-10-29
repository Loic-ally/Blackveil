#!/usr/bin/env python3
"""Organizer regression for workspace administration and invitation boundaries."""
import importlib.util
import uuid
from pathlib import Path
from smoke import Client, require

spec = importlib.util.spec_from_file_location("worker_check", Path(__file__).with_name("verify-worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
sql = worker.sql


def run():
    suffix=uuid.uuid4().hex
    profiles=[]
    try:
        admin, outsider=Client(),Client()
        for client,name in ((admin,"admin"),(outsider,"outsider")):
            status,profile=client.request("/api/auth/register","POST",{"name":name,"company":f"Team QA {suffix}","email":f"{name}-{suffix}@example.test","password":"team-verification-password"})
            require(status==201,f"registration failed: {profile}");profiles.append(profile)
        require(admin.request("/api/team")[0]==403,"ordinary operator obtained administrator directory")
        sql(f"UPDATE users SET role='tenant_admin' WHERE id='{profiles[0]['id']}';")
        email=f"invited-{suffix}@example.test"
        status,invite=admin.request("/api/team/invitations","POST",{"email":email,"role":"maintenance"})
        require(status==201,f"invitation failed: {invite}")
        require(outsider.request(f"/api/team/invitations/{invite['id']}","DELETE")[0]==403,"ordinary operator revoked an invitation")
        sql(f"UPDATE users SET role='tenant_admin' WHERE id='{profiles[1]['id']}';")
        require(outsider.request(f"/api/team/invitations/{invite['id']}","DELETE")[0]==404,"foreign administrator revoked an invitation")
        require(outsider.request(f"/api/team/users/{profiles[0]['id']}","PATCH",{"role":"operator"})[0]==404,"foreign administrator changed a role")
        require(admin.request(f"/api/team/users/{profiles[0]['id']}","PATCH",{"role":"operator"})[0]==409,"administrator removed own access")
        require(admin.request("/api/team/invitations","POST",{"email":email,"role":"system_admin"})[0]==400,"workspace admin granted system authority")
        payload={"email":email,"name":"Invited teammate","password":"team-invitation-password","token":invite["url"].split("#")[1]}
        teammate=Client()
        require(teammate.request("/api/auth/invitations/accept","POST",dict(payload,email="wrong@example.test"))[0]==403,"invitation accepted with wrong email")
        status,joined=teammate.request("/api/auth/invitations/accept","POST",payload)
        require(status==201 and joined["tenant_id"]==profiles[0]["tenant_id"] and joined["role"]=="maintenance",f"invited identity mismatch: {joined}")
        require(Client().request("/api/auth/invitations/accept","POST",payload)[0]==403,"invitation was reusable")
        require(teammate.request("/api/team")[0]==403,"maintenance role gained administration")
        require(admin.request(f"/api/team/users/{joined['id']}","PATCH",{"role":"tenant_admin"})[0]==204,"role promotion failed")
        require(teammate.request("/api/team")[0]==200,"new role not reflected in current session")
        require(admin.request(f"/api/team/users/{joined['id']}","PATCH",{"role":"operator"})[0]==204,"role demotion failed")
        require(teammate.request("/api/team")[0]==403,"demoted session retained access")
        for kind in ("revoked","expired"):
            email=f"{kind}-{suffix}@example.test"
            status,item=admin.request("/api/team/invitations","POST",{"email":email,"role":"operator"})
            require(status==201,"could not create negative-test invitation")
            if kind=="revoked":
                require(admin.request(f"/api/team/invitations/{item['id']}","DELETE")[0]==204,"revocation failed")
            else:
                sql(f"UPDATE invitations SET expires_at=now()-interval '1 second' WHERE id='{item['id']}';")
            attempt=dict(payload,email=email,token=item["url"].split("#")[1])
            require(Client().request("/api/auth/invitations/accept","POST",attempt)[0]==403,f"{kind} invitation accepted")
        _,team=admin.request("/api/team")
        require(all("token_hash" not in item and "token" not in item for item in team["invitations"]),"invitation listing disclosed token material")
        _,events=admin.request("/api/audit")
        require(any(e["action"]=="user.role_changed" for e in events),"role audit missing")
        print("PASS: tenant-scoped team administration, invitation email binding/single use/revocation/expiry, role changes and immediate session enforcement.")
    finally:
        for profile in profiles:
            sql(f"DELETE FROM invitations WHERE tenant_id='{profile['tenant_id']}'; DELETE FROM tenants WHERE id='{profile['tenant_id']}';")


if __name__=="__main__":
    run()
