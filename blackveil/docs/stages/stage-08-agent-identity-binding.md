# Stage 08 — Agent identity binding

**Stage ID**

`BV-08-AGENT-IDENTITY-BINDING`

**Player objective**

Show whether the native Linux agent binds a historical tenant number to the
authenticated tenant UUID when it processes a worker-signed archive request.

**Starting knowledge**

The player has completed application and asynchronous-worker investigation and
has reached the restricted `operator` shell in the disposable AETHER Linux VM.
They know the UUID for the requester's tenant and have found archived records
that use numeric tenant identities. They do not have root access or the worker
signing key.

**System components**

AETHER API and worker, the private `lab` Docker network, QEMU user-mode
networking, Debian 13 cloud guest, the Rust `aether-agent` daemon, its
tenant-number map and archived maintenance records.

**Technical root cause**

In challenge mode, `aether-agent` verifies the worker HMAC over `job_id`,
`principal`, and `tenant_uuid`, then uses `legacy_tenant_no` to select the
archive without including that number in the signed projection or checking the
UUID-to-number mapping. Patched mode includes the number in the HMAC and derives
the accepted number from the UUID mapping.

**Player prerequisite path (Stages 06–07)**

The player reaches the `operator` shell through Stages 01–06 (no organizer
action) and, in Stage 07, reads a retained operator-readable capture of one
legitimate worker-signed request (North Works) left under
`/var/lib/aether-migration/`. This capture — not the signing key — is the valid
envelope this stage manipulates: the player substitutes only `legacy_tenant_no`
and resubmits it to the agent at `127.0.0.1:8080`. `scripts/verify-chain.py`
exercises exactly this path end-to-end inside the player's WebSocket terminal
(`sed` on the capture piped to `curl`). The patched-agent refusal is an organizer
assertion over the patched fixture's loopback SSH, because no player terminal
reaches that fixture.

**Realistic origin**

The reporting worker migrated to UUID tenant identities, while a Rust archive
agent retained a numeric lookup interface. The worker's signing projection was
copied from its newer envelope schema, which did not carry the legacy field.
The ordinary `legacy-archive` report resolves the tenant's enabled reporting
service identity from PostgreSQL, submits a signed envelope over the private lab
network, and returns CSV. Only tenants enrolled in archive migration can queue
this report. The API never accepts a client-supplied numeric tenant or principal.

**Required observations**

The player can compare the service build/protocol metadata with archived API and
worker records. The agent's request behavior and its local tenant map provide
independent evidence about the two identity fields.

**Reasoning requirement**

Infer that a valid worker signature authenticates only a subset of the request,
then test whether changing the numeric identity affects the archive selected
while preserving the signed UUID and job fields.

**Trigger conditions**

The disposable VM profile is running in challenge mode; the player has a
restricted guest shell; a valid UUID-to-number migration record and a second
archived tenant number are available; and the worker submits an HMAC-valid
archive envelope. Patched mode uses the same fixture with full-field signing and
canonical UUID-to-number resolution.

**Expected result**

Challenge mode returns the bounded archive selected by a substituted historical
number. Patched mode rejects that envelope while accepting a valid request for
the UUID's mapped archive. The result is evidence of cross-service identity
confusion; it does not grant guest root or host access.

**Misleading hypotheses**

The old number may be a report sequence rather than a tenant key; compare it
with the local mapping and the archive response. A stale archive cache may seem
responsible; use a new job ID and compare the resolved number in the response.

**Verification**

The organizer verification starts challenge and patched guests. It sends one
valid request, then changes only `legacy_tenant_no` without changing the HMAC.
Challenge mode must return the other bounded archive; patched mode must reject
the altered request and accept the canonical request. Verification also
confirms ordinary registered operators cannot open the browser terminal and
the guest SSH port is not published on the host.
The live worker verification also queues archive reports through authenticated
HTTPS, checks archive CSV and audit/notification completion, and confirms an
unenrolled tenant cannot queue the report or download another tenant's result.

**Replay and timestamp protection (patched)**

The envelope carries an `issued_at` field. Challenge mode leaves it unsigned (as
with the numeric selector), so a captured envelope replays indefinitely and a
substituted number is accepted. Patched mode signs `issued_at` and
`legacy_tenant_no` as part of the projection, rejects an envelope whose
`issued_at` is more than 120 seconds from the guest clock, and rejects a
signature already served within that window (compared case-normalized). The
`accept_once` cache is process-local; this is sufficient here because the
`operator` cannot restart the agent and a per-connection panic does not restart
the process. `vm/verify-agent.py` asserts the patched agent rejects a replayed
(case-flipped) signature and an expired (`issued_at` 600s old) envelope.

**Remediation**

Sign a canonical, versioned representation of every authorization field; derive
legacy numbers from the authenticated UUID on the server side; bind the
principal, tenant, operation and job ID; and reject replayed or mismatched
envelopes.

**Difficulty justification**

The player must combine application identity semantics, queue/job evidence,
Linux service discovery and native protocol analysis. A successful request
requires explaining the different meanings assigned to one signed envelope by
the worker and the daemon.

**Unintended solutions**

The guest must not receive the worker key, Docker socket, writable host mount or
published SSH/agent ports. Archive selection is numeric-only and bounded; the
agent does not accept filesystem paths, shell commands or arbitrary tenant data.

