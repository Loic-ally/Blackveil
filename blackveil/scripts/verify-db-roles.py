#!/usr/bin/env python3
"""Check runtime database roles are non-superuser and narrowly scoped."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]

QUERY = """
SELECT
  (SELECT rolsuper FROM pg_roles WHERE rolname='aether_api'),
  (SELECT rolsuper FROM pg_roles WHERE rolname='aether_auth'),
  (SELECT rolsuper FROM pg_roles WHERE rolname='aether_worker'),
  (SELECT rolsuper FROM pg_roles WHERE rolname='aether_legacy'),
  (SELECT rolsuper FROM pg_roles WHERE rolname='aether_telemetry'),
  has_table_privilege('aether_legacy','legacy_history','SELECT'),
  has_table_privilege('aether_legacy','users','SELECT'),
  has_table_privilege('aether_telemetry','telemetry','INSERT'),
  has_table_privilege('aether_telemetry','users','SELECT'),
  has_schema_privilege('aether_api','public','CREATE'),
  has_schema_privilege('aether_worker','public','CREATE'),
  has_column_privilege('aether_api','invitations','revoked_at','UPDATE'),
  has_table_privilege('aether_worker','reports','UPDATE'),
  has_table_privilege('aether_worker','users','SELECT'),
  has_column_privilege('aether_api','users','tenant_id','UPDATE'),
  has_column_privilege('aether_api','users','role','UPDATE'),
  has_table_privilege('aether_api','users','INSERT'),
  has_table_privilege('aether_api','sessions','SELECT'),
  has_table_privilege('aether_auth','worker_service_identities','SELECT'),
  has_column_privilege('aether_auth','users','role','UPDATE'),
  has_table_privilege('aether_worker','reports','INSERT'),
  has_table_privilege('aether_worker','audit_events','INSERT'),
  has_table_privilege('aether_api','administrator_recovery_receipts','SELECT'),
  has_table_privilege('aether_api','administrator_recovery_receipts','INSERT'),
  has_table_privilege('aether_api','administrator_recovery_redemptions','INSERT'),
  has_table_privilege('aether_api','administrator_recovery_redemptions','DELETE'),
  has_table_privilege('aether_auth','administrator_recovery_receipts','SELECT'),
  has_table_privilege('aether_worker','administrator_recovery_receipts','SELECT'),
  has_table_privilege('aether_legacy','administrator_recovery_receipts','SELECT');
"""


def main():
    result = subprocess.run(
        COMPOSE + ["exec", "-T", "aether-db", "sh", "-c",
                   'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F,'],
        input=QUERY, text=True, cwd=ROOT, capture_output=True)
    if result.returncode:
        raise SystemExit(f"database role query failed: {result.stderr.strip()}")
    expected = "f,f,f,f,f,t,f,t,f,f,f,t,t,f,f,t,f,f,f,f,f,t,t,f,t,f,f,f,f"
    actual = result.stdout.strip()
    if actual != expected:
        raise SystemExit(f"unexpected service-role privileges: {actual}")
    for service, role in (
        ("aether-api", "aether_api"),
        ("aether-auth", "aether_auth"),
        ("aether-worker", "aether_worker"),
        ("aether-legacy", "aether_legacy"),
        ("aether-telemetry", "aether_telemetry"),
    ):
        container = subprocess.run(COMPOSE + ["ps", "-q", service], cwd=ROOT,
                                   check=True, capture_output=True, text=True).stdout.strip()
        raw_env = subprocess.run(["docker", "inspect", "--format", "{{json .Config.Env}}", container],
                                 cwd=ROOT, check=True, capture_output=True, text=True).stdout
        variables = json.loads(raw_env)
        dsn = next((value for value in variables if value.startswith("DATABASE_URL=")), "")
        if not dsn.startswith(f"DATABASE_URL=postgres://{role}:"):
            raise SystemExit(f"{service} is not configured with its dedicated database role")
        if any(value.startswith("AETHER_DB_PASSWORD=") for value in variables):
            raise SystemExit(f"{service} has the database owner password in its environment")
    print("PASS: runtime database roles are non-superuser and separately configured; sensitive legacy, telemetry, API and worker grants are bounded.")


if __name__ == "__main__":
    main()
