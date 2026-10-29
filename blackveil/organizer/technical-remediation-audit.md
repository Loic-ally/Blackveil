# BLACK VEIL — technical remediation audit

**Private organizer material. Not a player artifact.** This file lives under
`organizer/`, which is outside the `./web`, `./api` and `./vm` Docker build
contexts and is additionally listed in `vm/.dockerignore`, so it is never baked
into a deployed image.

Audit date: **2026-10-29**. Scope of this pass: validate the reported problems
against the real source and running stack, then fix the one confirmed
chain-verification defect (directive §3 / STEP 2). Findings are classified and
marked **confirmed** (code/test evidence) vs **suspected**.

## 1. Confirmed defect (fixed this pass)

### HIGH — `chain-verify` silently skipped Stages 06–08 and still reported success

**Evidence (before fix):** `scripts/verify-chain.py` computed `vm_up = status != 503`
on the terminal handshake; when the guest was unavailable it printed
`SKIP: stage 06–08 …`, ran only the patched 03/04/05 regressions, and returned
normally — so `make chain-verify` exited `0` while the Linux half of the chain
(Stages 06, 07, 08 and the patched Stage 08 regression) never ran. A verifier
named `chain-verify` reporting full-chain success without the Linux stages is
exactly the failure the directive forbids.

**Fix:** `scripts/verify-chain.py` now has two explicit scopes:

- `--web` (`make web-chain-verify`): Stages 01–05 plus patched 03/04/05. The
  Linux guest is out of scope by request (printed as a NOTE, not a skip-on-
  failure). Exit 0.
- default (`make chain-verify`): Stages 01–08. A `503` terminal handshake, or a
  missing patched guest fixture, now raises and exits **nonzero**, naming the
  stages that did not execute and pointing to `make vm-up` / `make
  web-chain-verify`. It never prints a full-chain success line on a missing
  guest. The `make chain-verify` target brings up both the challenge and
  patched guests (`--wait`) first, and CI runs the web scope in the no-VM job
  and the full scope in the VM job (`.github/workflows/blackveil.yml`).

**Verification (live, this host — aarch64/TCG):**

| Scenario | Command | Result |
|---|---|---|
| Web scope, guest irrelevant | `python3 scripts/verify-chain.py --web` | PASS, exit 0 |
| Full scope, both guests up | `python3 scripts/verify-chain.py` | PASS 01–08 + patched, exit 0 |
| Full scope, challenge guest stopped | `python3 scripts/verify-chain.py` | AssertionError naming Stages 06–08, **exit 1** |

## 2. Verified already-correct (no change needed)

These were checked against source and the running stack and found to already
meet the directive; they are **not** claimed as new work.

- **Worker lease fencing & atomic completion (§7).** `processOneReport`
  (`api/internal/platform/platform.go`) claims with `FOR UPDATE SKIP LOCKED`,
  captures `attempt_count` as a fence, and gates both the failure and the
  completion writes on `status='running' AND attempt_count=$fence`; the
  completion and its notification share one transaction and only insert the
  notification when the fenced update affected exactly one row. `make
  fencing-verify` passes against the live DB (stale owner's completion/failure
  rejected; only the current fence owner completes).
- **Anti-replay (§6).** The patched Rust agent (`vm/agent/src/main.rs`) signs
  `legacy_tenant_no` and `issued_at`, rejects envelopes outside a 120s window,
  and rejects case-normalized duplicate signatures; challenge mode retains the
  intentional unsigned selector. The process-local `accept_once` cache is
  documented as acceptable because the `operator` cannot restart the service.
  `make chain-verify` exercises the patched-agent substitution refusal live.
- **Organizer-secret separation (§10).** Live probe as the guest `operator`
  (uid 1000, group `operator`, no sudo): `grep` for the worker key and its
  prefix across `/var /etc /run /tmp /home /opt` returned nothing;
  `/etc/aether-agent/worker.key` and `/var/lib/aether-agent` are
  `root:aether-agent` and unreadable; only the captured envelope under
  `/var/lib/aether-migration/` (Stage 07 evidence) is operator-readable.
  `organizer/` is outside all build contexts and in `vm/.dockerignore`.
- **Network isolation (§9).** `scripts/check-network.sh` passes: only the
  gateway publishes a host port (443), VM ports are private, app/data/lab
  networks are `internal`, and the API's VM-state mount is read-only.
- **Installation-id reservation.** Migration 011 advances the tenant-number
  sequence past the reserved 4100–4199 block; `chain-verify` asserts a fresh
  player tenant number is ≥ 4102 and its own migration history is empty.

## 3. Documentation reconciled (§11)

- `README.md` previously stated the challenge path granting guest access "has
  not yet been implemented" — stale; corrected to describe the live Stage 01–05
  → `system_admin` progression, and the command list now documents
  `web-chain-verify` and the mandatory-guest semantics of `chain-verify`.
- `PROGRESS.md` verification section rewritten to describe the two scopes and
  the hard-fail-on-missing-guest contract.

## 4. Remaining risks / not done this pass

- **Destructive reset & guest-restart validation (§8, §12).** `make reset` /
  `make vm-reset` are not exercised by an automated test; CI uses TCG only with
  no KVM/ARM64 matrix. Reset correctness is still asserted only by inspection.
- **Final evidence-correlation flow / isolated validator (Phase 6).** Absent, as
  before — out of scope for this remediation.
- **Blind playtest and difficulty rubric (Phase 9).** Not performed.
- **Stages 09–15.** Intentionally not started (directive).
