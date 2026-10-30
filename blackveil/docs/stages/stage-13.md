# Stage 13 — The Broken Trust Chain

**Stage ID**

`BV-13-BROKEN-TRUST-CHAIN`

**Domain**

Distributed-systems security (cross-service identity binding).

**Player objective**

Assemble a deployment manifest for a tenant the player does not own by correlating
three facts, each from a different component, that are individually valid but
jointly unbound. The manifest reference opens the Stage 14 forensic evidence set.

**Starting knowledge (entry condition)**

- The worker-originated `job_id` from the Stage 07 retained capture.
- The forged provenance token from Stage 12 (JSON identity = Harbor, signed TLV =
  North Works, accepted by the challenge agent).
- The API migration mapping (Stage 03): Harbor's `tenant_uuid` ↔ `4102`.

**System components (three tiers)**

- **Worker:** produced the retained archive request (its `job_id`).
- **Agent:** `POST /v1/manifest` (`manifest_decision` in `vm/agent/src/main.rs`),
  which also re-verifies the provenance token.
- **Application API:** the migration mapping the player reads in Stage 03.

**Root cause (precise)**

`manifest_decision` (challenge) checks each fact in isolation — the job reference
is well-formed, the provenance signature verifies, and the supplied mapping is
internally consistent with the agent's tenant map — and requires the mapping to
match the provenance's *asserted* (JSON) identity. It never binds that identity to
the *signed* TLV, nor to the caller's own tenant. So a North-signed token carrying
a Harbor JSON identity, plus a Harbor mapping and any valid worker job reference,
assembles a Harbor manifest. Each service trusts its neighbour's partial
assertion; no one checks the whole chain.

**Realistic origin**

The manifest assembler was built to "stitch together" provenance, the historical
mapping and the originating job for audit. Each input was already validated by its
own service, so the assembler trusted them and only checked that they referred to
the same tenant *as asserted* — assuming the asserted identity equalled the signed
one, which Stage 12 shows it need not.

**Player-discoverable clues**

1. The Stage 12 provenance reply advertises the next step; the agent exposes
   `POST /v1/manifest`.
2. The manifest request shape (provenance, mapping, job_ref) is in the agent
   binary.
3. A manifest attempt with uncorrelated facts returns `trust chain broken`,
   showing the assembler checks agreement between the facts (but not the TLV).

**Reproducible intended solution**

1. Collect the three facts (job_id, forged token, Harbor mapping).
2. `POST /v1/manifest` with them → `deploy-4102` for Harbor, `next:
   everything-was-logged`, and the evidence path.
3. Confirm no single fact suffices: a mismatched mapping yields `trust chain
   broken`.

**Patched implementation**

`manifest_decision` (patched) resolves the provenance against the signed TLV
(`resolve_provenance` patched), so the forged cross-tenant token is rejected
(`provenance field mismatch`) before any manifest is assembled; a genuine token
only yields its own signed identity's manifest.

**Automated challenge-mode tests**

Host (`vm/agent` `cargo test`): `challenge_manifest_crosses_tenants`,
`challenge_manifest_requires_correlated_mapping`,
`manifest_rejects_unknown_mapping_and_bad_job`. Live (`scripts/verify-chain.py`,
player terminal): assemble the cross-tenant manifest from the three facts, and
confirm an uncorrelated mapping breaks the chain.

**Automated patched-mode tests**

Host: `patched_manifest_refuses_forged_identity`. Live: an organizer assertion
against the patched guest confirms the forged token is refused.

**Unintended-path analysis**

- The manifest requires a valid provenance signature (cannot be fabricated without
  the provenance key) and a mapping consistent with the agent's tenant map (cannot
  be invented), so the only leverage is the Stage 12 signed-vs-asserted gap applied
  across the three facts.
- A single component in isolation is insufficient: the token alone is not a
  manifest; the mapping alone grants nothing; the job reference is only a
  well-formedness check.

**Progressive hint structure**

1. "The provenance step pointed somewhere. What else does the agent accept?"
2. "The manifest wants three things from three places. Where did each come from?"
3. "The facts must agree with each other — but with what do they *not* have to
   agree?"

**Organizer documentation**

Design in `organizer/attack-graph-v3.md` §2 (Stage 13). Additive agent endpoint;
Stage 08 archive path unchanged. The manifest references, but does not contain,
the Stage 14 evidence set. No new network exposure.
