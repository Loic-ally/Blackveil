# BLACK VEIL · AETHER

BLACK VEIL is a local, isolated cybersecurity CTF built around AETHER Industrial
Intelligence Platform. The challenge runs in disposable infrastructure and is
not intended for deployment on a public network.

## Start the current playable build

Requirements: Docker Desktop with Compose, Go 1.23 or newer for local API checks,
Node.js 20.9 or newer for local web builds, and OpenSSL for the local certificate.

```sh
cd blackveil
cp .env.example .env
make setup
make up
```

Map `aether.blackveil.test` to `127.0.0.1` in the host's hosts file if it is not
already mapped. The setup script prints the required line. Trust the generated
self-signed certificate locally if desired, then open
`https://aether.blackveil.test` and create an ordinary operator workspace.

`make setup` generates local database and service credentials and a TLS
certificate. AETHER includes registration and sessions, tenant-scoped equipment
and telemetry, team invitations, incidents, internal notifications, CSV reports,
audit events, PostgreSQL, Redis, NATS and separate API, auth, worker and legacy
services. Stage 01 is a verified identity mismatch in historical exports; see
its [stage specification](docs/stages/stage-01-identity-parity.md).

The disposable Debian guest runs in a non-privileged QEMU container under TCG,
so no host virtualization package is required. A browser terminal is available
only to identities with the `system_admin` milestone; ordinary workspace
registration does not grant it. The terminal reaches the guest through the API
over the private lab network. `make vm-shell` remains an organizer-only route.
The worker sends enrolled archive reports to the guest agent. The browser
terminal requires the `system_admin` milestone, which a player reaches through
the Stage 01–05 challenge chain (ordinary signup → `tenant_admin` →
`system_admin`) with no organizer action; Stages 06–08 then play out inside that
terminal. Stages 09–15 are implemented and player-reachable (the full chain runs through
the WebSocket terminal and the `/lab` final-proof form). Run `make worker-verify`
with the VM running to exercise real queued archive delivery.

## Useful commands

```sh
make check          # Go checks, Next.js production build, Compose config check
make network-check  # Verify only the gateway publishes host ports
make vm-up          # Build and start the disposable Debian Linux guest
make vm-shell       # Organizer-only SSH through the private QEMU forward
make vm-verify      # Compare vulnerable and patched native-agent behavior
make worker-verify  # Verify VM archive delivery and interrupted-job recovery
make lifecycle-verify # Verify durable queued jobs with three competing workers
make team-verify    # Verify invitation and tenant authorization
make legacy-verify  # Verify Stage 01 in challenge and patched modes
make recovery-verify # Verify Stage 02 from ordinary signup in both modes
make db-roles-verify # Check service-specific database privileges
make web-chain-verify # Verify the player chain Stages 01-05 (no Linux guest)
make chain-verify   # Verify the full player chain Stages 01-15 (requires both guests already running)
make fencing-verify # Stale worker lease cannot complete or fail a reclaimed job
make reset-verify   # Fresh/guest restart/agent restart/VM reset/full reset in a disposable copy, chain after each
make vm-reset       # Remove only the two Linux guest disks and keys
make logs
make down
make reset          # Explicitly removes application data and Linux VM state
```

## Build status

See [PROGRESS.md](PROGRESS.md) for verified phase status and
[organizer/full-chain-validation.md](organizer/full-chain-validation.md) for the
latest recorded command results. Organizer verification scripts and `organizer/`
are for the local disposable lab and must not be exposed to players.

`make chain-verify` drives Stages 06–08 as shell commands inside the player's own
WebSocket terminal session; organizer SSH is used only for the patched-guest
regression, which no player terminal reaches. `make reset-verify` never touches
the running `blackveil` project: it copies the tree to a temporary directory and
runs it as a separate Compose project on port 18443 (`BLACKVEIL_PROJECT` /
`BLACKVEIL_HTTPS_PORT`), then removes it.

`make lifecycle-verify` temporarily stops workers, queues 24 reports across two
temporary tenants, and starts three worker replicas. It checks single claims,
notifications and tenant isolation, cleans up its tenants, and restores the
original worker count. Run `python3 scripts/verify-lifecycle.py --restart-app`
to also verify session and queue persistence across an application/database
stop/start. That option causes brief application downtime and retains named
volumes and guest state; CI runs it before Linux guest verification.

Full-chain verification requires both guests already running. Provision them with
`docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify up -d --build --wait aether-linux-vm aether-linux-vm-patched`
first; `make chain-verify` does not start missing guests. Terminal framing has
standalone regressions: `python3 scripts/test-terminal.py`.

The reset verifier injects a narrowly scoped agent-restart sudo rule only into
its disposable build. This permits a real service restart while preserving the
boot ID; production guest permissions are unchanged. Exact current results and
limits are recorded in [full-chain validation](organizer/full-chain-validation.md).
