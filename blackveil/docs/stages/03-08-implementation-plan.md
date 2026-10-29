# Stages 03–08 implementation plan

Source-of-truth review date: **2026-10-29**. This plan is derived from the
actual working tree (`api/internal/platform/*.go`, `migrations/001–007`,
`vm/agent/src/main.rs`), not from aspiration. It closes the gap PROGRESS.md
records: the player path currently stops at `tenant_admin` and nothing bridges
to `system_admin`, the Linux terminal, or the already-implemented Stage 08.

## Invariant (unchanged from `docs/architecture/trust-boundary.md`)

Every hop must bind `(user, role, tenant UUID, legacy integer, service
principal, job ID)` to one authorization context. Challenge mode violates
exactly one binding per stage; patched mode derives every representation from
the canonical server-side tenant record and rejects disagreement. This is the
same flaw class already shipped in Stage 01 (unbound `legacy_tenant_no` in the
historical report), Stage 02 (unbound receipt source-tenant in recovery) and
Stage 08 (unbound `legacy_tenant_no` in the agent envelope). Stages 03–07 reuse
it; they do not introduce a new vulnerability family.

## What each privilege level can do today (measured, not assumed)

| Identity | Can do | Cannot do |
|---|---|---|
| `operator` (fresh signup) | own-workspace reads/writes; `legacy-history` report (Stage 01); administrator recovery (Stage 02) | team admin; `legacy-archive` (not enrolled); terminal |
| `tenant_admin` (after Stage 02) | team admin, invitations, role changes (≤ tenant_admin) | grant `system_admin`; enroll in archive migration; terminal |
| enrolled tenant | queue `legacy-archive` → worker → agent | — |
| `system_admin` | `/api/lab/terminal` → operator SSH shell in disposable VM | read worker signing key; host access |

Two independent gates therefore stand between `tenant_admin` and Stage 08:
1. **`system_admin`** — required by `terminal.go:13`; no code path grants it.
2. **archive enrollment** — required by `createReport` (`platform.go:578`) and
   `archiveReport` (`archive.go:29`); only seeded for North Works/Harbor.

Stages 03–05 open both gates through investigation + the unbound-identity flaw,
without editing the DB, injecting credentials, or equating the two roles.

## Dependency graph

```
signup(operator)
      │  Stage 01  BV-01  POST /api/v2/reports/historical   (unbound legacy_tenant_no)
      ▼
reads foreign historical archive 4101  ──► handover receipt
      │  Stage 02  BV-02  POST /api/v2/team/recover          (unbound receipt source tenant)
      ▼
tenant_admin (own workspace)
      │  Stage 03  BV-03  GET  /api/v2/tenant + /api/v2/tenant/migration   (unbound migration number)
      ▼
reconstructs UUID↔number map, principal svc:aether-reporting,
discovers platform-operator installation 4100 recovery artifact
      │  Stage 04  BV-04  POST /api/v2/tenant/reporting-identity           (unbound archive number)
      ▼
own tenant enrolled as svc:aether-reporting  ──►  legacy-archive queueable  ──► (worker→agent path open)
      │  Stage 05  BV-05  POST /api/v2/lab/operator-recovery               (unbound destination UUID)
      ▼                     requires: platform-operator receipt (03) + reporting principal (04)
system_admin
      │  Stage 06  (no new code — Stage 05 legitimately satisfies terminal.go gate)
      ▼  GET /api/lab/terminal  →  operator SSH shell in disposable VM
      │  Stage 07  in-VM investigation: aether-agent build/protocol, observe worker-signed envelope
      ▼
holds a valid worker-signed archive envelope
      │  Stage 08  BV-08  POST agent /v1/legacy/archive with substituted legacy_tenant_no  (ALREADY IMPLEMENTED)
      ▼
cross-service identity confusion proven — bounded foreign archive, no root, no host
```

