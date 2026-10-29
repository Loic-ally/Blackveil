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

