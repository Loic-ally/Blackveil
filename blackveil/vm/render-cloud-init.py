#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

TENANTS = (
    ("4f3e2d1c-0b9a-4876-9d5c-4b3a29180716", 4101),
    ("9a8b7c6d-5e4f-4321-8abc-def012345678", 4102),
)

ARCHIVES = {
    4101: json.dumps({"legacy_tenant_no": 4101, "record": "north-works / pump train P-04 / seal inspection 2023-11-14"}),
    4102: json.dumps({"legacy_tenant_no": 4102, "record": "harbor-process / compressor C-17 / vibration review 2023-11-16"}),
}

UNIT = """[Unit]
Description=AETHER legacy identity agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aether-agent
Group=aether-agent
EnvironmentFile=/etc/aether-agent/agent.env
ExecStart=/usr/local/sbin/aether-agent
Restart=on-failure
RestartSec=2
NoNewPrivileges=yes
PrivateDevices=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
CapabilityBoundingSet=
AmbientCapabilities=
ReadOnlyPaths=/etc/aether-agent
ReadOnlyPaths=/var/lib/aether-agent

[Install]
WantedBy=multi-user.target
"""

UNIT_INDEXER = """[Unit]
Description=AETHER legacy record indexer (legacy-envelope/0 compatibility)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aether-indexer
Group=aether-indexer
Environment=AETHER_AGENT_MODE={mode}
ExecStart=/usr/local/sbin/aether-indexer
Restart=on-failure
RestartSec=2
NoNewPrivileges=yes
PrivateDevices=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
CapabilityBoundingSet=
AmbientCapabilities=
ReadOnlyPaths=/etc/aether-indexer

[Install]
WantedBy=multi-user.target
"""

UNIT_PROVISIONER = """[Unit]
Description=AETHER confined provisioning service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aether-prov
Group=aether-prov
Environment=AETHER_AGENT_MODE={mode}
ExecStart=/usr/local/sbin/aether-provisioner
Restart=on-failure
RestartSec=2
NoNewPrivileges=yes
PrivateTmp=yes
PrivateMounts=yes
ProtectHome=yes
ProtectSystem=strict
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
CapabilityBoundingSet=
AmbientCapabilities=
ReadOnlyPaths=/etc/aether-provisioner

[Install]
WantedBy=multi-user.target
"""