Each arrow is a distinct authorization decision, not a guessed endpoint. 03→04→05
each require evidence produced by the previous stage; 05 requires artifacts from
*both* 03 and 04 (the "service boundary" reasoning requirement).

## Stage designs

### Stage 03 — Historical State Reconstruction  `BV-03-HISTORICAL-RECONSTRUCTION`
- **New surface:** `GET /api/v2/tenant` (tenant settings — fills the PROGRESS
  "Tenant settings absent" gap): returns the caller's tenant name, canonical
  `legacy_tenant_no`, and archive-enrollment status. `GET /api/v2/tenant/migration?legacy_tenant_no=N`
  (tenant_admin/system_admin): returns migration/audit history for `N`.
- **Flaw (challenge):** the migration endpoint resolves records by the
  caller-supplied `N` without binding it to the session tenant — the Stage 01
  flaw re-expressed at the settings layer. Lets the player read foreign tenants'
  migration records (4101/4102) and the platform-operator artifact (4100).
- **Patched:** ignore `N`; resolve the caller's own canonical number from `tenants`.
- **Yields:** UUID↔number map, `svc:aether-reporting` principal, and the
  existence of a platform-operator recovery receipt for installation 4100
  (lead for Stage 05). No privilege change.
- **Data:** migration 008 adds a `legacy_history` row for installation 4100 and
  a `platform_operator_recovery_receipts` table (mirrors `007`).

### Stage 04 — Asynchronous Trust Investigation  `BV-04-REPORTING-IDENTITY`
- **New surface:** `POST /api/v2/tenant/reporting-identity` (tenant_admin):
  enroll the caller's own workspace as `svc:aether-reporting` by presenting the
  migration proof found in Stage 03.
- **Flaw (challenge):** binds the principal + a caller-supplied `archive_tenant_no`
  without binding that number to the caller's canonical tenant number — same
  unbound-number class as Stage 01/08. Inserts a `worker_service_identities` row
  for the caller's tenant.
- **Patched:** derive `archive_tenant_no` from the canonical tenant record;
  reject caller-supplied numbers.
- **Yields:** `legacy-archive` reports become queueable (worker→agent path
  opens, Stage 08 worker prerequisite) and the player now legitimately *holds*
  the `svc:aether-reporting` principal (proof for Stage 05). A queued job carries
  the player's UUID while resolving a number they chose — the reproducible
  inconsistency.
- **Note on `archive_tenant_no UNIQUE` (migration 002):** the player enrolls
  with their *own* canonical number (e.g. 4102+), which has no archive file in
  the VM; the legitimate `legacy-archive` therefore returns an empty/own archive.
  Reading a *foreign* archive still requires the Stage 08 agent substitution —
  this is what motivates Stage 08 rather than trivializing it.

### Stage 05 — Service Boundary Analysis  `BV-05-OPERATOR-RECOVERY`
- **New surface:** `POST /api/v2/lab/operator-recovery` (tenant_admin): elevate
  to `system_admin` by presenting (a) the platform-operator receipt for
  installation 4100 (from Stage 03) and (b) proof the caller holds the
  `svc:aether-reporting` reporting identity (from Stage 04 enrollment).
- **Flaw (challenge):** binds the installation number + principal but **not** the
  destination tenant UUID — the Stage 02 flaw lifted one level. A player who did
  03+04 can elevate their own account.
- **Patched:** require installation receipt, principal and destination UUID to
  all agree; reject a foreign/platform receipt.
- **Boundaries (identical discipline to Stage 02):** grants `system_admin` only;
  per-account redemption tracking; atomic promotion+redemption in one tx under
  the workspace advisory lock; full audit of source/destination. **No permanent
  credential, no service key, no tenant reassignment.** This is why it is not
  "tenant_admin == system_admin": elevation requires two independently-earned
  artifacts and is a tracked, auditable, single-use role grant.

