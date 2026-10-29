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

**Realistic origin**

The reporting worker migrated to UUID tenant identities, while a Rust archive
agent retained a numeric lookup interface. The worker's signing projection was
copied from its newer envelope schema, which did not carry the legacy field.

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

