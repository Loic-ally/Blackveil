# Full-chain validation — 2026-10-29

Private organizer evidence. Scope: Stages 01–08. Production vulnerability
mechanisms and progression were not changed. Stages 09–15 were not implemented.

## Commands and exit codes

Commands below ran from `blackveil` unless the directory column says otherwise.
A zero Rust test result includes zero unit tests; agent behavior is tested by
`make vm-verify`. Docker checks required access outside the filesystem sandbox.

| Directory | Command | Exit code |
|---|---|---|
| api | `env GOPATH=/tmp/blackveil-gopath GOMODCACHE=/tmp/blackveil-gomod GOCACHE=/tmp/blackveil-go-cache go test ./...` | 0 |
| api | `env GOPATH=/tmp/blackveil-gopath GOMODCACHE=/tmp/blackveil-gomod GOCACHE=/tmp/blackveil-go-cache go vet ./...` | 0 |
| vm/agent | `cargo test --locked` | 0 (zero unit tests) |
| web | `npm run build` | 0 |
| blackveil | `python3 scripts/test-terminal.py` | 0 (4 tests) |
| blackveil | `docker compose --env-file .env -f compose.yaml config --quiet` | 0 |
| blackveil | `make network-check` | 0 |
| blackveil | `python3 scripts/smoke.py` | 0 |
| blackveil | `make team-verify` | 0 |
| blackveil | `make legacy-verify` | 0 |
| blackveil | `make recovery-verify` | 0 |
| blackveil | `make db-roles-verify` | 0 |
| blackveil | `make worker-verify` | 0 |
| blackveil | `make fencing-verify` | 0 |
| blackveil | `python3 scripts/verify-lifecycle.py --restart-app` | 0 |
| blackveil | `make vm-verify` | 0 |
| blackveil | `make web-chain-verify` | 0 |
| blackveil | `make chain-verify` | 2 |

The first `make chain-verify` returned 2 after completing all eight player
stages because the separate patched guest was absent. It printed no full-chain
success. The underlying Python verifier exited 1; Make maps recipe failure to 2.
`make vm-verify` uses a temporary patched fixture and cleans it up, so the
persistent patched guest must be provisioned separately for `chain-verify`.

The persistent patched fixture was then provisioned:
`docker compose --env-file .env -f compose.yaml --profile vm-verify up -d --build --wait --wait-timeout 900 aether-linux-vm-patched > /tmp/blackveil-patched-start.log 2>&1` exited **0**.
The final `make chain-verify > /tmp/blackveil-chain-final.log 2>&1` exited **0**,
including Stages 01–08 and patched 03/04/05/08 assertions. This run includes the
stricter patched assertion requiring `service signature rejected`, so transport
failure or arbitrary invalid JSON cannot count as a patched refusal.

## Disposable lifecycle run

Command: `python3 scripts/verify-reset.py > /tmp/blackveil-reset-validation.log 2>&1`.
Project: `bvresetc38f9e`, port 18443. Final exit code: **0**. Disposable containers, networks and volumes were removed.
Fresh full-chain verification passed. Stopping the challenge guest made
`make chain-verify` return 2 with the explicit Stages 06–08 unavailable message.
All five scenarios passed, each followed by `make chain-verify` (exit 0):

| Scenario | Command inside disposable copy | Exit | Identity assertions |
|---|---|---|---|
| Fresh deployment | `docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify up -d --build --wait --wait-timeout 900` | 0 | Receipts, SSH keys and capture provisioned |
| Required guest absent | `make chain-verify` after `docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify stop aether-linux-vm` | 2 (expected); stop 0 | Explicit 503; no full-chain success |
| Guest restart | `docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify restart aether-linux-vm aether-linux-vm-patched` | 0 | Boot/invocation changed; keys, capture, receipts and marker preserved |
| Agent restart | `sudo -n /usr/bin/systemctl restart aether-agent` via organizer SSH in disposable challenge guest | 0 | Invocation changed; boot ID, keys and capture preserved; patched guest unchanged |
| Worker recovery | `python3 scripts/verify-worker.py` | 0 | Archive delivery recovered after agent restart |
| VM reset | `sh scripts/vm-reset.sh` with `RESET-VM` on stdin | 0 | Guest SSH keys/captures regenerated; database receipts and marker preserved |
| Full reset | `sh scripts/reset.sh` with `RESET` on stdin | 0 | Guest keys/captures and database receipts regenerated; marker removed; .env key preserved |

After each restart/reset, the same Compose up command above waited for readiness
and `docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify exec -T aether-gateway nginx -s reload`
exited 0 before assertions. Cleanup used
`docker compose --env-file .env -f compose.yaml --profile vm --profile vm-verify down --volumes --remove-orphans`;
the log confirms the project resources were removed.

The run copied the source before the final terminal subshell/strict patched-error
assertion changes; the persistent final full-chain run separately verified those.
After the lifecycle run started, receipt comparison was made order-independent
and cleanup was hardened to use the sanitized environment and propagate failure.
These two harness-only changes were syntax-checked; the five-scenario run was
not repeated after them.

## Interpretation

Stages 06–08 use one authenticated WebSocket session. The terminal regression
suite covers PTY echoes, split frames, repeated commands, exit status, closure
and timeout. Organizer helpers are limited to setup, cleanup and independent
assertions. Patched protocol checks use organizer-signed fixtures separately.

Reset tests inject a narrowly scoped restart permission only into the copied
guest fixture. Service restart must change InvocationID while preserving boot
ID. Guest restarts preserve keys/capture/application data; VM reset regenerates
guest keys/capture while preserving database identity; full reset regenerates
database receipts and removes a marker user, while retaining .env signing keys.

No successful CI run, blind playtest, image CVE scan or VM escape test is claimed.

## Final static checks

From the repository root:
`python3 -m py_compile blackveil/scripts/verify-reset.py blackveil/scripts/verify-chain.py`
exited 0. `git diff --check` exited 0. The terminal regression suite was rerun
after the final terminal changes: 4 tests, exit 0.

Evidence excerpts: [validation-evidence.txt](validation-evidence.txt). Full local
logs: `/tmp/blackveil-reset-validation.log`, `/tmp/blackveil-chain-final.log`,
`/tmp/blackveil-check-0.log` through `-12.log`. The numbered command mapping is
in [validation-commands.json](validation-commands.json). These are local runs;
no CI result is inferred.