### Stage 06 — Restricted Linux Access  `BV-06-LAB-FOOTHOLD`
- **No new authorization code.** `terminal.go` already gates on `system_admin` +
  Origin + pinned host key + non-root `operator` SSH. Stage 05 is the sanctioned
  path to `system_admin`; Stage 06 is reaching the shell through the existing
  bridge. The gate is kept at `system_admin` (not relaxed to `tenant_admin`):
  challenge *completion* (Stage 05) is what produces that identity, so the
  terminal's authorization model already distinguishes it from arbitrary signup.
- **Work:** `make vm-up` profile; verify operator shell is non-root/non-sudo and
  cannot read `/etc/aether-agent/worker.key`; SSH port unpublished on host.

### Stage 07 — Native Service Investigation  `BV-07-AGENT-DISCOVERY`
- Inside the operator shell the player enumerates `aether-agent`: `GET /v1/build`
  (`agent/1.4.2-migration-protocol`, `legacy-envelope/1`), the archive dir, and
  the fact that the numeric selector is unsigned in the live build. They trigger
  a `legacy-archive` report (enrolled in Stage 04) and observe the worker→agent
  envelope on the lab interface, obtaining one valid worker-signed envelope.
- **Yields:** the Stage 08 prerequisite — a valid envelope the player can modify
  — obtained without the signing key and without organizer help.

### Stage 08 — Agent Identity Binding  `BV-08` (already implemented)
- Substitute `legacy_tenant_no` in the captured envelope → challenge agent returns
  the foreign bounded archive (signature covers only job/principal/UUID). Patched
  agent signs+validates the number and rejects. No change to the mechanism; the
  remaining work is documentation sync (timestamp/anti-replay already in code but
  undocumented) and the organizer walkthrough.

## Two verification paths (Requirement 4)

1. **Player-path integration** (`scripts/verify-chain.py`): fresh DB → register →
   Stage 01 → 02 → 03 → 04 → 05 → open terminal → in-VM capture → Stage 08, using
   only HTTP/SSH/agent interfaces a player uses. **No DB edits, no injected
   credentials, no organizer role grants.** Asserts each stage's privilege/enrollment
   actually changed via the public API (`GET /api/me`, `GET /api/v2/tenant`).
2. **Patched-mode regression** (extend existing `verify-*.py` + `vm-verify.py`):
   with `AETHER_IDENTITY_MODE=patched` / `AETHER_AGENT_MODE=patched`, assert every
   stage's exploit is refused while the legitimate same-tenant operation still
   succeeds (canonical recovery, canonical enrollment, canonical archive).

## Quality gate per stage (Requirement 6)

spec → migration/handler → clues in product artifacts → Go unit test (pure
resolution logic) → live challenge-mode check → live patched-mode check →
organizer walkthrough entry → unintended-bypass check → next stage reachable.

## Environment blockers (stated honestly, per directive)

- **QEMU is not installed on this host.** VM profiles (`make vm-up`) and the
  Stage 06–08 *integration* paths cannot be executed here; they build (cargo) and
  are unit-tested, but end-to-end VM verification must run on a QEMU/Docker host
  (CI uses the TCG path).
- **Full-stack `verify-*.py`** require `make up` (Docker). Runnable here but heavy;
  each is run and its result reported explicitly — never assumed from code presence.
- Application-side stages (03/04/05) are fully Go-testable without QEMU and are the
  first increments landed.

## Execution order (status tracked here)

1. Inspect repository — **done**.
2. This plan + dependency graph — **done**.
3. Stage 03 (settings + migration endpoint, migration 008, spec, Go test) — **implemented**;
   verified by `go build/vet/test` and by applying migrations 001–008 on real
   Postgres 16 (grants, cross-tenant read, and receipt-hash integrity checked).
   Live HTTP verification (`verify-reconstruction.py`) pending full-stack `make up`.
4. Stage 04, 5. Stage 05 — application-side, Go-testable.
6. Stage 06/07 VM wiring + Stage 08 doc sync + agent rebuild.
7. `verify-chain.py` + patched regression.
8. Update PROGRESS.md with actual command output.
