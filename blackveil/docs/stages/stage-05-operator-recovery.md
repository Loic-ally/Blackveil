# Stage 05 — Service boundary analysis (operator recovery)

**Stage ID**

`BV-05-OPERATOR-RECOVERY`

**Player objective**

Combine the evidence from Stages 03 and 04 to recover the platform-operator
identity and elevate to `system_admin`, the identity the Linux lab terminal
requires. Progress requires reasoning about the relationship between the
platform-operator installation, the reporting principal and the destination
workspace — not guessing an endpoint.

**Starting knowledge**

`tenant_admin`; the platform-operator recovery receipt for installation 4100
reconstructed in Stage 03; and the `svc:aether-reporting` reporting identity
enrolled in Stage 04 (`archive_enabled:true`).

**System components**

AETHER API, `POST /api/v2/lab/operator-recovery`, the
`platform_operator_recovery_receipts` table (migration 008), the
`platform_operator_recovery_redemptions` ledger (migration 010),
`worker_service_identities`, the `users.role` model and the terminal gate.

**Technical root cause**

Operator recovery requires two independently-earned artifacts — the Stage 03
platform-operator receipt and the Stage 04 reporting enrollment — then elevates
the caller to `system_admin`. In challenge mode it does **not** bind the
receipt's canonical tenant (North Works, installation 4100) to the destination
workspace: the Stage 02 administrator-recovery flaw lifted one authority level.
Patched mode requires the installation receipt, principal and destination UUID
to agree and refuses a foreign/platform receipt.

This is deliberately not "tenant_admin == system_admin": elevation is gated on
two discovered artifacts, is tracked single-use per account, promotes only a
`tenant_admin` (not an operator), and is a role grant — never a credential,
service key or guest access.

**Realistic origin**

The organization that operated the shared lab during migration held a
platform-operator recovery receipt bound to its installation number and
reporting principal. The UUID binding that the modern role model needs was never
added to that recovery path.

**Required observations**

Two independent signals: operator recovery is refused for a `tenant_admin` that
has not enrolled the reporting identity (Stage 04 is a genuine prerequisite), and
the recovery audit records a foreign `source_tenant_uuid` (North Works) against
the caller's own `tenant_uuid` with `role:system_admin`. The terminal gate
flips from 403 (denied) to reachable only after elevation.

**Reasoning requirement**

Infer that the platform-operator authority is reconstructed from an installation
receipt plus a reporting identity rather than bound to the authenticated
workspace, then test whether presenting the foreign installation's receipt from
an enrolled workspace yields `system_admin`.

**Trigger conditions**

Challenge mode; `tenant_admin`; reporting identity enrolled (Stage 04); the
platform-operator receipt for installation 4100 reconstructed (Stage 03).

**Expected result**

Challenge mode elevates the caller to `system_admin` exactly once and the
terminal authorization gate stops returning 403. Patched mode refuses the
foreign receipt (403) and never elevates. The stage grants no credential, key or
guest access; it changes one account's role.

**Misleading hypotheses**

The receipt may look like a password or service key; the player distinguishes it
by its single-use, per-account, role-only effect and the audit provenance. The
terminal's 403 may look like a missing feature; after elevation the same request
no longer returns 403, showing the gate is identity-based.

**Verification**

`scripts/verify-chain.py` (challenge): ordinary operators refused; a
tenant_admin without enrollment refused (Stage 04 prerequisite); invalid-receipt
and wrong-installation boundaries; successful single-use elevation to
`system_admin`; terminal gate flips from 403; provenance audit; secret not
copied. Patched: foreign-receipt elevation refused. Pure binding logic in
`sourceBindingOK` (`reporting_test.go`).

**Remediation**

Bind the platform-operator receipt's installation, principal and destination
UUID before elevating; keep single-use per-account redemption, the
`tenant_admin`-only promotion guard and full provenance audit; never issue a
durable credential.

**Difficulty justification**

The player must combine two separately-earned artifacts and reason about the
boundary between the reporting service identity and the platform-operator role —
neither artifact alone elevates, and the binding failure is only visible by
comparing the recovery audit's source and destination.

**Unintended solutions**

Elevation must not be reachable from an ordinary operator, an unenrolled
workspace, a caller-supplied role field, or a replayed redemption; it must not
grant a credential, service key, guest shell or tenant reassignment. The terminal
remains gated on `system_admin` so challenge completion, not signup, opens it.
