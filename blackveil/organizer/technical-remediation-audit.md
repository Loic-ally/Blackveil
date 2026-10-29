# BLACK VEIL — technical remediation audit

Private organizer material. Scope: Stages 01–08 only.

The source review confirmed that the old full-chain verifier used organizer SSH
for player actions after opening a terminal. Stages 06–08 now retain one player
WebSocket and execute discovery, permission checks and archive substitution in
that session. Delimiters split marker arguments to avoid PTY echoes; command
status is explicit, execution is in a subshell, and reads have a bounded deadline.
Standalone terminal regressions exercise echoes, frame splitting, repeated
commands, closure, nonzero status and timeout.

`make chain-verify` now verifies existing guests rather than provisioning them.
Missing guests must produce a nonzero result. Both guest fixtures are mandatory.
The patched fixture remains an independent organizer assertion, since player
terminals intentionally target only the challenge guest.

The disposable reset verifier creates a separate project, port, networks,
volumes and fresh `.env`. Agent-only restart uses a rule injected into the copy,
restricted to restarting aether-agent. It checks unchanged boot ID and changed
systemd invocation. VM/full reset compare SSH keys, captures and application
identity data, then rerun the full chain. Environment overrides are removed so
the caller cannot accidentally redirect the disposable project.

Current execution evidence and exact exit codes are in
[full-chain-validation.md](full-chain-validation.md). Prior audit claims are
superseded; no historical pass is treated as current verification.
