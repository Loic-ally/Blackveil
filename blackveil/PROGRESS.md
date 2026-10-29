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
| 4. Linux integration | In progress | Disposable Debian 13 QEMU guest, restricted `operator` login, Rust agent and `system_admin`-gated browser terminal are implemented; Live archive reports now use the worker and VM agent; the earlier milestone granting access is pending. |
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
- The Linux guest uses Debian's generic-cloud image checked against the pinned
  SHA-512 manifest in `vm/images/SHA512SUMS`; disks and SSH keys live in named
  Docker volumes. QEMU user networking reaches only API/worker peers on the
  internal lab network, with explicit SSH/agent forwards and no public egress.

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
- The Linux VM stage implementation is in `vm/`: QEMU/TCG lifecycle, cloud-init
  provisioning, a key-only non-sudo operator, a native Rust agent, and
  challenge/patched identity-envelope handling. `make vm-verify` exercises both.
- Linux VM verification passed on the ARM64 development host: both guests booted
  from clean volumes; SSH confirmed the operator is non-root, non-sudo and cannot
  read the worker key; the API can read the operator key through a read-only
  mount; the challenge accepted a changed unsigned legacy number; the patched
  agent rejected it. API and worker both reached the agent health endpoint over
  the private lab network.
- After adding the VM, `scripts/check-network.sh` still passed with only gateway
  TCP 443 published; `scripts/smoke.py` passed ordinary signup, tenant isolation,
  telemetry, incidents, audit, notifications and asynchronous reports; it also
  confirmed an ordinary operator receives HTTP 403 from the Linux terminal.
- `scripts/vm-verify.py` passed the gated browser terminal flow through HTTPS and
  WebSocket: the organizer test grants the stage role, a foreign Origin is
  rejected, the API pins the guest's ED25519 host key, and the session receives
  a non-root `operator` shell. The temporary test tenant is deleted afterward.
- `scripts/vm-reset.sh` passed interactively: it deleted both disposable guest
  state volumes and restarted the API without removing application data. A
  cleared-state challenge guest then booted from the pinned Debian image and
  became healthy with a newly generated operator key and guest host key.

## Remaining Phase 2 work

- Split authentication into the required `aether-auth` process with a defined
  service-to-service contract.
- Add the legacy compatibility service and independent service-identity model.
- Add role enforcement, invitations/user management, and tenant-level admin
  functions.
- Exercise clean restart, reset, and concurrent worker behavior in CI.
- Make the ordinary UI accessible through the local hostname after the hosts
  entry is installed.

## Remaining Linux integration work

- Add replay protection and durable recovery for interrupted archive jobs.
- Implement the earlier identity milestones that unlock historical tenants and the terminal.
- Add guest restart/reset and guest-host boundary checks to CI on Linux/KVM and
  the ARM64 TCG development path.

## Archive reporting integration

- Added ordered, transactional migrations and a separate worker service-identity map.
- Enrolled tenants can queue historical archive CSVs through the app; the worker
  signs database-derived identities, calls the private VM agent, checks the
  returned identity and records provenance in tenant-scoped audit events.
- Live HTTPS/worker/VM verification passed, including enrollment denial, foreign
  report denial, audit provenance, CSV content and completion notification.
- Go protocol tests passed for both signature modes, response tenant mismatch
  rejection and redirect rejection. The production frontend build passed.
