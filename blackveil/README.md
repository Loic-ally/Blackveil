# BLACK VEIL · AETHER

BLACK VEIL is a local, isolated cybersecurity CTF built around AETHER Industrial
Intelligence Platform. The challenge runs in disposable infrastructure and is
not intended for deployment on a public network.

## Start the current MVP

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

`make setup` generates a local database password and TLS certificate. The
working MVP currently includes registration and sessions, tenant-scoped
equipment and telemetry, incident workflows, internal notifications, CSV report
jobs, audit events, API documentation, PostgreSQL, Redis, NATS and a worker.
Challenge weaknesses are not part of this baseline increment.

The disposable Debian guest runs in a non-privileged QEMU container under TCG,
so no host virtualization package is required. A browser terminal is available
only to identities with the `system_admin` milestone; ordinary workspace
registration does not grant it. The terminal reaches the guest through the API
over the private lab network. `make vm-shell` remains an organizer-only route.
The worker's live report-to-agent job flow and the preceding identity stages
that grant the milestone are still in progress.

## Useful commands

```sh
make check          # Go checks, Next.js production build, Compose config check
make network-check  # Verify only the gateway publishes host ports
make vm-up          # Build and start the disposable Debian Linux guest
make vm-shell       # Organizer-only SSH through the private QEMU forward
make vm-verify      # Compare vulnerable and patched native-agent behavior
make vm-reset       # Remove only the two Linux guest disks and keys
make logs
make down
make reset          # Explicitly removes application data and Linux VM state
```

## Build status

See [PROGRESS.md](PROGRESS.md) for phase status. The core identity flaw and the
first stage specification are in `docs/`; the vulnerable implementation will be
added only after ordinary application behavior is tested.
