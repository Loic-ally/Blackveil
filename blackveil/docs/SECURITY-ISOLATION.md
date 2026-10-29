# BLACK VEIL security isolation checklist

## Current container baseline

- [x] Only `aether-gateway` publishes a host port, TCP 443.
- [x] PostgreSQL, Redis, NATS, web, API, worker and telemetry have no published
  host ports.
- [x] `edge` is the only non-internal Docker network; only the gateway joins it.
- [x] `app` and `data` Docker networks are marked internal.
- [x] The gateway joins `edge` and `app`, never `data`.
- [x] The API joins `app` and `data`; the web joins only `app`.
- [x] Worker and telemetry join only `data`.
- [x] No Docker socket, host device or writable host filesystem is mounted.
- [x] No container uses `privileged: true`.
- [x] API, worker, telemetry and web run as unprivileged users; gateway and
  stateful official images retain only narrowly required runtime capabilities.
- [x] Reset removes only this Compose project's named data volumes after a
  deliberate confirmation.
- [x] Runtime service logs and integration checks are local to the lab.

## Not implemented or not yet verified

- [ ] Disposable challenge VM and its network boundary (Phase 4).
- [ ] Native `aether-agent` confinement and lifecycle tests (Phase 4).
- [ ] Organizer validator network and evidence submission protocol (Phase 6).
- [ ] Independent restart/reset test in CI (still listed as Phase 2 work).
- [ ] Image digest pinning and automated image vulnerability scanning.

The network assertions in the checked items are enforced by
`scripts/check-network.sh`. Do not expose a future VM management interface on the
player-facing network.
