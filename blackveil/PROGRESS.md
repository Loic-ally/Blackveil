# BLACK VEIL build progress

## Current milestone

Phase 1 is complete. Phase 2 has a working application baseline and tenant
administration. Phase 3 now has its first end-to-end identity-confusion stage;
the application-to-guest progression and later guest stages remain incomplete.

## Milestones

| Phase | State | Evidence / next action |
|---|---|---|
| 1. Repository initialization | Complete | Project layout, trust-boundary definition, first stage spec, Makefile, Compose, CI, reset/setup scripts and network policy are present. |
| 2. Application MVP | In progress | Registration, UUID tenant APIs, team invitations, telemetry, incidents, notifications, audit, and asynchronous reports work. Dedicated legacy service and ordinary workflow regressions pass; database service roles and clean-restart CI coverage remain. |
| 3. First playable challenge | In progress | Stage 01 reproduces a bounded cross-tenant historical export in challenge mode and canonical tenant resolution in patched mode. The route is tested through HTTPS; the path to a guest foothold remains unimplemented. |
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

- Add dedicated database roles so the auth/API process boundary also restricts database authority.
- Add tenant settings and implement the intended challenge path to administrator membership.
- Exercise clean restart, reset, and concurrent worker behavior in CI.
- Make the ordinary UI accessible through the local hostname after the hosts
  entry is installed.

## Remaining Linux integration work

- Add replay protection for worker-to-agent requests.
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

## Authentication service split

- `aether-auth` owns public credential routes and private session resolution.
  The API resolves every session through that service and fails closed on errors.
- Auth has no lab network membership or VM key mount, and no host-published port.
- Unit checks cover revoked/malformed identities, unknown roles and service
  failure. Live signup/login/logout and archive-delivery regressions are exercised.

## VM startup and host identity correction

- VM readiness now waits for the agent, authenticated cloud-init completion and
  collection of the final ED25519 host key. Bootstrap retries use backoff.
- The SSH bridge explicitly negotiates the pinned host-key type; otherwise Go
  could select another valid guest host key and fail its ED25519 pin check.
- A fresh patched guest reached readiness and passed the agent protocol checks.
  The browser terminal regression passed through the separate auth service after
  the negotiation correction (`scripts/vm-verify.py --terminal-only`).
- The VM verifier now stops its patched fixture even if deployment fails.

## Team administration

- `/team` supports tenant-scoped member lists, role changes, invitation creation
  and revocation. `/join` accepts invitations through the auth service. Tokens
  are stored only as hashes, bound to email, expire after 48 hours and are
  consumed transactionally. Workspace administrators cannot grant system roles.
- Live regression passed for operator/foreign-tenant denial, email binding,
  single use, revoked/expired invitations, role promotion/demotion and immediate
  session enforcement. Production frontend and Go checks passed.
- Organizer tests grant a temporary administrator prerequisite and clean up their
  tenants. Signup still grants ordinary operator access; no admin bypass was added.

## Legacy identity stage

- Added a private legacy-history service and historical export workflow over the
  existing NATS worker. The public installation reference, UUID API docs,
  migration records, worker map and CSV output provide independent evidence
  about the old and new identity models.
- The worker and legacy service use a dedicated credential, separate from the
  Linux agent key. The service is attached only to the private data network and
  publishes no host port.
- `scripts/verify-legacy.py` passed in challenge and patched modes: the ordinary
  operator retrieves the seeded cross-tenant archive only in challenge mode;
  patched mode resolves the canonical migration mapping, while enrolled archive
  exports continue to work. UUID boundary and audit evidence checks passed.
- The normal application smoke test, production web build, Go tests and network
  isolation script passed after integration.
- Remaining: this stage demonstrates bounded data access but does not grant the
  intended Linux foothold. The admin membership and terminal progression need a
  fully specified and verified stage.

## Durable report recovery

- Report claims now carry a one-minute lease and an attempt counter. A worker
  that exits after claiming work leaves a report that can be reclaimed after
  the lease expires; old unleased `running` rows are returned to the queue by
  migration 005.
- `scripts/verify-worker.py` passed a live interruption check: it stopped the
  worker after queueing a report, marked the claim expired, restarted the worker
  and confirmed the report completed on its second attempt. Archive delivery,
  tenant isolation, audit provenance and notifications passed in the same run.
- Replay protection for guest agent envelopes remains separate work.
