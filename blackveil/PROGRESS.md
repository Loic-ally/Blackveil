# BLACK VEIL build progress

Last source and local-stack review: **2026-10-29**. This inventory includes the
current working tree, including uncommitted worker/agent replay-protection changes.
Implementation, previous verification reports and checks rerun during this review
are distinguished below; running containers do not prove they contain every local change.

## Current milestone

AETHER has an implemented application baseline. The playable challenge currently
chains ordinary signup → Stage 01 historical export → Stage 02 administrator
recovery → `tenant_admin` in the player's own workspace.

**The application-side chain is complete: ordinary signup → Stage 01 → 02 → 03 →
04 → 05 reaches `system_admin` with no organizer action, and the Linux terminal
authorization gate opens.** Stages 03 (historical reconstruction), 04
(reporting-identity enrollment) and 05 (operator recovery, the former missing
`tenant_admin → system_admin` bridge) are implemented and live-verified by
`scripts/verify-chain.py` in challenge and patched modes against the full stack.
Remaining: the VM-side stages — Stage 06 (reach the operator shell through the
existing terminal), Stage 07 (in-guest agent discovery / capture a worker-signed
envelope) and Stage 08 integration (already-implemented agent mechanism, doc
sync, rebuild), plus the patched-mode VM regression. The VM fixtures, terminal
bridge and Stage 08 agent mechanism already exist.

## Milestones

| Phase | State | Actual implementation / remaining work |
|---|---|---|
| 1. Repository initialization | Complete | Separate project, Compose, Makefile, setup/reset scripts, architecture and stage specifications, CI workflow. |
| 2. Application MVP | In progress | Auth, tenant-scoped business workflows, team administration, reports and audit implemented. Tenant settings absent. |
| 3. First playable challenge | Partial: Stages 01–02 implemented | Signup-to-tenant-admin chain exists in challenge mode, with patched controls. Administrator-to-guest progression absent. |
| 4. Linux integration | Implemented infrastructure; progression incomplete | Debian QEMU guest, restricted operator, Rust agent, gated browser terminal and live archive reporting implemented. Guest access still needs an earlier challenge stage. |
| 5. Advanced investigation | Partial | Stage 08 has a specification, native agent mechanism and organizer verifier. Intermediate worker/guest investigation stages and player-accessible prerequisites remain. |
| 6. Final proof | Not implemented | No final evidence-correlation flow or isolated final validator found. |
| 7. Full challenge validation | Partial | Component/integration scripts and CI exist; no complete player walkthrough, destructive reset/replay validation or blind playtest. |
| 8. Security hardening | Partial | Network separation, runtime database roles, restricted guest and SSH host pinning exist. Complete boundary audit and remaining replay/lease/reset cases are unfinished. |
| 9. Difficulty tuning | Not implemented | No completed blind playtest or published scoring rubric found. |

## Implemented application

- **Authentication:** separate `aether-auth` service; registration creates an
  ordinary operator workspace; login/logout and database-backed sessions. The API
  resolves sessions through auth and fails closed on resolution errors. Auth has
  no lab network membership or VM key mount.
- **Workspace UI:** landing, registration/login, `/workspace`, `/team`, `/join`
  and `/lab`. Workspace views cover overview, equipment, maintenance incidents,
  reports, notifications and activity history.
- **Equipment and telemetry:** tenant-scoped equipment listing/creation,
  dashboard and per-asset telemetry history. A dedicated service generates
  synthetic telemetry every 15 seconds; this is a lab simulator, not a live
  industrial equipment integration. Equipment editing/deletion is not implemented.
- **Maintenance and activity:** incident creation/listing/status updates,
  internal notifications with read marking, and tenant-scoped audit events.
- **Team administration:** member listing, workspace role changes, invitations,
  revocation and acceptance. Invitation tokens are hashed, email-bound, expire
  after 48 hours and are consumed transactionally. Workspace administrators
  cannot grant system roles. Signup itself does not grant administrator access.
- **Reports:** asynchronous inventory and maintenance CSVs, Stage 01 historical
  exports (`legacy-history`), and VM-backed archives (`legacy-archive`) for
  enrolled tenants. Results/downloads remain scoped to the requesting tenant.
  Historical exports and VM archive reports are separate paths.
- **Durability:** PostgreSQL stores report jobs and results; NATS wakes workers
  and polling also finds work. Claims use `FOR UPDATE SKIP LOCKED`, a one-minute
  lease and attempt counter. Expired running jobs can be reclaimed. This is not
  a general exactly-once guarantee: overlapping expired-lease owners are not
  fenced, and completion/notification writes are separate operations.
- **Database:** ordered transactional migrations 001–007; separate API, auth,
  worker, telemetry and legacy runtime roles with scoped grants. A short-lived
  migrator owns schema changes; runtime services do not receive its credentials.

Main evidence: `api/internal/platform/{platform,auth_service,team,archive,legacy,
recovery,terminal,service_roles,migrate}.go`, `api/internal/platform/migrations/`,
and `web/app/`.

## Challenge stages

### Stage 01 — historical identity mismatch

