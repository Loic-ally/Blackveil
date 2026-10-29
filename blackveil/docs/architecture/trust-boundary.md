# AETHER identity migration trust boundary

## Central failure

AETHER's current identity model assigns every organization a UUID and authorizes
API requests against that UUID. A retained compatibility service still accepts
the historical integer tenant key. The asynchronous worker translates between
those identifiers using a service-principal mapping that has its own lifecycle.
The native Linux agent later trusts a compact identity envelope emitted by the
worker. Those representations are not yet governed by one canonical binding.

The intended challenge is about the failure to preserve one tenant identity and
one authorization decision across a migration. It is not a password guessing
challenge and must not depend on access to a host Docker socket or host files.

## Components and intended authority

| Component | Identifier it understands | Authority it should have |
|---|---|---|
| AETHER web / API | UUID tenant ID | User-scoped reads and writes for the authenticated tenant |
| Auth service | UUID tenant ID + role | Issue and validate user sessions |
| Legacy service | Historical integer tenant ID | Compatibility reads only for a worker-authorized request |
| Worker | Service principal + canonical tenant UUID | Process jobs queued by the API and publish bounded results |
| Native agent | Worker-issued job envelope | Perform only the operation and tenant scope encoded in a verified envelope |

## Challenge invariant

Every hop must bind `(user, role, tenant UUID, legacy integer, service principal,
job ID)` to one authorization context. A hop may not reconstruct authority from a
caller-controlled legacy integer, stale mapping, display label or partial token.
Challenge mode will violate a specific binding at a time; patched mode will
derive all representations from a canonical server-side tenant record and reject
disagreement.

## Evidence design

The player-facing clues will be ordinary product artifacts: API schema history,
migration/audit records, asynchronous job metadata, and service behavior. No
artifact will name the intended vulnerability. At least two independent
observations must support each required inference. Organizer specifications and
walkthroughs live outside the web build context.

## Safe execution boundary

The Linux agent and all host-compromise stages belong inside a disposable VM.
The application containers will not receive privileged mode, host device access,
the Docker socket or writable host mounts. The final validator will run outside
both player-facing networks and the challenge VM.
