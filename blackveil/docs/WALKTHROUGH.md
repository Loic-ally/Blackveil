# BLACK VEIL — organizer solve walkthrough (private)

**Spoiler. Do not ship to players.** This is the complete solution for the
Stage 01 → Stage 08 chain. Receipts are random per database initialization, so
exact token values differ each reset; every value below is *extracted from a
response*, never guessed.

## The one idea

Every stage is the same bug class at a different hop: a component trusts a
caller-supplied legacy integer or a partially-bound receipt instead of binding
the full identity tuple `(user, role, tenant UUID, legacy integer, service
principal, job ID)`. AETHER migrated to UUID tenant identities but kept
integer-keyed compatibility paths; the binding between the two was never
completed. Patched mode derives every identifier from the authenticated UUID and
refuses disagreement.

Fixed identifiers used throughout (discoverable in-game):

| Name | Tenant UUID | Archive/installation no. |
|---|---|---|
| North Works (platform operator) | `4f3e2d1c-0b9a-4876-9d5c-4b3a29180716` | 4100 (platform), 4101 (archive) |
| Harbor Process | `9a8b7c6d-5e4f-4321-8abc-def012345678` | 4102 (archive) |
| Reporting principal | — | `svc:aether-reporting` |

A fresh player tenant gets its own `legacy_tenant_no` (≥ 4102 from the sequence)
and is **not** archive-enrolled.

## Setup

```sh
make setup && make up          # application stack
make vm-up                     # disposable Linux guest (challenge mode)
# add to /etc/hosts:  127.0.0.1 aether.blackveil.test
```

Open `https://aether.blackveil.test` (self-signed dev cert). All requests below
send `Origin: https://aether.blackveil.test` and carry the session cookie from
registration/login.

The entire chain is demonstrated automatically by `make chain-verify`
(`scripts/verify-chain.py`); this document is the manual version.

---

## Stage 01 — Identity parity → cross-tenant historical export

1. Register an ordinary account at `/`. You are an `operator` in your own
   workspace; `/api/me` shows your `tenant_id` (UUID). `/api/team` is 403 and the
   lab terminal is denied.
2. Product artifacts (reports UI, API docs, audit) show that historical reports
   are keyed by an **integer** `legacy_tenant_no`, separate from the UUID.
3. Submit a historical report naming *your own UUID* but a *foreign* installation
   number 4101:
   ```
   POST /api/v2/reports/historical
   {"tenant_uuid":"<your-uuid>","legacy_tenant_no":4101}
   ```
   Poll `/api/reports`; when complete, `GET /api/reports/{id}` returns North
   Works' bounded historical CSV even though you authenticated as a different
   tenant. The API checked the UUID against your session but copied the integer
   into the job unbound.
4. In that CSV, revision `ADM-21` contains the administrator **handover receipt**:
   `Recovery receipt: <64 hex>`. Save it.

*Win:* a bounded foreign archive read; the handover receipt for installation 4101.

## Stage 02 — Administrator recovery → `tenant_admin`

1. The `/team` recovery form (and `POST /api/v2/team/recover`) restores workspace
   administration from a migrated handover receipt.
2. Submit *your own* UUID, installation 4101 and the receipt from Stage 01:
   ```
   POST /api/v2/team/recover
   {"tenant_uuid":"<your-uuid>","legacy_tenant_no":4101,"receipt":"<ADM-21 receipt>"}
   ```
   Challenge mode validates the receipt against installation 4101 but does not
   bind the receipt's *source* tenant (North Works) to *your* workspace, so you
   are promoted to `tenant_admin` in your own workspace. `/api/me` now shows
   `role: tenant_admin` and `/api/team` works.

*Win:* `tenant_admin`. The terminal is still 403.

## Stage 03 — Historical state reconstruction

1. `GET /api/v2/tenant` shows your own canonical `legacy_tenant_no` and
   `archive_enabled:false`. Numbers are per-tenant identities.
2. `GET /api/v2/tenant/migration?legacy_tenant_no=N` returns migration history for
   installation `N` — and challenge mode does not bind `N` to your session, so
   you can read any installation. Enumerate:
   - `N=4100` → the **platform-operator** record (`PO-01`): North Works ran the
     shared lab; recovery binds principal `svc:aether-reporting` + installation
     4100; `Recovery receipt: <64 hex>` (the Stage 05 key). Save it.
   - `N=4101` / `N=4102` → the UUID↔number map and the reporting principal.
3. Confirm the extracted platform-operator receipt is real: its SHA-256 equals
   the stored hash (the organizer check in `verify-chain.py`).

*Win:* the platform-operator receipt (installation 4100) and the identity map.
No privilege gained.

## Stage 04 — Asynchronous trust investigation → reporting enrollment

1. `GET /api/v2/tenant/migration?legacy_tenant_no=4101` also carries revision
   `RP-22`: the reporting-identity **enrollment receipt**
   (`Enrollment receipt: <64 hex>`). Save it.
