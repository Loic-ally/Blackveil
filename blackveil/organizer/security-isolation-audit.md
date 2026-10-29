# BLACK VEIL — security isolation audit

Private organizer material. Review date: 2026-10-29. Scope: Stages 01–08.
Execution results are in [full-chain-validation.md](full-chain-validation.md).

## Source findings

Compose publishes only gateway HTTPS. The gateway joins edge/app; API joins
app/data/lab for its terminal bridge; worker joins data/lab. App, data and lab
are internal networks. Guest services join lab, expose no host ports and mount
separate state volumes. No service mounts the Docker socket or uses privileged
mode. Services drop all capabilities and use no-new-privileges; required gateway
and database capabilities are added explicitly. Most root filesystems are read-only;
database, cache and bus are exceptions.

The API mounts challenge VM state read-only. Guest entrypoint sets the state
directory to 0710 with group 10001 and private files under umask 077. API has
supplementary group 10001 to read the operator key and pinned host public key.
Its SSH bridge validates the guest host key. The operator cannot read the agent
key or tenant map; these are root-owned 0600 in cloud-init. The agent unit runs
as a separate account with no capabilities, no-new-privileges, restricted address
families and system protection settings. The production operator has no sudo
service-control permission. These are source findings, not a penetration-test
claim.

## Executed checks

`make network-check` passed in this review: gateway-only publication, private
VM ports, internal networks and read-only API state mount. Full-chain Stage 06
checks uid/groups and Origin rejection; Stage 07 checks protected file reads.
Their actual execution status is recorded separately in the validation report.
No recursive secret scan, kernel/QEMU escape test or image CVE scan was performed
in this review. Historical claims of those checks are not current evidence.

## Destructive test boundary

The reset verifier copies the project into a temporary directory, generates new
secrets and selects a random bvreset project with a separate HTTPS port. Caller
Compose and AETHER overrides are removed before lifecycle operations. All
resets resolve the copy's .env and operate on its own volumes. Cleanup removes
only that project's services/volumes and temporary tree, leaving shared images.
A narrowly scoped sudo rule is injected only into the temporary cloud-init
renderer to restart aether-agent without rebooting the guest. Production source
and player permissions are unchanged. This fixture difference is intentional
and must be considered when interpreting lifecycle results.

## Limits

Replay state is process-local and forgotten on restart. Reset preserves .env
keys, so it is not signing-key rotation. Tagged container images, local TLS,
manual hostname setup and untested kernel/VM escape boundaries remain risks.
See [remaining-risks.md](remaining-risks.md).
