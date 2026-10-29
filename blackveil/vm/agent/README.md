# AETHER Linux agent

`aether-agent` is a small Rust daemon installed by cloud-init into the Debian
guest and started by systemd. Its bounded archive endpoint accepts a signed
report envelope. The stage-specific difference between `challenge` and
`patched` mode is documented in `docs/stages/stage-08-agent-identity-binding.md`.

The service has no shell execution, path-taking parameters or arbitrary file
read operation. Archive IDs are unsigned integers that select only files under
`/var/lib/aether-agent`. The worker key is readable by the agent service but
not by the guest's `operator` account.

Builds use the committed Cargo lockfile and the official Debian 13 cloud image
hashes in `vm/images/SHA512SUMS`. If Debian's `latest` object changes, the
checksum check fails closed; update the image metadata and hash intentionally.

## Envelope protocol and replay protection

The archive envelope carries `job_id`, `principal`, `tenant_uuid`,
`legacy_tenant_no`, `issued_at` and `signature` (`legacy-envelope/1`). The worker
signs an HMAC-SHA256 over a newline-joined projection of these fields:

- **challenge** signs `job_id\nprincipal\ntenant_uuid` only — the numeric
  selector and timestamp are unsigned, which is the Stage 08 weakness.
- **patched** signs `job_id\nprincipal\ntenant_uuid\nlegacy_tenant_no\nissued_at`,
  derives the accepted number from the UUID→number map, and additionally
  enforces freshness and single-use: it rejects an envelope whose `issued_at` is
  more than `REPLAY_WINDOW_SECS` (120s) from the guest clock, and rejects a
  signature it has already served within that window (signatures are compared
  case-normalized, since hex decoding accepts either case).

The replay cache is process-local: an agent restart forgets signatures still
inside the window. This is acceptable in this environment because the `operator`
account cannot restart the service (no sudo/systemctl) and a per-request thread
panic does not restart the process; persist the cache only if guest restarts
ever become player-triggerable.


Verification uses two distinct paths: the full-chain verifier submits the
operator-readable retained capture and changes only its numeric selector through
one player WebSocket session. `vm/verify-agent.py` uses organizer-signed fixtures
to test patched binding, freshness and duplicate rejection independently. A
refusal of the old retained capture alone does not distinguish an invalid
signature from expiry. Reboots and service restarts clear the replay cache;
reset/reprovisioning preserves `.env`'s signing key and regenerates guest SSH
keys and the retained capture. See `organizer/full-chain-validation.md` for
executed checks rather than inferring results from these protocol properties.