2. Enroll your own workspace as the reporting principal:
   ```
   POST /api/v2/tenant/reporting-identity
   {"tenant_uuid":"<your-uuid>","installation_no":4101,"receipt":"<RP-22 receipt>"}
   ```
   Challenge mode does not bind the receipt's installation (North Works) to your
   tenant, so your unmigrated workspace is enrolled as `svc:aether-reporting`.
   `GET /api/v2/tenant` and `/api/me` now show `archive_enabled:true`, and
   `POST /api/reports {"type":"legacy-archive"}` is accepted (202) where it was
   403 before. (Your archive slot is empty — reading a real archive still needs
   Stage 08.)

*Win:* the reporting identity (`svc:aether-reporting`) and the open worker→agent
path. No role gained.

## Stage 05 — Service boundary analysis → `system_admin`

1. `POST /api/v2/lab/operator-recovery` recovers the platform-operator identity.
   It requires **both** the platform-operator receipt (Stage 03) and the reporting
   identity you now hold (Stage 04):
   ```
   POST /api/v2/lab/operator-recovery
   {"tenant_uuid":"<your-uuid>","installation_no":4100,"receipt":"<PO-01 receipt>"}
   ```
   Challenge mode does not bind the receipt's tenant (North Works) to your
   workspace, so you are elevated to `system_admin` (single-use, audited).
   `/api/me` shows `role: system_admin`.

*Win:* `system_admin`. (A `tenant_admin` without the Stage 04 enrollment is
refused here — the two artifacts are both required.)

## Stage 06 — Restricted Linux access

1. As `system_admin`, open the browser terminal (`/lab`, which upgrades
   `GET /api/lab/terminal` to a WebSocket). The API bridges to a **non-root,
   non-sudo `operator`** SSH shell in the disposable guest. `id` shows uid 1000,
   group `operator`.

*Win:* a restricted Linux foothold inside the disposable VM.

## Stage 07 — Native service investigation

1. The agent is on `127.0.0.1:8080`: `curl -s 127.0.0.1:8080/v1/build` →
   `agent/1.4.2-migration-protocol`, `legacy-envelope/1`.
2. You **cannot** read `/etc/aether-agent/worker.key` or `tenant-map.csv` (owned
   `root:aether-agent`). But migration validation left a capture:
   ```
   cat /var/lib/aether-migration/last-archive-request.json
   ```
   This is one legitimate, worker-signed request for North Works (tenant
   `4f3e…`, `legacy_tenant_no:4101`) — a captured *message*, not the key.

*Win:* a valid worker-signed envelope you can replay.

## Stage 08 — Agent identity binding

1. Replay the capture as-is to confirm it works:
   ```
   curl -s -H 'Content-Type: application/json' \
     -d @/var/lib/aether-migration/last-archive-request.json \
     127.0.0.1:8080/v1/legacy/archive
   ```
   → North Works archive (`resolved_legacy_tenant_no:4101`).
2. Change **only** `legacy_tenant_no` to `4102` and resubmit the *same signature*:
   ```sh
   sed 's/"legacy_tenant_no": 4101/"legacy_tenant_no": 4102/' \
     /var/lib/aether-migration/last-archive-request.json \
   | curl -s -H 'Content-Type: application/json' -d @- 127.0.0.1:8080/v1/legacy/archive
   ```
   The challenge agent signs only `(job_id, principal, tenant_uuid)`, so the
   signature is still valid, and it returns **Harbor's** archive
   (`resolved_legacy_tenant_no:4102`, record mentions `harbor-process`) — a
   different tenant's data via one unsigned integer.

*Win:* cross-service identity confusion proven. Bounded archive only — no guest
root, no host access.

---

## Patched mode (the regression)

Set `AETHER_IDENTITY_MODE=patched` (API) and `AETHER_AGENT_MODE=patched` (guest).
Each flaw closes while legitimate same-tenant operations still work:

- **01** historical report resolves the caller's canonical archive, not the
  supplied integer.
- **02** recovery requires the receipt's source tenant to equal the destination.
- **03** migration lookup resolves the caller's own number; no foreign receipt.
- **04** enrollment requires the receipt's installation to equal the caller.
- **05** operator recovery requires installation, principal and destination UUID
  to agree.
- **08** the agent signs `legacy_tenant_no` and `issued_at`, derives the number
  from the UUID map, and rejects the substitution plus replayed/expired envelopes.

## Automated organizer verification

```sh
make chain-verify     # player path 01→08 (challenge) + patched 03/04/05/08
make vm-verify        # terminal auth, non-root operator, agent challenge/patched + replay/expiry
make fencing-verify   # worker lease fencing + atomic completion
make recovery-verify  # Stage 01→02 challenge + patched
make legacy-verify    # Stage 01 challenge + patched
```

Only `chain-verify` is a player-equivalent run: it reaches every stage through
the HTTP API and the player's own WebSocket terminal, with no database edits,
injected credentials or role grants. The other targets are organizer fixtures:
`vm-verify` grants `system_admin` with SQL and signs envelopes with the
organizer-held key; `chain-verify`'s patched-agent check uses organizer SSH
because no player terminal reaches the patched guest. `make reset-verify` reruns
`chain-verify` after fresh deploy, guest restart, agent restart, VM reset and
full reset in a disposable copy.
