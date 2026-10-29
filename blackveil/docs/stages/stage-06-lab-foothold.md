# Stage 06 — Restricted Linux access (lab foothold)

**Stage ID**

`BV-06-LAB-FOOTHOLD`

**Player objective**

As `system_admin` (reached in Stage 05), open the browser terminal and obtain
the restricted `operator` shell in the disposable AETHER Linux guest.

**Starting knowledge**

`system_admin`; the public application. No SSH key, guest address or organizer
access.

**System components**

`GET /api/lab/terminal` (unchanged), the WebSocket↔SSH bridge, the disposable
QEMU guest and its non-root `operator` account, the API-held operator key and
the pinned guest host key.

**Technical design (not a new vulnerability)**

Stage 06 introduces no new authorization code. `terminal.go` already gates on
`system_admin` plus the configured Origin, bridges a WebSocket to a non-root,
non-sudo `operator` SSH shell, and pins the guest host key. The previous gap was
that nothing *player-reachable* produced `system_admin`; Stage 05 now does. The
terminal gate is deliberately kept at `system_admin` (not relaxed to
`tenant_admin`) so that challenge completion — not ordinary signup — is what
opens the Linux lab. This is the authorization model distinguishing challenge
completion from system administration.

**Required observations**

The terminal returns 403 for every identity below `system_admin` and for a
foreign Origin; after Stage 05 elevation the same session opens the shell. The
shell is uid 1000 `operator`, non-root, cannot sudo, and cannot read the worker
signing key.

**Trigger conditions**

The disposable VM profile is running (`make vm-up`); the player holds a
`system_admin` session obtained through Stages 01–05.

**Expected result**

A non-root `operator` shell inside the disposable guest, isolated to the VM. The
foothold grants no host access, no Docker socket, no writable host mount and no
published guest ports.

**Verification**

`scripts/verify-chain.py` continues the live player path: after Stage 05 it opens
the terminal WebSocket from the player's own session (no SQL grant), confirms a
foreign Origin is rejected (403), completes the 101 handshake, and runs `id` to
confirm the non-root `operator` shell. The organizer `scripts/vm-verify.py`
additionally asserts the operator cannot read the worker key, cannot sudo, and
that guest state files are not readable from the API container.

**Remediation**

Not applicable — this stage is the intended, authorized foothold. Isolation is
maintained by the existing SSH bridge, host-key pinning, Origin enforcement and
the non-root operator account.

**Unintended solutions**

The guest must not expose root, sudo, the worker key, a Docker socket, a
writable host mount or published SSH/agent ports. The terminal must remain
`system_admin`-only and Origin-bound. Tests confirm sub-admin identities and
foreign origins are rejected.
