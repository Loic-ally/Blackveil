# BLACK VEIL build progress

Last source and local-stack review: **2026-10-29**. Implementation and the
commands rerun during this review are distinguished below; the exact commands
and exit codes are in `organizer/full-chain-validation.md`.

## Current milestone

AETHER has an implemented application baseline and Stages 01–08 are playable.
Stages 09–15 are not implemented.

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
mechanism already existed and is now player-reachable. Stages 06–08 are verified
as commands typed into the player's own WebSocket terminal session.

Open items: `organizer/remaining-risks.md`.

### Advanced extension (Stages 09–15) — in progress

Design and Phase A complete: the pre-implementation audit
(`organizer/advanced-extension-assessment.md`) and the full 09–15 dependency
graph / architecture (`organizer/attack-graph-v3.md`), grounded in the source.
Built depth-first; each stage committed only when its tests run green, without
altering Stages 01–08.

- **Stage 09 — The Forgotten Binary (reverse engineering): implemented and
  live-verified.** New `aether-indexer` native service (`vm/indexer/`) with a
  custom `legacy-envelope/0` binary TLV protocol, provisioned into the guest by
  cloud-init (confined `aether-indexer` account, loopback-only `:9090`,
  root-owned transport key the operator cannot read, world-readable binary for
  RE). Challenge mode's legacy compat shim trusts a client-supplied origin
  marker and skips the HMAC; patched mode decommissions the legacy transport.
  Verified by 7 host `cargo test` vectors and live through the player's own
  WebSocket terminal as part of `make chain-verify` (Stages 01–09, exit 0).
  Spec: `docs/stages/stage-09.md`.
- **Stage 10 — Namespace Labyrinth (Linux internals): implemented and
  live-verified.** New confined `aether-provisioner` service (`vm/provisioner/`)
  under its own `aether-prov` account in a private mount namespace, on a per-boot
  abstract unix socket `@aether-prov.<boot8>`. Challenge mode gates the `describe`
  handshake on the world-readable boot epoch (reached by correlating the Stage 09
  descriptor, `/proc/net/unix` and `/proc/sys/kernel/random/boot_id`); patched
  mode requires a non-world-readable ticket, closing the shortcut. Verified by 5
  host `cargo test` vectors and live through the player terminal in
  `make chain-verify` (Stages 01–10, exit 0). Spec: `docs/stages/stage-10.md`.
- **Stage 11 — False Root (privilege boundaries): implemented and
  live-verified.** The provisioner's `provision` op renders templates from a
  confined store (`root:aether-prov`); challenge mode joins the caller's `arg`
  without sanitization, so `../provenance.blob` escapes the store as the deputy
  and extracts the Stage 12 provenance blob — yet the same traversal to
  `/etc/aether-agent/worker.key` is denied, proving the elevation is bounded to
  the `aether-prov` identity (not guest root). Patched mode rejects any traversal.
  Verified by host `cargo test` and live through the player terminal in
  `make chain-verify` (Stages 01–11, exit 0). Spec: `docs/stages/stage-11.md`.
- **Stage 12 — The Integrity Paradox (applied cryptography): implemented and
  live-verified.** The agent gained an additive `POST /v1/provenance` endpoint
  (Stage 08 archive path byte-for-byte unchanged). Challenge mode verifies the
  HMAC over the canonical TLV but reports the identity from the blob's
  unauthenticated JSON fields, so an edited-JSON blob with the original signature
  is accepted as a different identity; patched mode binds the identity to the
  signed TLV and rejects a mismatch. No primitive is broken. Verified by 4 host
  `cargo test` vectors and live through the player terminal in `make chain-verify`
  (Stages 01–12, exit 0). Spec: `docs/stages/stage-12.md`.
