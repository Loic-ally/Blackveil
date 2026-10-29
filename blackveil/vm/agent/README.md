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

