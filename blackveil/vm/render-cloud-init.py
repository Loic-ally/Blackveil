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
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--key", required=True)
    parser.add_argument("--mode", choices=("challenge", "patched"), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(args.key) < 64 or any(char not in "0123456789abcdefABCDEF" for char in args.key):
        raise SystemExit("agent key must be at least 32 bytes in hexadecimal")

    agent = base64.b64encode(args.agent.read_bytes()).decode("ascii")
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
    ]
    for legacy, content in ARCHIVES.items():
        files.append(block(f"/var/lib/aether-agent/archive-{legacy}.json", content + "\n", "0600"))

    # Stage 07 (BV-07-AGENT-DISCOVERY) evidence: a retained, operator-readable
    # capture of one legitimate worker-signed archive request (North Works,
    # installation 4101). This is a captured message, NOT the signing key: the
    # operator cannot forge a new envelope, but in challenge mode the signature
    # covers only (job_id, principal, tenant_uuid), so substituting
    # legacy_tenant_no still selects a foreign archive — the Stage 08 step the
    # player must perform. The patched agent signs the number and enforces the
    # timestamp, so both substitution and replay of this capture are refused.
    job_id = "mig-capture-" + secrets.token_hex(4)
    principal = "svc:aether-reporting"
    sample_uuid, sample_no = TENANTS[0]  # North Works, 4101
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
    files.append(block("/var/lib/aether-migration/README",
        "Retained capture of the last reporting-archive request submitted to "
        "aether-agent during migration validation. The agent at 127.0.0.1:8080 "
        "serves POST /v1/legacy/archive; GET /v1/build reports the protocol.\n", "0644"))

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
        "  - [systemctl, enable, --now, aether-agent.service]",
        "  - [systemctl, restart, ssh.service]",
        "  - [/bin/sh, -c, 'if id debian >/dev/null 2>&1; then usermod -L debian; gpasswd -d debian sudo >/dev/null 2>&1 || true; userdel --remove debian || true; fi']",
        "",
    ])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "user-data").write_text(cloud_config)
    (args.output / "meta-data").write_text("instance-id: blackveil-aether-linux-v1\nlocal-hostname: aether-linux\n")


if __name__ == "__main__":
    main()