- **Stage 13 — The Broken Trust Chain (distributed systems): implemented and
  live-verified.** Additive agent `POST /v1/manifest` correlates three facts from
  three tiers — the worker `job_id` (Stage 07 capture), the forged agent-verified
  provenance token (Stage 12), and the API migration mapping (Stage 03). Challenge
  mode validates each fact and that they agree with the provenance's *asserted*
  identity, but never binds them to the signed TLV or the caller, so a North-signed
  token with a Harbor JSON identity + Harbor mapping yields a cross-tenant manifest
  (`deploy-4102`); patched mode resolves against the signed TLV and refuses.
  Verified by 4 host `cargo test` vectors and live through the player terminal in
  `make chain-verify` (Stages 01–13, exit 0). Spec: `docs/stages/stage-13.md`.
- **Stage 14 — Everything Was Logged (digital forensics): implemented and
  live-verified.** A deterministic incident evidence set (worker/agent/API, with a
  guest clock offset and a retry) is seeded under
  `/var/lib/aether-migration/incident/`; the additive agent `POST /v1/incident`
  scorer accepts only the correct `(offset, pivot_job, pivot_number)` and returns
  an incident attestation (the Stage 15 input). Verified by 2 host `cargo test`
  vectors and live through the player terminal in `make chain-verify` (Stages
  01–14, exit 0). Spec: `docs/stages/stage-14.md`.
- **Stage 15 — The Black Veil (final synthesis + isolated validator):
  implemented and live-verified.** A subtle public-site clue
  (`aether-migration-channel: veil/v0` in `web/app/layout.tsx`) is the proof's
  domain label. The isolated `aether-validator` service (dedicated internal
  network, no host port, key-holding, code mounted from `organizer/` so it never
  enters a player image) mints `BV{…}` only for a complete proof assembled from
  the incident attestation (14), the cross-tenant manifest/pivot (13) and the site
  clue (15). Verified by the validator's self-checks and live in
  `make chain-verify`: an incomplete proof is rejected with `missing`, the full
  proof mints the flag (Stages 01–15, exit 0). Specs:
  `docs/stages/stage-15.md`, `organizer/final-proof-design.md`.

**BLACK VEIL is now player-solvable Stages 01–15**, end-to-end through the real
HTTP API, the player WebSocket terminal and the guest services, with the final
proof gated behind the isolated organizer validator. `make chain-verify` exercises
the whole chain (challenge) plus the patched 03/04/05/08/09/10/11/12/13
regressions and exits nonzero if the guest is unavailable.

## Milestones

| Phase | State | Actual implementation / remaining work |
|---|---|---|
| 1. Repository initialization | Complete | Separate project, Compose, Makefile, setup/reset scripts, architecture and stage specifications, CI workflow. |
| 2. Application MVP | In progress | Auth, tenant-scoped business workflows, team administration, reports, audit and a read-only tenant settings view (`GET /api/v2/tenant`) implemented. Equipment editing/deletion absent. |
| 3. First playable challenge | Stages 01–08 playable | Signup → tenant_admin → system_admin → Linux shell → agent identity confusion, challenge and patched, live-verified by `scripts/verify-chain.py`. |
| 4. Linux integration | Progression complete | Debian QEMU guest, restricted operator, Rust agent, gated terminal and archive reporting implemented; guest access now reached via Stages 05–06 with no organizer action. |
| 5. Advanced investigation | Player-reachable | Stage 08 agent mechanism is now reached through Stages 03–07 (reconstruction, enrollment, operator recovery, foothold, retained capture). Final evidence-correlation flow (Phase 6) still absent. |
| 6. Final proof | Not implemented | No final evidence-correlation flow or isolated final validator found. |
| 7. Full challenge validation | Partial | Player-equivalent chain verifier (Stages 01–08), organizer walkthrough (`docs/WALKTHROUGH.md`) and disposable reset/restart verifier (`make reset-verify`) exist. No blind playtest; reset verification is not in CI. |
| 8. Security hardening | Partial | Network separation, runtime database roles, restricted guest, SSH host pinning, patched-mode anti-replay and lease fencing exist; audit in `organizer/security-isolation-audit.md`. Image digest pinning and vulnerability scanning absent. |
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
  lease and attempt counter. Expired running jobs can be reclaimed. The
  `attempt_count` is a lease fence: a reclaim advances it, so a stale owner's
  completion or failure write is rejected, and the result and its notification
  are written in one transaction (a report never completes without its
  notification). Verified by `scripts/verify-fencing.py`.
