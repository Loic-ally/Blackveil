# Stage 02 — Administrator recovery

**Stage ID:** `BV-02-ADMINISTRATOR-RECOVERY`

**Objective:** Recover workspace administrator membership from an ordinary
operator account by following the historical migration evidence from Stage 01.

**Starting knowledge:** The public application, API documentation, the caller's
UUID and a historical CSV. No organizer database changes or privileged account
are prerequisites.

**Product workflow:** Migrated installation administrators retained a recovery
receipt in their handover archive. The team page lets an authenticated user
present that receipt and the installation reference to restore administration
in the current workspace. Receipts are random per database initialization; they
are not passwords, service keys or invitations. They authorize only tenant_admin.

**Root cause:** Challenge mode verifies the caller's UUID and validates the
receipt against the numeric installation, but omits the binding between the
receipt's canonical tenant UUID and the current workspace. Patched mode requires
all three identities to agree before recording redemption or changing the role.

**Evidence:** The archive identifies its original tenant UUID and contains a
handover receipt. The team page and API schema describe recovery into the active
workspace. The recovery audit records the source and destination UUIDs. Players
must connect Stage 01's cross-tenant read to the separate recovery decision.

**Expected result:** A player submits their own UUID, installation 4101 and its
archived receipt to POST /api/v2/team/recover. Challenge mode promotes only that
player, in their existing workspace, to tenant_admin. Auth resolves the updated
role on the next request. The player can then use the ordinary team workflow.
Patched mode denies a foreign receipt, including one obtained before patching,
and still accepts a legitimate same-tenant receipt.

**Replay and multiplayer:** Each user may redeem a given receipt once; a
demoted user cannot reuse it. Redemption and promotion are one transaction.
Receipts are not globally consumed, allowing independent player workspaces.

**Verification:** Fresh signup → historical CSV → receipt extraction → recovery
→ team access, with no organizer role grants. Check invalid receipt, wrong
installation, foreign destination UUID, unknown role fields, replay, audit
provenance and terminal denial. Test patched rejection of a known foreign
receipt and successful canonical recovery with an organizer fixture.

**Remediation:** Bind source receipt, installation and destination tenant before
granting any authority; retain atomic per-user redemption and fixed role scope.

**Boundaries:** No tenant reassignment, system_admin grant, guest access or
service credentials. Receipt tables are readable only by the API; the legacy
service reads the bounded archived copy through its existing private route.
The migration and this specification are outside the web build context.