def block(path: str, content: str, mode: str, owner: str = "root:root") -> str:
    lines = [
        "  - path: " + json.dumps(path),
        "    owner: " + json.dumps(owner),
        "    permissions: " + json.dumps(mode),
        "    content: " + json.dumps(content),
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, type=Path)
    parser.add_argument("--indexer", required=True, type=Path)
    parser.add_argument("--provisioner", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--key", required=True)
    parser.add_argument("--mode", choices=("challenge", "patched"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(args.key) < 64 or any(char not in "0123456789abcdefABCDEF" for char in args.key):
        raise SystemExit("agent key must be at least 32 bytes in hexadecimal")

    agent = base64.b64encode(args.agent.read_bytes()).decode("ascii")
    indexer = base64.b64encode(args.indexer.read_bytes()).decode("ascii")
    indexer_key = hmac.new(bytes.fromhex(args.key), b"aether-indexer-transport/v0",
                           hashlib.sha256).hexdigest()
    provisioner = base64.b64encode(args.provisioner.read_bytes()).decode("ascii")
    provisioner_ticket = hmac.new(bytes.fromhex(args.key), b"aether-provisioner-ticket/v0",
                                  hashlib.sha256).hexdigest()
    prov_key = hmac.new(bytes.fromhex(args.key), b"aether-provenance/v0", hashlib.sha256).digest()
    prov_service, (prov_uuid, prov_no), prov_issued = "svc:aether-reporting", TENANTS[0], int(time.time())

    def _tlv(tag, value):
        raw = str(value).encode()
        return bytes([tag]) + len(raw).to_bytes(2, "big") + raw

    prov_tlv = (b"AEP\x00" + _tlv(1, prov_service) + _tlv(2, prov_uuid)
                + _tlv(3, prov_no) + _tlv(4, prov_issued))
    prov_sig = hmac.new(prov_key, prov_tlv, hashlib.sha256).hexdigest()
    provenance_blob = json.dumps({
        "format": "provenance/1", "service": prov_service, "tenant_uuid": prov_uuid,
        "legacy_tenant_no": prov_no, "issued_at": prov_issued,
        "tlv": prov_tlv.hex(), "sig": prov_sig,
    }, indent=2)
    incident_seed = hmac.new(bytes.fromhex(args.key), b"aether-incident/v0", hashlib.sha256).digest()
    inc_offset = incident_seed[0] % 40 + 20
    inc_base = 1_793_000_000
    inc_job = "mig-" + incident_seed.hex()[:8]
    (north_uuid, north_no), (harbor_uuid, harbor_no) = TENANTS[0], TENANTS[1]
    worker_jsonl = "\n".join(json.dumps(row) for row in [
        {"ts": inc_base, "job": "hb-0", "event": "heartbeat"},
        {"ts": inc_base + 120, "job": inc_job, "actor_no": north_no, "target_no": north_no, "event": "archive_request"},
        {"ts": inc_base + 121, "job": inc_job, "actor_no": north_no, "target_no": north_no, "event": "archive_request_retry"},
        {"ts": inc_base + 300, "job": inc_job, "actor_no": north_no, "target_no": harbor_no, "event": "archive_request"},
    ]) + "\n"
    agent_trace = "\n".join(json.dumps(row) for row in [
        {"gts": inc_base + inc_offset, "event": "heartbeat", "ref": "hb-0"},
        {"gts": inc_base + 120 + inc_offset, "job": inc_job, "resolved_no": north_no},
        {"gts": inc_base + 300 + inc_offset, "job": inc_job, "resolved_no": harbor_no},
    ]) + "\n"
    api_audit = "\n".join(json.dumps(row) for row in [
        {"ts": inc_base + 60, "actor_uuid": north_uuid, "action": "reporting.enrolled"},
        {"ts": inc_base + 290, "actor_uuid": north_uuid, "action": "operator.recovered"},
    ]) + "\n"
    deployment_jsonl = "\n".join(json.dumps(row) for row in [
        {"ts": inc_base + 110, "event": "dispatch", "id": "d-north", "job": inc_job,
         "principal": "svc:aether-reporting", "requested_no": north_no},
        {"ts": inc_base + 121, "event": "retry", "id": "d-north", "job": inc_job,
         "reason": "worker lease expired"},
        {"ts": inc_base + 295, "event": "dispatch", "id": "d-harbor", "job": inc_job,
         "principal": "svc:aether-reporting", "requested_no": harbor_no,
         "provenance": "migration-map fallback"},
    ]) + "\n"
    incident_metadata = json.dumps({
        "map": {north_uuid: north_no, harbor_uuid: harbor_no}, "window": [inc_base, inc_base + 600],
    }, indent=2) + "\n"
    incident_notes = (
        "Incident evidence (migration window). The guest clock was not NTP-synced: "
        "align the agent trace to UTC using the heartbeat 'hb-0' present in both "
        "worker.jsonl and agent-trace.log. Correlate deployment dispatch IDs and API actor history; then find the request whose resolved "
        "tenant number differs from the actor's.\n")
    public_key = args.public_key.read_text().strip()
    tenant_map = "".join(f"{uuid},{legacy}\n" for uuid, legacy in TENANTS)
    agent_env = f"AETHER_AGENT_MODE={args.mode}\n"
    files = [
        "  - path: /usr/local/sbin/aether-agent\n    owner: root:root\n    permissions: '0755'\n    encoding: b64\n    content: " + agent,
        block("/etc/aether-agent/agent.env", agent_env, "0600"),
        block("/etc/aether-agent/worker.key", args.key + "\n", "0600"),
        block("/etc/aether-agent/tenant-map.csv", tenant_map, "0600"),
        block("/etc/aether-agent/operator.pub", public_key + "\n", "0600"),
        block("/etc/systemd/system/aether-agent.service", UNIT, "0644"),
        block("/etc/ssh/sshd_config.d/80-blackveil.conf", "PasswordAuthentication no\nPermitRootLogin no\nAllowUsers operator\n", "0644"),
        "  - path: /usr/local/sbin/aether-indexer\n    owner: root:root\n    permissions: '0755'\n    encoding: b64\n    content: " + indexer,
        block("/etc/aether-indexer/transport.key", indexer_key + "\n", "0600"),
        block("/etc/systemd/system/aether-indexer.service", UNIT_INDEXER.format(mode=args.mode), "0644"),
        "  - path: /usr/local/sbin/aether-provisioner\n    owner: root:root\n    permissions: '0755'\n    encoding: b64\n    content: " + provisioner,
        block("/etc/aether-provisioner/ticket", provisioner_ticket + "\n", "0600"),
        block("/etc/systemd/system/aether-provisioner.service", UNIT_PROVISIONER.format(mode=args.mode), "0644"),
        block("/var/lib/aether-provisioner/templates/default.tmpl",
              "AETHER provisioning template v1\nregion={{region}}\nstore=confined\n", "0640"),
        block("/var/lib/aether-provisioner/provenance.blob", provenance_blob + "\n", "0640"),
    ]
    for legacy, content in ARCHIVES.items():
        files.append(block(f"/var/lib/aether-agent/archive-{legacy}.json", content + "\n", "0600"))

    job_id = "mig-capture-" + secrets.token_hex(4)
    principal = "svc:aether-reporting"
    sample_uuid, sample_no = TENANTS[0]
    issued_at = int(time.time())
    if args.mode == "patched":
        projection = f"{job_id}\n{principal}\n{sample_uuid}\n{sample_no}\n{issued_at}"
    else:
        projection = f"{job_id}\n{principal}\n{sample_uuid}"
    signature = hmac.new(bytes.fromhex(args.key), projection.encode(), hashlib.sha256).hexdigest()
    sample = json.dumps({
        "job_id": job_id, "principal": principal, "tenant_uuid": sample_uuid,
        "legacy_tenant_no": sample_no, "issued_at": issued_at, "signature": signature,
    }, indent=2)
    files.append(block("/var/lib/aether-migration/last-archive-request.json", sample + "\n", "0644"))
    files.append(block("/var/lib/aether-migration/incident/deployment.jsonl", deployment_jsonl, "0644"))
    files.append(block("/var/lib/aether-migration/incident/worker.jsonl", worker_jsonl, "0644"))
    files.append(block("/var/lib/aether-migration/incident/agent-trace.log", agent_trace, "0644"))
    files.append(block("/var/lib/aether-migration/incident/api-audit.jsonl", api_audit, "0644"))
    files.append(block("/var/lib/aether-migration/incident/migration-metadata.json", incident_metadata, "0644"))
    files.append(block("/var/lib/aether-migration/incident/NOTES", incident_notes, "0644"))
    files.append(block("/var/lib/aether-migration/README",
        "Retained capture of the last reporting-archive request submitted to "
        "aether-agent during migration validation. The agent at 127.0.0.1:8080 "
        "serves POST /v1/legacy/archive; GET /v1/build reports the protocol.\n"
        "\n"
        "A legacy record indexer (legacy-envelope/0) remains on 127.0.0.1:9090 "
        "for backward compatibility with pre-migration binary records.\n", "0644"))

    cloud_config = "\n".join([
        "#cloud-config",
        "hostname: aether-linux",
        "manage_etc_hosts: true",
        "ssh_pwauth: false",
        "disable_root: true",
        "users: []",
        "write_files:",
        *files,
        "runcmd:",
        "  - [systemctl, daemon-reload]",
        "  - [/usr/sbin/useradd, --create-home, --shell, /bin/bash, --gid, operator, operator]",
        "  - [/usr/sbin/usermod, --lock, operator]",
        "  - [/usr/bin/install, -d, -o, operator, -g, operator, -m, '0700', /home/operator/.ssh]",
        "  - [/usr/bin/install, -o, operator, -g, operator, -m, '0600', /etc/aether-agent/operator.pub, /home/operator/.ssh/authorized_keys]",
        "  - [/usr/sbin/useradd, --system, --user-group, --home-dir, /nonexistent, --shell, /usr/sbin/nologin, --no-create-home, aether-agent]",
        "  - [/usr/bin/install, -d, -o, root, -g, aether-agent, -m, '0750', /var/lib/aether-agent]",
        "  - [/bin/chown, -R, 'root:aether-agent', /etc/aether-agent, /var/lib/aether-agent]",
        "  - [/bin/chmod, '0440', /etc/aether-agent/agent.env, /etc/aether-agent/worker.key]",
        "  - [/bin/chmod, '0640', /etc/aether-agent/tenant-map.csv, /var/lib/aether-agent/archive-4101.json, /var/lib/aether-agent/archive-4102.json]",
        "  - [/bin/rm, -f, /etc/aether-agent/operator.pub]",
        "  - [/usr/sbin/useradd, --system, --user-group, --home-dir, /nonexistent, --shell, /usr/sbin/nologin, --no-create-home, aether-indexer]",
        "  - [/bin/chown, 'root:aether-indexer', /etc/aether-indexer/transport.key]",
        "  - [/bin/chmod, '0640', /etc/aether-indexer/transport.key]",
        "  - [systemctl, enable, --now, aether-indexer.service]",
        "  - [/usr/sbin/useradd, --system, --user-group, --home-dir, /nonexistent, --shell, /usr/sbin/nologin, --no-create-home, aether-prov]",
        "  - [/bin/chown, 'root:aether-prov', /etc/aether-provisioner/ticket]",
        "  - [/bin/chmod, '0640', /etc/aether-provisioner/ticket]",
        "  - [/bin/chown, -R, 'root:aether-prov', /var/lib/aether-provisioner]",
        "  - [/bin/chmod, '0750', /var/lib/aether-provisioner, /var/lib/aether-provisioner/templates]",
        "  - [/bin/chmod, '0640', /var/lib/aether-provisioner/templates/default.tmpl, /var/lib/aether-provisioner/provenance.blob]",
        "  - [systemctl, enable, --now, aether-provisioner.service]",
        "  - [systemctl, enable, --now, aether-agent.service]",
        "  - [systemctl, restart, ssh.service]",
        "  - [/bin/sh, -c, 'if id debian >/dev/null 2>&1; then usermod -L debian; gpasswd -d debian sudo >/dev/null 2>&1 || true; userdel --remove debian || true; fi']",
        "",
    ])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "user-data").write_text(cloud_config)
    binary_hash = hashlib.sha256(
        args.agent.read_bytes() + args.indexer.read_bytes() + args.provisioner.read_bytes()
    ).hexdigest()[:12]
    (args.output / "meta-data").write_text(
        f"instance-id: blackveil-aether-linux-{binary_hash}\nlocal-hostname: aether-linux\n"
    )


if __name__ == "__main__":
    main()
