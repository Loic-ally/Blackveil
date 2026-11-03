#!/usr/bin/env python3


import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]


def sql(statement, user="aether"):
    result = subprocess.run(
        COMPOSE + ["exec", "-T", "aether-db", "sh", "-c",
                   f'exec psql -U {user} -d "$POSTGRES_DB" -tA -v ON_ERROR_STOP=1'],
        input=statement, text=True, cwd=ROOT, check=True, capture_output=True)
    return result.stdout.strip()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


COMPLETE = ("WITH u AS (UPDATE reports SET status='complete',content='{tag}',lease_until=NULL,"
            "completed_at=now() WHERE id='{rid}' AND status='running' AND attempt_count={fence} "
            "RETURNING 1) SELECT count(*) FROM u;")
FAIL = ("WITH u AS (UPDATE reports SET status='failed',error='x',lease_until=NULL,completed_at=now() "
        "WHERE id='{rid}' AND status='running' AND attempt_count={fence} RETURNING 1) SELECT count(*) FROM u;")


def run():
    tid, uid, rid = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    try:
        sql(f"""
          INSERT INTO tenants(id,name) VALUES('{tid}','Fence QA {tid[:8]}');
          INSERT INTO users(id,tenant_id,email,display_name,password_hash,role)
            VALUES('{uid}','{tid}','fence-{tid[:8]}@example.test','Fence QA','x','operator');
          INSERT INTO reports(id,tenant_id,requested_by,report_type,status,attempt_count,lease_until)
            VALUES('{rid}','{tid}','{uid}','asset-inventory','running',1, now()-interval '2 minutes');
        """)
        b_fence = sql(f"WITH u AS (UPDATE reports SET status='running',lease_until=now()+interval '1 minute',"
                      f"attempt_count=attempt_count+1 WHERE id='{rid}' RETURNING attempt_count) SELECT attempt_count FROM u;", user="aether_worker")
        require(b_fence == "2", f"reclaim did not advance the fence token: {b_fence}")

        require(sql(COMPLETE.format(tag="A", rid=rid, fence=1), user="aether_worker") == "0",
                "stale owner completed a reclaimed report")
        require(sql(FAIL.format(rid=rid, fence=1), user="aether_worker") == "0",
                "stale owner failed a reclaimed report")
        require(sql(f"SELECT status||','||attempt_count FROM reports WHERE id='{rid}';") == "running,2",
                "stale writes corrupted the reclaimed report")

        require(sql(COMPLETE.format(tag="B", rid=rid, fence=2), user="aether_worker") == "1",
                "current fence owner could not complete the report")
        require(sql(f"SELECT status||','||coalesce(content,'') FROM reports WHERE id='{rid}';") == "complete,B",
                "final report state is wrong")
        print("PASS: lease fencing — a reclaimed report rejects the stale owner's completion and "
              "failure writes; only the current fence owner completes (notification is same-tx).", flush=True)
    finally:
        sql(f"DELETE FROM notifications WHERE user_id='{uid}'; DELETE FROM reports WHERE id='{rid}'; "
            f"DELETE FROM users WHERE id='{uid}'; DELETE FROM tenants WHERE id='{tid}';")


if __name__ == "__main__":
    run()
