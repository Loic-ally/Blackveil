# Stage 01 — Identity parity

**Stage ID**

`BV-01-IDENTITY-PARITY`

**Player objective**

Establish which tenant identity is authoritative at the modern API boundary and
determine whether the retained compatibility path preserves that binding.

**Starting knowledge**

The player has only `https://aether.blackveil.test`, can create an ordinary
workspace account, and can use the platform's public website and documented
product functions. No privileged account or internal service address is given.

**System components**

AETHER web, authentication service, UUID-based API, legacy numeric-tenant
service, PostgreSQL audit history and API documentation.

**Technical root cause**

The authenticated request to `POST /api/v2/reports/historical` must name the
caller's own `tenant_uuid`. The API checks that UUID against the session, then
copies the request's `legacy_tenant_no` into the queued job without checking
that the number belongs to that UUID. The worker asks the legacy service for
records using that number. Patched mode ignores the supplied number and resolves
the archive number from the canonical worker migration map. Workspaces with no
archive migration resolve to the empty archive (number zero), so newly allocated
database tenant numbers cannot collide with historical archive identifiers.

**Realistic origin**

AETHER retained old reporting integrations during a tenant migration. Product
teams migrated interactive APIs first; reporting and customer-support workflows
continued to depend on integer keys and archived schema versions.

**Required observations**

The player must collect at least two independent signals: a mismatch between
current and archived identity fields in a normal application artifact, and a
behavioral or audit difference between the UUID API and compatibility service.

**Reasoning requirement**

Infer that the numeric value is a separate authorization identity rather than a
harmless display field, then test whether the compatibility operation binds it
to the authenticated UUID tenant.

**Trigger conditions**

Challenge mode, two seeded tenant migration records, an authenticated
low-privilege account in one tenant, the account's own UUID, the other tenant's
historical integer from product migration evidence, and a completed asynchronous
historical-report job. No timing race or external dependency is required.

**Expected result**

The completed job contains a bounded archived report from the tenant represented
by `legacy_tenant_no`, despite the request being authenticated as a different
UUID tenant. This stage does not grant host access or administrative API
privileges.

**Misleading hypotheses**

The archived integer may be a harmless chart sequence or asset number; the
player can reject that interpretation by comparing its stable relationship to
tenant-scoped audit and report records. A stale browser cache may appear
responsible; repeating the operation with a fresh session distinguishes it.

**Verification**

An organizer test will create two tenants, authenticate a low-privilege user in
one, submit that user's UUID with a seeded historical tenant's integer, verify
the bounded record and assert that patched mode returns only the authenticated
tenant's archive while preserving ordinary reports.

**Remediation**

Resolve all legacy identifiers server-side from the authenticated canonical
tenant UUID, bind them to the job and principal, reject caller-provided identity
aliases, and record the canonical decision in audit events.

**Difficulty justification**

The player must connect a migration artifact to API behavior and audit evidence;
one isolated request or error message does not explain the full identity
relationship.

**Unintended solutions**

The stage must not expose database credentials, an unscoped list endpoint,
predictable privileged credentials, direct database/message-bus access, or a
player-facing debug route. Tests must verify these paths remain unavailable.
