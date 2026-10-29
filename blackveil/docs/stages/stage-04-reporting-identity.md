# Stage 04 — Asynchronous trust investigation (reporting identity)

**Stage ID**

`BV-04-REPORTING-IDENTITY`

**Player objective**

As a workspace administrator, investigate how the asynchronous worker resolves a
tenant's reporting service identity, and enroll your own workspace as the
`svc:aether-reporting` principal using the enrollment evidence recovered in
Stage 03. This opens the worker→agent archive path and establishes the reporting
identity Stage 05 checks.

**Starting knowledge**

`tenant_admin`; the Stage 03 reconstruction (UUID↔installation map, the
`svc:aether-reporting` principal, and the reporting-enrollment receipt embedded
in installation 4101's migration history). The workspace is not archive-enrolled
(`GET /api/v2/tenant` shows `archive_enabled:false`) so `legacy-archive` reports
are refused.

**System components**

AETHER API, the asynchronous worker, `worker_service_identities`, the new
`POST /api/v2/tenant/reporting-identity` endpoint, the `reporting_enrollment_receipts`
table and the `reporting_archive_numbers` sequence (migration 009).

**Technical root cause**

Enrollment validates the reporting receipt and the principal, then records a
`worker_service_identities` row for the caller's tenant. In challenge mode it
does **not** bind the receipt's canonical installation (North Works, 4101) to
the caller's tenant UUID — the Stage 02 unbound-source flaw re-expressed at the
enrollment hop — so an administrator who found North Works' reporting receipt
enrolls their own unmigrated workspace. Patched mode requires the receipt's
canonical tenant to equal the caller and refuses.

The self-enrolled workspace receives an archive number from the dedicated
`reporting_archive_numbers` sequence (≥ 500000), which can never collide with a
tenant's own `legacy_tenant_no` (4100+) or the seeded archive ids (4101/4102)
and has no archive file in the guest. The legitimate `legacy-archive` report
therefore resolves an empty archive; reading a real foreign archive still
requires the Stage 08 agent substitution.

**Realistic origin**

Reporting enrollment was a self-service migration step keyed on an installation
receipt. The step predates the UUID identity model and never gained the binding
that ties the receipt's installation to the workspace redeeming it.

**Required observations**

Two independent signals: the `legacy-archive` report is refused before enrollment
and accepted after (`archive_enabled` flips in `GET /api/v2/tenant` and
`GET /api/me`); and the enrollment audit records a foreign `source_tenant_uuid`
(North Works) against the caller's own `tenant_uuid`.

**Reasoning requirement**

Infer that the worker derives a tenant's reporting identity from a per-tenant
enrollment row, then test whether a foreign installation's receipt can create
that row for your own workspace while preserving your UUID.

**Trigger conditions**

Challenge mode; `tenant_admin`; the reporting-enrollment receipt for installation
4101 reconstructed in Stage 03; the caller's workspace not yet enrolled.

**Expected result**

Challenge mode enrolls the caller's workspace as `svc:aether-reporting`, makes
`legacy-archive` queueable, and records the cross-installation provenance in
audit. Enrollment is single-use per workspace (second attempt → 409). The stage
grants no role; the terminal remains denied. Patched mode refuses a foreign
installation receipt (403) and never enrolls the caller.

**Misleading hypotheses**

The archive number may look like a tenant id; the player distinguishes it by its
distinct high range and the empty archive it resolves. The empty `legacy-archive`
result may look like failure of the whole path; the player confirms the path is
open (report accepted, worker runs) and that only the archive content is absent.

**Verification**

`scripts/verify-chain.py` (challenge): signup → 01 → 02 → 03 → 04, asserting
pre-enrollment refusal, invalid-receipt/wrong-installation boundaries, successful
enrollment, `archive_enabled` flip, `legacy-archive` queueability, single-use
409, terminal still denied, provenance audit, and secret not copied. Patched:
foreign-receipt enrollment refused. Pure binding logic in
`enrollmentBindingOK` (`reporting_test.go`).

**Remediation**

Bind the receipt's canonical installation to the authenticated tenant before
creating the reporting identity; derive the archive number server-side; keep
per-workspace single-use enrollment and audit the canonical decision.

**Difficulty justification**

The player must connect the worker's per-tenant identity resolution, the Stage 03
enrollment evidence, and the before/after behavior of `legacy-archive` to decide
the receipt is an unbound authorization artifact.

**Unintended solutions**

Enrollment must not grant a role, accept a caller-supplied archive number, reuse
a seeded archive id, or enable reading another tenant's archive content (that
requires Stage 08). Tests confirm ordinary operators cannot enroll, the terminal
stays denied, and the archive slot is empty.