- **Database:** ordered transactional migrations 001–011 (011 reserves
  installation ids 4100–4199 so registered workspaces start at 4200 and never
  collide with a seeded installation number); separate API, auth,
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
stage grants no role or enrollment. **Previously reported:** `go test` (including
`migrationLookupNumber`) and live by the Stage 03 / patched-03 sections of
`scripts/verify-chain.py` (receipt hash-checked against the stored value; no
role or terminal access gained). There is no separate reconstruction script.

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
**Verified:** `scripts/verify-chain.py`, inside the player's WebSocket terminal,
confirms `GET /v1/build`, reads the captured North Works envelope, and confirms
`cat` of the worker key and tenant map fails with "Permission denied". The
patched sample's signing projection matches the committed timestamp-extended
agent.

### Stage 08 — native agent identity binding

The mechanism is implemented in `vm/agent/src/main.rs`, with specification
`docs/stages/stage-08-agent-identity-binding.md` and organizer verification in
`vm/verify-agent.py` / `scripts/vm-verify.py`.
Challenge mode signs job/principal/UUID but trusts an unsigned numeric archive
selector. Patched mode signs and validates the numeric identity against the
UUID mapping. This yields bounded archive access, not guest root or host access.
The worker derives its service identity from the database and checks the agent's
response identity before delivering CSV and recording provenance.

**Anti-replay implementation (source):** the worker adds
`issued_at`; patched-mode HMAC signs it with `legacy_tenant_no`. The patched Rust
agent accepts timestamps within 120 seconds and rejects repeated signatures
(case-normalized). Challenge mode retains its unsigned-field behavior and does
not enforce replay protection. **Previously reported:** `go test` (worker projection incl.
`issued_at`) and `vm/verify-agent.py` run against the rebuilt patched guest —
the patched agent rejects a substituted number, a replayed (case-flipped)
signature and an expired (`issued_at` 600s old) envelope. The `accept_once` cache
is process-local by design: the `operator` cannot restart the agent and a
per-connection panic does not restart the process, so persistent replay storage
is not required (documented in `vm/agent/README.md` and the Stage 08 spec).

`vm/verify-agent.py` signs fixtures with the organizer-held key; it checks the
agent mechanism only. The player path to a valid envelope (Stages 03–07) is
established separately by `scripts/verify-chain.py`, which submits the retained
capture and the number-substituted copy from the player's terminal.

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
  retaining application data. `make reset-verify` exercises both, plus guest and
  agent restarts, in a disposable Compose project and reruns the full chain after
  each (see `organizer/full-chain-validation.md`).
- No `aether.blackveil.test` entry was found in `/etc/hosts` during this review.
  Setup prints the mapping to add; browser hostname readiness remains local
  setup work.

## Verification status

Current commands, exit codes and remaining gaps are recorded in
[organizer/full-chain-validation.md](organizer/full-chain-validation.md).
Earlier verification claims in this file describe historical reports; they are
not evidence that this working tree or its deployed images passed a fresh run.
Stages 01–08 are implemented. Stages 09–15 remain unimplemented.

The full-chain target requires already-running challenge and patched guests.
Stages 06–08 use one authenticated player WebSocket session, including protocol
discovery and archive substitution. Organizer SQL/SSH is limited to setup,
cleanup and independent assertions. The disposable reset verifier covers fresh
deployment, guest reboot, actual agent-only restart, VM reset and full reset,
with a full chain after each. A test-only sudo rule is injected into the copied
cloud-init renderer for the agent-only restart; the boot ID must stay unchanged.

Remaining work includes CI reset coverage, a blind playtest, image digest
pinning/scanning, and final evidence correlation. No CI success is claimed.
