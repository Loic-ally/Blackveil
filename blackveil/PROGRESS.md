# BLACK VEIL build progress

Last source and local-stack review: **2026-10-29**. This inventory reflects the
committed tree; the worker/agent replay-protection changes are now committed and
verified. Implementation, previous verification reports and checks rerun during this review
are distinguished below; running containers do not prove they contain every local change.

## Current milestone

AETHER has an implemented application baseline. The playable challenge currently
chains ordinary signup → Stage 01 historical export → Stage 02 administrator
recovery → `tenant_admin` in the player's own workspace.

**BLACK VEIL is playable Stage 01 through Stage 08 with no organizer action.**
The full chain — ordinary signup → Stage 01 historical export → 02 administrator
recovery → 03 historical reconstruction → 04 reporting-identity enrollment → 05
operator recovery (`system_admin`) → 06 restricted Linux operator shell → 07
agent discovery / retained capture → 08 agent identity confusion — is implemented
and live-verified end-to-end by `scripts/verify-chain.py` against the full
running stack, using only player interfaces (no DB edits, no injected
credentials, no organizer role grants). Patched mode closes the Stage 03/04/05
disclosures and the Stage 08 substitution. Stages 03, 04, 05 and the Stage 07
capture are new; Stage 06 reuses the existing terminal; the Stage 08 agent
mechanism already existed and is now player-reachable.

Remaining (separate in-flight workstream, not this chain): the worker/agent
anti-replay timestamp work in the working tree (`main.rs`, `archive.go`,
`verify-agent.py`), its protocol-doc sync, and the destructive reset / lease
fencing / boundary items (Requirement 7).

## Milestones

| Phase | State | Actual implementation / remaining work |
|---|---|---|
| 1. Repository initialization | Complete | Separate project, Compose, Makefile, setup/reset scripts, architecture and stage specifications, CI workflow. |
| 2. Application MVP | In progress | Auth, tenant-scoped business workflows, team administration, reports and audit implemented. Tenant settings absent. |
| 3. First playable challenge | Stages 01–08 playable | Signup → tenant_admin → system_admin → Linux shell → agent identity confusion, challenge and patched, live-verified by `scripts/verify-chain.py`. |
| 4. Linux integration | Progression complete | Debian QEMU guest, restricted operator, Rust agent, gated terminal and archive reporting implemented; guest access now reached via Stages 05–06 with no organizer action. |
| 5. Advanced investigation | Player-reachable | Stage 08 agent mechanism is now reached through Stages 03–07 (reconstruction, enrollment, operator recovery, foothold, retained capture). Final evidence-correlation flow (Phase 6) still absent. |
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

### Stage 07 — native service investigation (agent discovery)

Implemented via `vm/render-cloud-init.py` (a retained, operator-readable capture
of one legitimate worker-signed North Works request under
`/var/lib/aether-migration/last-archive-request.json`), with specification
`docs/stages/stage-07-agent-discovery.md`. The capture is a single signed
message, not the signing key or tenant map (both remain `root:aether-agent`,
unreadable by `operator`). It is the valid envelope Stage 08 manipulates.
**Verified:** `scripts/verify-chain.py` reads it over the operator SSH, confirms
`GET /v1/build`, confirms the captured North Works envelope, and confirms the
operator cannot read the worker key. The patched sample's signing projection
matches the timestamp-extended agent in the working tree (the in-flight
anti-replay workstream).

### Stage 08 — native agent identity binding

The mechanism is implemented in `vm/agent/src/main.rs`, with specification
`docs/stages/stage-08-agent-identity-binding.md` and organizer verification in
`vm/verify-agent.py` / `scripts/vm-verify.py`.
Challenge mode signs job/principal/UUID but trusts an unsigned numeric archive
selector. Patched mode signs and validates the numeric identity against the
UUID mapping. This yields bounded archive access, not guest root or host access.
The worker derives its service identity from the database and checks the agent's
response identity before delivering CSV and recording provenance.

**Anti-replay implementation (committed and verified):** the worker adds
`issued_at`; patched-mode HMAC signs it with `legacy_tenant_no`. The patched Rust
agent accepts timestamps within 120 seconds and rejects repeated signatures
(case-normalized). Challenge mode retains its unsigned-field behavior and does
not enforce replay protection. **Verified:** `go test` (worker projection incl.
`issued_at`) and `vm/verify-agent.py` run against the rebuilt patched guest —
the patched agent rejects a substituted number, a replayed (case-flipped)
signature and an expired (`issued_at` 600s old) envelope. The `accept_once` cache
is process-local by design: the `operator` cannot restart the agent and a
per-connection panic does not restart the process, so persistent replay storage
is not required (documented in `vm/agent/README.md` and the Stage 08 spec).

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

`scripts/verify-chain.py` (`make chain-verify`) is the player-path verifier: it
drives signup → Stages 01–08 through the real HTTP, WebSocket terminal and guest
agent interfaces with no DB edits or injected privileges, and asserts the patched
Stage 03/04/05 disclosures and the patched-agent Stage 08 substitution are all
refused. It requires the full stack plus `make vm-up` (the VM fixtures); the
guest boots as aarch64 under TCG on Apple Silicon.

`scripts/verify-lifecycle.py` queues 24 reports across two temporary tenants,
uses three workers, checks claims/results/notifications/isolation, cleans its
fixtures and restores the worker count. Its restart variant exercises graceful
application/database/cache/bus restart while retaining volumes and guest state.
It does not cover destructive reset or overlapping expired-lease owners.

## Remaining work

Done since the previous review:
- Player progression `tenant_admin` → Linux foothold → Stage 08 (Stages 03–07),
  live-verified by `scripts/verify-chain.py`.
- Tenant settings (`GET /api/v2/tenant`) added with Stage 03.
- Anti-replay timestamp changes rebuilt, verified and documented (above).

Remaining:
1. Fence stale worker claims and make report completion/notification writes
   atomic under overlapping leases and failures between writes.
2. Automate destructive reset/reprovisioning and guest restart/boundary checks in
   CI; current CI uses the TCG path and has no dedicated KVM/ARM64 matrix.
3. Implement the final evidence correlation and isolated validator (Phase 6).
4. Final isolation/material-exposure audit and blind playtests; then tune
   difficulty and publish the rubric; publish the organizer walkthrough.