Implemented in `legacy.go`, migration 004 and the reports UI, with specification
`docs/stages/stage-01-identity-parity.md` and `scripts/verify-legacy.py`.
An ordinary operator supplies their session tenant UUID and a historical numeric
installation reference. Challenge mode lets the worker/private legacy service
retrieve a bounded foreign historical archive; patched mode resolves the
canonical migration mapping. API docs, installation references, migration data,
CSV output and audit records provide investigation evidence.

### Stage 02 — administrator recovery

Implemented in `recovery.go`, migration 007 and the `/team` recovery form, with
specification `docs/stages/stage-02-administrator-recovery.md` and
`scripts/verify-recovery.py`.
The Stage 01 archive contains the random initialization-time handover receipt
for installation 4101; the recovery lookup stores its SHA-256 hash. Challenge
mode validates the session destination and receipt/installation pair but omits
binding the receipt's source tenant to that destination. Patched mode enforces
that binding. Promotion and redemption share a transaction and workspace lock;
only `tenant_admin` is granted, with per-account redemption tracking and audit.
The terminal remains denied after recovery.

### Stage 03 — historical state reconstruction

Implemented in `tenant.go`, migration 008 and two authenticated routes
(`GET /api/v2/tenant`, `GET /api/v2/tenant/migration`), with specification
`docs/stages/stage-03-historical-reconstruction.md`. A `tenant_admin` reads the
migration history endpoint, which in challenge mode resolves records by a
caller-supplied installation number without binding it to the session tenant
(the Stage 01 flaw at the settings layer), reconstructing the UUID↔number map,
the `svc:aether-reporting` principal, and the installation-4100 platform-operator
recovery receipt (its SHA-256 matches the stored hash, so it is a usable Stage 05
artifact). Patched mode resolves the caller's own canonical number only. This
stage grants no role or enrollment. **Verified:** `go build`/`go vet`/`go test`
(including `migrationLookupNumber`) and application of migrations 001–008 on
Postgres 16 with grant, cross-tenant-read and receipt-integrity checks. Live
HTTP verification (`scripts/verify-reconstruction.py`) is not yet written/run.

### Stage 04 — reporting-identity enrollment

Implemented in `reporting.go`, migration 009 and `POST /api/v2/tenant/reporting-identity`,
with specification `docs/stages/stage-04-reporting-identity.md`. A `tenant_admin`
presents the reporting-enrollment receipt reconstructed in Stage 03 (installation
4101) to enroll its own workspace as `svc:aether-reporting`. Challenge mode omits
binding the receipt's canonical installation to the caller's tenant (the Stage 02
unbound-source flaw at the enrollment hop); patched mode requires them to agree
and refuses. Self-enrolled workspaces get an archive number from a dedicated
≥500000 sequence (no collision with tenant numbers or seeded archive ids; empty
guest slot), so `legacy-archive` becomes queueable but resolves an empty archive
— reading a real foreign archive still needs Stage 08. Grants no role. **Verified:**
`go build`/`go vet`/`go test` (incl. `enrollmentBindingOK`), migrations 001–009 on
Postgres, and `scripts/verify-chain.py` live against the full stack (challenge and
patched PASS).

### Stage 05 — operator recovery (tenant_admin → system_admin bridge)

Implemented in `operator.go`, migration 010 and `POST /api/v2/lab/operator-recovery`,
with specification `docs/stages/stage-05-operator-recovery.md`. A `tenant_admin`
presents the platform-operator receipt reconstructed in Stage 03 (installation
4100) and must already hold the Stage 04 reporting identity; challenge mode omits
binding the receipt's canonical tenant to the destination workspace (the Stage 02
flaw lifted one authority level) and elevates to `system_admin`; patched mode
requires installation, principal and destination UUID to agree and refuses.
Single-use per account, `tenant_admin`-only promotion, full provenance audit, no
credential issued. This is the previously missing bridge: a player now reaches
`system_admin` from ordinary signup with no organizer action, and the terminal
authorization gate (`terminal.go`, unchanged, still `system_admin`-only) opens.
**Verified:** `go build`/`go vet`/`go test` (incl. `sourceBindingOK`), migrations
001–010 on Postgres, and `scripts/verify-chain.py` live against the full stack —
signup → 01 → 02 → 03 → 04 → 05 → system_admin, challenge and patched PASS,
including the Stage 04 prerequisite and single-use/operator-denied/audit checks.

### Stage 06 — restricted Linux access (lab foothold)

No new authorization code: `terminal.go` already gates on `system_admin` +
Origin and bridges a WebSocket to the non-root `operator` SSH shell. Stage 05 is
now the player-reachable source of `system_admin`, so the gap closed without
relaxing the gate. Specification `docs/stages/stage-06-lab-foothold.md`.
**Verified:** `scripts/verify-chain.py` opens the terminal WebSocket from the
player's own session after Stage 05 (no SQL grant), rejects a foreign Origin
(403), completes the 101 handshake and reaches the non-root `operator` shell —
live, as part of the full signup → 01 → 02 → 03 → 04 → 05 → 06 chain. On this
Apple Silicon host the guest boots as aarch64 under the VM container's QEMU.

