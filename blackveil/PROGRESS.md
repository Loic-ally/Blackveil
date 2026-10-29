# BLACK VEIL build progress

## Current milestone

Phase 1 is complete. Phase 2 has a working local application baseline and remains
in progress until the remaining identity/auth split, admin workflow, and full
service contracts are implemented.

## Milestones

| Phase | State | Evidence / next action |
|---|---|---|
| 1. Repository initialization | Complete | Project layout, trust-boundary definition, first stage spec, Makefile, Compose, CI, reset/setup scripts and network policy are present. |
| 2. Application MVP | In progress | Web/API/PostgreSQL/Redis/NATS/worker/telemetry run. Ordinary workflows pass the black-box smoke test. Auth is still in the API process; add the separate auth service, service identities, admin flows and remaining integration coverage. |
| 3. First playable challenge | Not started | Add the first documented challenge flaw only after baseline behavior is working. |
| 4. Linux integration | Not started | Add disposable VM lifecycle and a restricted application-to-VM progression. |
| 5. Advanced investigation | Not started | Implement worker/agent trust analysis and native service stages. |
| 6. Final proof | Not started | Add evidence correlation and isolated validator. |
| 7. Full challenge validation | Not started | Execute organizer walkthrough and reset tests. |
| 8. Security hardening | Not started | Verify isolation, reset behavior and non-exposure of organizer material. |
| 9. Difficulty tuning | Not started | Blind playtest, adjust clues and publish rubric. |

## Decisions

- Keep the existing MetSec product intact; BLACK VEIL is a separate project in
  `blackveil/`.
- No challenge service will mount the Docker socket or host filesystem.
- The player entry point is the HTTPS gateway only. Application services will
  be private to explicitly named Compose networks.
- The challenge root cause is inconsistent identity interpretation across the
  UUID tenant model, retained numeric compatibility model, worker principal map
  and native agent trust envelope. Each stage must be specified before coding.

## Verification record

- `docker compose config --quiet` passed.
- Go API: `go test ./...`, `go vet ./...` and `go mod verify` passed.
- Next.js 16.4.3 production build passed with `next build --webpack`.
- `npm audit --omit=dev` reported zero vulnerabilities after updating Next.js.
- Docker built and started the web, gateway, API, PostgreSQL 18, Redis 8, NATS,
  worker and telemetry services.
- `scripts/smoke.py` passed registration, logout, tenant isolation, equipment,
  telemetry history, incident creation/status transitions, audit, notifications,
  asynchronous CSV generation and report tenant isolation.
- `scripts/check-network.sh` passed: only TCP 443 is published; API/web/worker/
  telemetry/database/cache/bus have no host ports; the gateway is absent from the
  data network; app and data networks are Docker-internal.
- The local host entry could not be written because `/etc/hosts` is protected in
  this environment. `make setup` prints the exact `127.0.0.1 aether.blackveil.test`
  line; add it manually before using the requested hostname in a browser.

## Remaining Phase 2 work

- Split authentication into the required `aether-auth` process with a defined
  service-to-service contract.
- Add the legacy compatibility service and independent service-identity model.
- Add role enforcement, invitations/user management, and tenant-level admin
  functions.
- Exercise clean restart, reset, and concurrent worker behavior in CI.
- Make the ordinary UI accessible through the local hostname after the hosts
  entry is installed.
