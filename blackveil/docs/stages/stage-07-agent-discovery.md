# Stage 07 — Native service investigation (agent discovery)

**Stage ID**

`BV-07-AGENT-DISCOVERY`

**Player objective**

Inside the restricted `operator` shell (Stage 06), investigate the native
`aether-agent`, understand its archive protocol, and obtain the legitimate
prerequisite for Stage 08: a valid worker-signed archive envelope. Do this
without the signing key, the tenant map or root.

**Starting knowledge**

A non-root `operator` shell in the disposable guest; the `svc:aether-reporting`
principal and the UUID↔installation map reconstructed in Stages 03–04; the
knowledge that archives are selected by a numeric identity.

**System components**

The Rust `aether-agent` (listening on `127.0.0.1:8080` in the guest), its
`GET /v1/build` and `POST /v1/legacy/archive` endpoints, the root/`aether-agent`
owned key/map/archives the operator cannot read, and a retained operator-readable
capture of one legitimate worker-signed request under `/var/lib/aether-migration/`.

**Technical design (prerequisite, not a new vulnerability)**

The operator enumerates the agent: `GET /v1/build` reports
`agent/1.4.2-migration-protocol` and `legacy-envelope/1`. The operator cannot
read `/etc/aether-agent/worker.key` or `tenant-map.csv` (owned `root:aether-agent`,
mode 0640; `operator` is not in that group) and cannot read the archive files.
The only obtainable authorization material is a **retained capture** of one past
legitimate worker-signed request (North Works, installation 4101) left under
`/var/lib/aether-migration/last-archive-request.json` during migration
validation. This is a captured message, not the signing key: the operator cannot
forge a new envelope for a different job or tenant. It is the envelope Stage 08
manipulates.

**Realistic origin**

Migration validation retained the last reporting-archive request on the lab host
for support. The capture was never purged, and the agent's challenge-mode signing
projection does not cover the numeric selector, so the capture remains usable for
a substitution attack.

**Required observations**

Two independent signals: the agent's build/protocol metadata (which identifies
the envelope schema), and the retained capture's structure — a valid signature
over `(job_id, principal, tenant_uuid)` with a separate `legacy_tenant_no` field.
Together they show the signature authenticates only part of the request.

**Reasoning requirement**

Infer that the captured signature authenticates a subset of the envelope, so the
`legacy_tenant_no` can be changed while the signature stays valid — then test it
in Stage 08.

**Trigger conditions**

The disposable VM is running in challenge mode; the player has the operator
shell; the retained capture is present; the agent serves `/v1/legacy/archive`.

**Expected result**

The player reads a valid North Works worker-signed envelope and confirms the
agent's protocol, without obtaining the key, the map or root. This is the
legitimate Stage 08 prerequisite, obtained with no organizer intervention.

**Misleading hypotheses**

The capture may look like a static archive dump; the player distinguishes it by
its envelope fields (principal, signature) and by replaying it against the live
agent. The agent's 404 for unmapped tenants may suggest the capture is useless;
the player confirms the captured tenant (North Works) is mapped.

**Verification**

`scripts/verify-chain.py` (challenge): over the operator SSH the terminal uses,
confirm `GET /v1/build`, read the retained capture, confirm it is the North Works
reporting envelope, and confirm the operator cannot read the worker key.

**Remediation**

Purge retained request captures from lab hosts; never leave signed envelopes on
disk; and (with Stage 08) sign the full authorization projection so a captured
envelope cannot be repurposed by changing the numeric selector.

**Difficulty justification**

The player must combine Linux service discovery with the application-layer
identity semantics from Stages 03–04 to recognize that a captured partial-signed
envelope is the key to the agent's numeric-selector flaw.

**Unintended solutions**

The operator must not read the worker key, the tenant map or the archive files,
gain root or sudo, or escape the guest. The capture is a single bounded envelope;
it does not let the operator forge envelopes for arbitrary jobs or tenants.
