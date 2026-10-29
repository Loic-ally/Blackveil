# BLACK VEIL security isolation checklist

## Current container baseline

- [x] Only `aether-gateway` publishes a host port, TCP 443.
- [x] PostgreSQL, Redis, NATS, web, API, worker and telemetry have no published
  host ports.
- [x] `edge` is the only non-internal Docker network; only the gateway joins it.
- [x] `app`, `data` and `lab` Docker networks are marked internal.
- [x] The gateway joins `edge` and `app`, never `data`.
- [x] The API joins `app` and `data`; the web joins only `app`.
- [x] Worker joins `data` and `lab`; telemetry joins only `data`.
- [x] No Docker socket, host device or writable host filesystem is mounted.
- [x] No container uses `privileged: true`.
- [x] API, worker, telemetry and web run as unprivileged users; gateway and
  stateful official images retain only narrowly required runtime capabilities.
- [x] API, auth, worker, telemetry and legacy use separate non-superuser
  database roles; schema migrations run through a short-lived owner account.
- [x] Reset removes only this Compose project's named data volumes after a
  deliberate confirmation.
- [x] Runtime service logs and integration checks are local to the lab.

## Not implemented or not yet verified

- [x] Disposable Debian guest under QEMU TCG; no devices, host mounts, Docker
  socket, privileged mode or host-published VM ports.
- [x] Native Rust `aether-agent` runs under a separate guest service account;
  operator login is key-only and has no sudo grant.
- [x] VM disk is isolated in Docker-managed named volumes and can be reset
  without removing application database state.
- [x] Browser terminal requires an authenticated `system_admin` session, uses
  the API's private SSH bridge, and does not publish guest SSH or agent ports.
- [x] API mounts VM state as a read-only named volume; only the operator key is
  group-readable to the API process, and the guest cannot read that volume.
- [x] Worker-to-agent archive delivery uses database-derived identities and bounded responses.
- [x] Expired lease recovery for reports interrupted after a worker claim.
- [ ] Replay protection for worker-to-agent envelopes (Phase 4/5).
- [ ] Organizer validator network and evidence submission protocol (Phase 6).
- [ ] Independent restart/reset test in CI (still listed as Phase 2 work).
- [ ] Image digest pinning and automated image vulnerability scanning.

The network assertions in the checked items are enforced by
`scripts/check-network.sh`. Do not expose a future VM management interface on the
player-facing network.
