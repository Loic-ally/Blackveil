# Stage 03 — Historical state reconstruction

**Stage ID**

`BV-03-HISTORICAL-RECONSTRUCTION`

**Player objective**

As a workspace administrator (`tenant_admin`, reached in Stage 02), reconstruct
the AETHER identity-migration map and discover how the shared lab was operated,
without any further privilege grant. Produce the leads required for Stages 04
and 05.

**Starting knowledge**

The player holds `tenant_admin` in their own workspace, knows their own UUID,
and has the public site and API documentation. They do not know other tenants'
numbers, the reporting service principal, or that a platform-operator recovery
path exists.

**System components**

AETHER web/API, the new tenant settings view (`GET /api/v2/tenant`), the tenant
migration history endpoint (`GET /api/v2/tenant/migration`), the API-owned
`tenant_migration_records` table and the `platform_operator_recovery_receipts`
table (migration 008).

**Technical root cause**

`GET /api/v2/tenant/migration?legacy_tenant_no=N` resolves records by the
caller-supplied installation number `N` without binding it to the authenticated
session tenant — the Stage 01 flaw re-expressed at the settings layer. A
workspace administrator can therefore read the migration records of any seeded
installation (4100 platform operator, 4101 North Works, 4102 Harbor). Patched
mode ignores `N` and resolves the caller's own canonical `legacy_tenant_no` from
`tenants`, so it returns only the caller's own (empty) migration history.

`GET /api/v2/tenant` returns only the caller's own tenant row (name, canonical
`legacy_tenant_no`, archive-enrollment status) and is not the vulnerable
surface; it exists so the player can see that installation numbers are
per-tenant identities and that their workspace is not yet archive-enrolled.

**Realistic origin**

During migration, AETHER kept a settings-level "migration history" view for
support staff that keyed records on the historical installation number. The
UUID binding that governs the modern API was never added to that compatibility
view.

**Required observations**

Two independent signals: (1) the caller's own canonical number from the settings
view versus numbers that return foreign records from the migration endpoint, and
(2) the stable UUID↔number↔principal relationship across the returned records,
which distinguishes a tenant identity from a display sequence.

**Reasoning requirement**

Infer that the installation number selects an authorization-relevant record set
rather than a cosmetic field, then enumerate the seeded installations to recover
the UUID↔number map, the `svc:aether-reporting` principal, and the existence of
a platform-operator recovery receipt bound to installation 4100.

**Trigger conditions**

Challenge mode; an authenticated `tenant_admin`; the seeded migration records for
installations 4100/4101/4102. No race or external dependency.

**Expected result**

The player reads installation 4100's record, extracts the embedded platform-
operator recovery receipt, and records the reporting principal and the
UUID↔number map. The SHA-256 of the extracted receipt equals the stored
`platform_operator_recovery_receipts.token_hash`, so it is a usable Stage 05
artifact. This stage grants no role and no enrollment; patched mode returns only
the caller's own history and never the foreign receipt.

**Misleading hypotheses**

The installation number may look like a report sequence or chart index; the
player rejects this by observing its stable link to a fixed UUID and principal
across revisions. A stale settings cache may seem responsible; a fresh session
returns the same cross-tenant record, distinguishing the two.

**Verification**

Challenge: an authenticated `tenant_admin` requests installation 4100 and
receives the platform-operator record including a receipt whose hash matches the
stored value; requests 4101/4102 and receives the mapping records. Patched: the
same requests return only the caller's own (empty) history and never a foreign
receipt, while the settings view still returns the caller's own row. Covered by
`scripts/verify-reconstruction.py` (live) and `migrationLookupNumber` resolution
logic (`tenant_test.go`).

**Remediation**

Resolve all migration lookups server-side from the authenticated canonical
tenant UUID; reject caller-supplied installation numbers; keep the settings view
scoped to the caller; audit every migration read with the resolved number.

**Difficulty justification**

The player must connect the settings view, the migration endpoint and the stable
identity relationship to decide the number is an authorization identity, then
enumerate installations to reconstruct the map — no single response explains it.

**Unintended solutions**

The stage must not expose database credentials, the worker signing key, an
unscoped tenant list, or any role/enrollment change. The migration endpoint is
read-only, bounded to seeded installations, and requires `tenant_admin`. Tests
must confirm ordinary operators cannot call it and that it grants no privilege.
