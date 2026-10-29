# BLACK VEIL network boundaries

## Planned topology

```mermaid
flowchart LR
    P[Player browser] -->|HTTPS :443 only| G[aether-gateway]
    G --> W[aether-web]
    G --> A[aether-api]
    G -->|credential operations| AU[aether-auth]
    A -->|authenticated WebSocket / private SSH| VM[QEMU Debian VM]
    A --> AU[aether-auth]
    A --> L[aether-legacy]
    A --> T[aether-telemetry]
    A --> PG[(aether-db)]
    A --> R[(aether-cache)]
    A --> N[(aether-bus / NATS)]
    N --> WK[aether-worker]
    WK --> L
    WK --> VM[QEMU Debian VM / Rust aether-agent]
    V[blackveil-validator] -. signed evidence only .-> VM
```

## Firewall policy

| Source | Destination | Allowed traffic |
|---|---|---|
| Player network | Gateway | TCP 443 |
| Gateway | Web | TCP 3000 |
| Gateway | API | TCP 8080 |
| API | Auth | TCP 8081 |
| API | Legacy | TCP 8082 |
| API | Telemetry | TCP 8083 |
| API / worker | PostgreSQL | TCP 5432 |
| API / worker | Redis | TCP 6379 |
| API / worker | NATS | TCP 4222 |
| API / worker | Linux VM agent | TCP 18080 on private `lab` network only |
| API | Linux VM operator SSH | TCP 2222 on private `lab` network only; initiated after a `system_admin` session check |
| Player network | Any internal service | Denied |
| Challenge workloads | Validator | Denied; evidence is submitted through a constrained one-way interface |

Only the gateway is published on the host. Database, cache, bus, API, worker,
telemetry, auth, legacy and VM services have no host port mappings. Compose
internal networks are checked by `scripts/check-network.sh`. The internal `lab`
network joins only the API, worker and QEMU VM service; the gateway and web
frontend are excluded. QEMU user-mode NAT lets the guest reach only the API and
worker peers on the internal `lab` network; that network has no public egress.
Only guest SSH and agent ports are forwarded to the VM container, and neither
port is host-published. The API mounts the named guest-state volume read-only;
filesystem permissions expose only the restricted operator key to its
unprivileged service account. The guest SSH key is never sent to the browser.

## Deployment limitation

The local name `aether.blackveil.test` resolves to loopback on the player's host.
The setup script will document the required hosts entry and generate a local TLS
certificate. Production deployment must replace the local certificate and keep
the same single-entry-point policy.
