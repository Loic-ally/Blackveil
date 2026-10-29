# BLACK VEIL network boundaries

## Planned topology

```mermaid
flowchart LR
    P[Player browser] -->|HTTPS :443 only| G[aether-gateway]
    G --> W[aether-web]
    G --> A[aether-api]
    A --> AU[aether-auth]
    A --> L[aether-legacy]
    A --> T[aether-telemetry]
    A --> PG[(aether-db)]
    A --> R[(aether-cache)]
    A --> N[(aether-bus / NATS)]
    N --> WK[aether-worker]
    WK --> L
    WK --> VM[Disposable Linux VM / aether-agent]
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
| Worker | Linux VM agent | Explicit challenge-only port, added in Phase 4 |
| Player network | Any internal service | Denied |
| Challenge workloads | Validator | Denied; evidence is submitted through a constrained one-way interface |

Only the gateway is published on the host. Database, cache, bus, API, worker,
telemetry, auth and legacy services have no host port mappings. Compose internal
networks will be checked by `scripts/check-network.sh` when service definitions
are added.

## Deployment limitation

The local name `aether.blackveil.test` resolves to loopback on the player's host.
The setup script will document the required hosts entry and generate a local TLS
certificate. Production deployment must replace the local certificate and keep
the same single-entry-point policy.
