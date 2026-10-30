# BLACK VEIL — advanced extension assessment (Stages 09–15)

**Private organizer material. Not a player artifact.**

Assessment date: **2026-10-30**. This is the mandatory pre-implementation audit
for the Stage 09–15 extension. It records what the repository actually contains
(read this pass), what can be extended safely, and the boundaries that must stay
intact. Nothing here is a design decision — the design is in
[attack-graph-v3.md](attack-graph-v3.md). Nothing here is invented; every claim
cites a file read in this pass.

## 1. What exists (authoritative, from source)

### Application (Go, `api/internal/platform/`)
- Modes selected by `AETHER_MODE`: `api`, `auth`, `worker`, `legacy`,
  `telemetry`, `migrate` (`compose.yaml`). One binary, mode-switched.
- Identity chain Stages 01–05 live in `legacy.go`, `recovery.go`, `tenant.go`,
  `reporting.go`, `operator.go`; migrations `001`–`011`.
- `terminal.go` bridges an authenticated `system_admin` WebSocket to the guest
  `operator` SSH shell; pins the guest host key; rejects foreign `Origin`.
- `AETHER_IDENTITY_MODE` (`challenge`|`patched`) switches the app-side flaws.

### Linux guest (`vm/`)
- `aether-linux-vm` service: unprivileged QEMU (TCG on this host) booting a
  Debian 13 cloud image, `cap_drop: [ALL]`, `no-new-privileges`, read-only
  rootfs, no devices/socket/host mount. State in named volume.
- `vm/agent/` — Rust `aether-agent` (read in full this pass). One binary, HTTP
  on `0.0.0.0:8080` in-guest. Endpoints `GET /healthz`, `GET /v1/build`,
  `POST /v1/legacy/archive`. HMAC-SHA256 over a **mode-dependent projection**:
  challenge signs `job_id\nprincipal\ntenant_uuid`; patched adds
  `legacy_tenant_no\nissued_at`, derives the number from the UUID map, enforces a
  120 s window and a process-local single-use cache.
- `vm/render-cloud-init.py` provisions, via cloud-init `write_files` + `runcmd`:
  the agent binary (`/usr/local/sbin/aether-agent`), `worker.key`,
  `tenant-map.csv`, archives (`/var/lib/aether-agent/archive-{4101,4102}.json`),
  the systemd unit, the `operator` account (key-only, locked, no sudo), and the
  Stage 07 capture (`/var/lib/aether-migration/last-archive-request.json`).

### Modes and secrets
- `AETHER_AGENT_KEY` (HMAC key) is in `.env`, baked into the guest cloud-init
  seed (volume, mode 0600, uid 10001), and readable in-guest only by
  `root:aether-agent`. The `operator` cannot read it (confirmed live in the
  isolation audit).
- `AETHER_LEGACY_SERVICE_KEY` is separate, app-side only.

### Verification harness
- `scripts/verify-chain.py` — player-equivalent 01–08; Stages 06–08 run as shell
  commands in the player's own WebSocket terminal (`Terminal` class). Hard-fails
  (never skips) when the guest is absent.
- `scripts/verify-reset.py` — disposable-copy fresh/restart/reset matrix.
- `vm/verify-agent.py`, `scripts/vm-verify.py` — organizer agent/terminal checks.
- Component suites: smoke, team, legacy, recovery, db-roles, fencing, lifecycle,
  worker, network.

## 2. Reusable extension points (safe to build on)

| Need for 09–15 | Existing hook | How it extends without touching 01–08 |
|---|---|---|
| A second native binary in the guest | `vm/` build + cloud-init `write_files`/`runcmd` | Add a new `write_files` block + unit; a new Cargo bin target or crate under `vm/`. The agent is untouched. |
| New in-guest service identity / account | cloud-init `runcmd` `useradd` pattern | Add accounts/groups the same way `aether-agent` and `operator` are made. |
| Confinement (namespaces/mounts) inside the guest | systemd unit hardening already used (`ProtectSystem`, `PrivateTmp`, `RestrictNamespaces`) | New units can opt into / out of specific isolation to create the Stage 10/11 surface — entirely inside the guest. |
| Player reaches new guest services | the authenticated WebSocket terminal | Players use the shell; no new player network path needed. |
| App-side clues / provenance records | audit events, migration records, worker provenance | New migrations and audit actions, additive. |
| Mode switching | `AETHER_AGENT_MODE`, `AETHER_IDENTITY_MODE` | New stages read the same env for challenge/patched. |
| Isolated final validator | a new Compose service on a **non-lab, non-player** network | Mirrors how the patched guest is a separate fixture; validator holds its key, never in a player image. |

## 3. Guest permissions available to the player

- `operator`: uid 1000, group `operator` only; key-only SSH; account locked
  (`usermod --lock`); **no sudo** (confirmed). Cannot read `worker.key`,
  `tenant-map.csv`, archive files, block devices, cloud-init user-data, or logs
  in group `adm`.
- The player can run arbitrary unprivileged commands, read world/operator-
  readable files, reach `127.0.0.1:8080` (agent), and inspect `/proc` for its
  own processes. This is the surface Stages 09–11 must build on — new readable
  evidence and new local services, not new host capability.

## 4. What Stage 08 actually produces (the entry state for Stage 09)

- A player who has: `system_admin` in the app; an `operator` shell; the ability
  to replay/modify the captured worker-signed envelope against the agent
  (challenge: numeric substitution returns a foreign bounded archive).
- Knowledge established: the agent authenticates only a **subset** of a request;
  numeric identity is trusted unsigned; a UUID→number map exists but is not
  operator-readable; the system came from a numeric→UUID migration.
- **Not** produced: any guest privilege beyond `operator`, any key, any host
  access. Stage 09 must start from exactly this and require new investigation.

## 5. Organizer-only material (must never enter a player image)

- `AETHER_AGENT_KEY`, `AETHER_LEGACY_SERVICE_KEY`, DB passwords — `.env`.
- `worker.key`, `tenant-map.csv`, archive files — guest, root-owned.
- Everything under `organizer/` — outside all build contexts, in
  `vm/.dockerignore`.
- New for 09–15: any final-proof validation key must live only in the isolated
  validator service, never in `web/`, `api/`, or `vm/` images.

## 6. Boundaries that must remain intact

1. Only the gateway publishes a host port (443). New services join internal
   networks only; the validator is reachable by organizer assertion, not by the
   player host.
2. No privileged container, Docker socket, host device, or host mount — for any
   new service. New privilege surfaces live **inside** the guest.
3. The guest cannot reach the host; the player cannot reach the host. Stage 11's
   "root" must be namespace/sandbox root inside the guest, provably not guest
   host root and not the physical host.
4. Stages 01–08 mechanisms and progression are frozen. New stages chain off
   Stage 08's output; they do not alter it. Only strictly necessary
   compatibility changes are allowed, and must be called out.
5. Every stage keeps a challenge/patched pair and player-equivalent verification;
   a missing guest fails the full verifier, never skips.

## 7. Risks specific to this extension (carried into remaining-risks.md)

- **Build weight.** Each guest-integrated stage needs a guest rebuild (~minutes
  under TCG). Verification is real but slow; host-runnable unit tests (Rust/Go
  test vectors) are the fast inner loop and are the primary regression gate.
- **Namespace features under TCG.** Stage 10/11 must use only namespace/mount
  features available in the unprivileged guest; anything needing host kernel
  privileges is out.
- **Scope honesty.** 09–15 is multi-session. Increments are committed only when
  their tests run green; unbuilt stages stay documented, not stubbed as passing.