### Stage 08 — native agent identity binding

The mechanism is implemented in `vm/agent/src/main.rs`, with specification
`docs/stages/stage-08-agent-identity-binding.md` and organizer verification in
`vm/verify-agent.py` / `scripts/vm-verify.py`.
Challenge mode signs job/principal/UUID but trusts an unsigned numeric archive
selector. Patched mode signs and validates the numeric identity against the
UUID mapping. This yields bounded archive access, not guest root or host access.
The worker derives its service identity from the database and checks the agent's
response identity before delivering CSV and recording provenance.

**Current local anti-replay implementation:** the worker adds `issued_at`;
patched-mode HMAC includes it. The patched Rust agent accepts timestamps within
120 seconds and rejects repeated signatures, normalizing hexadecimal case.
The cache is process-local and disappears on restart. Challenge mode retains
its unsigned-field behavior and does not enforce replay protection. Go protocol
tests and the Python verifier have been updated; the updated VM behavior was
not rebuilt or rerun during this review. Persistent replay protection remains
unfinished. The Stage 08 specification and agent README do not yet describe
this timestamp extension.

No Stage 03–07 specifications or implemented progression connecting Stage 02 to
Stage 08 were found. The organizer verifier signs fixtures with organizer-held
credentials; it does not establish that a player can obtain the required valid
envelope through the intended investigation path.

## Infrastructure and isolation

- HTTPS Nginx gateway is the only host-published service (TCP 443). Web, API,
  auth, worker, telemetry, legacy, PostgreSQL, Redis and NATS run separately.
  App, data and lab networks are Docker-internal; gateway is outside data/lab.
- Debian 13 generic-cloud guest under QEMU/TCG, pinned SHA-512 image manifest,
  cloud-init provisioning, named-volume disks/keys, no privileged container or
  Docker socket mount. Guest forwarding exposes SSH/agent only inside the lab.
- VM startup waits for agent readiness, authenticated cloud-init completion and
  the final ED25519 guest host key. The API pins that key for SSH.
- `/api/lab/terminal` requires `system_admin` and the configured Origin. It
  bridges WebSocket to a non-root, non-sudo `operator` SSH shell. The operator
  cannot read the worker signing key. `make vm-shell` is organizer access.
- VM services are optional Compose profiles: ordinary `make up` does not start
  them. `make vm-up` starts the challenge guest; verification uses a separate
  patched guest and volume.
- `make reset` removes application and VM volumes after explicit confirmation.
  `make vm-reset` removes both guest states/keys and recreates the API while
  retaining application data. Scripts exist; full reset correctness is not
  established by CI teardown alone.
- No `aether.blackveil.test` entry was found in `/etc/hosts` during this review.
  Setup prints the mapping to add; browser hostname readiness remains local
  setup work.

## Verification status

### Rerun during the 2026-10-29 review

- `go test ./...`: passed on the current Go working tree.
- `go vet ./...`: passed.
- `docker compose config --quiet`: passed.
- `scripts/check-network.sh`: passed; only gateway is host-published and VM
  ports remain private.
- `docker compose ps`: application services and both VM fixtures were running;
  services with health checks reported healthy. Images were not rebuilt, so
  this does not verify deployment of the local anti-replay changes.

### Previously recorded results — not rerun during this review

The previous progress log reported successful production web build, dependency
checks, application smoke tests, team administration, Stages 01–02 in both
identity modes, database grants, live archive delivery, worker interruption
recovery, persistent application restart with three competing workers, VM
protocol/terminal checks and an interactive VM reset. These are retained as
historical reports, not fresh verification of the entire current working tree.

### Automated coverage present in the repository

`.github/workflows/blackveil.yml` configures Go tests, web build, service startup,
smoke/team/legacy/recovery/database-role/network checks, lifecycle verification
with `--restart-app`, worker archive checks and VM/terminal verification, followed
by volume teardown. Workflow presence is not evidence of a successful CI run.

`scripts/verify-lifecycle.py` queues 24 reports across two temporary tenants,
uses three workers, checks claims/results/notifications/isolation, cleans its
fixtures and restores the worker count. Its restart variant exercises graceful
application/database/cache/bus restart while retaining volumes and guest state.
It does not cover destructive reset or overlapping expired-lease owners.

## Remaining work

1. Specify and implement the player progression from `tenant_admin` to the
   authorized Linux foothold, including the intermediate investigation clues
   and Stage 08 prerequisites.
2. Add tenant settings to complete the planned application scope.
3. Rebuild and verify the local timestamp/anti-replay changes against both VM
   modes; synchronize protocol documentation and address replay across agent
   restarts if required by the final challenge model.
4. Fence stale worker claims and define/test report completion and notification
   behavior under overlapping leases and failures between writes.
5. Automate destructive reset/reprovisioning and guest restart/boundary checks;
   current CI uses the TCG path and has no dedicated KVM/ARM64 matrix.
6. Implement the final evidence correlation and isolated validator.
7. Run the complete organizer walkthrough, final isolation/material-exposure
   audit and blind playtests; then tune difficulty and publish the rubric.
