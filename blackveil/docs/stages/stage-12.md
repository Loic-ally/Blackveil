# Stage 12 — The Integrity Paradox

**Stage ID**

`BV-12-INTEGRITY-PARADOX`

**Domain**

Applied cryptography (serialization / canonicalization / verification context).

**Player objective**

Analyze the provenance blob extracted in Stage 11. It is HMAC-signed over a
canonical TLV, but the agent's provenance verifier trusts the blob's JSON fields
rather than the signed TLV. Produce a provenance token whose JSON identity differs
from the signed TLV yet is accepted as "verified" — the Stage 13 input. No
cryptographic primitive is broken.

**Starting knowledge (entry condition)**

The Stage 11 provenance blob: `{format, service, tenant_uuid, legacy_tenant_no,
issued_at, tlv (hex of the canonical form), sig (HMAC over the TLV)}`, and the
discovery that the agent exposes `POST /v1/provenance`.

**System components**

- The agent endpoint `POST /v1/provenance` (`provenance_decision` in
  `vm/agent/src/main.rs`), added additively alongside the Stage 08 archive path.
- The provenance key: `HMAC(worker_key, "aether-provenance/v0")`, derived by both
  the agent and `render-cloud-init.py`; the operator never sees it.
- The canonical TLV (`AEP\0` + tag/len/value records) vs the JSON representation.

**Root cause (precise)**

`provenance_decision` (challenge) verifies `HMAC(prov_key, tlv) == sig` — a correct
signature check — but then reports the identity from the blob's **JSON** fields
(`service`, `tenant_uuid`, `legacy_tenant_no`), which are not covered by the
signature. The signed bytes (TLV) and the consumed bytes (JSON) are two different
representations with no binding between them. An attacker edits the JSON while
leaving `tlv`/`sig` intact, and the verifier trusts the edit.

**Realistic origin**

The provenance format gained a convenient JSON mirror of the canonical TLV "so
callers don't have to parse the binary". The verifier was updated to read the
easy JSON fields but kept verifying the original TLV signature, assuming the two
always agree.

**Player-discoverable clues**

1. The blob carries both a `tlv` and redundant JSON fields — two representations.
2. `sig` verifies against the TLV, not the JSON (visible in the agent binary).
3. Posting the unmodified blob returns `source: "json"`, signalling which
   representation the verifier actually reports.

**Reproducible intended solution**

1. POST the genuine blob to `/v1/provenance` → `verified: true`, identity 4101 /
   North Works, `source: "json"`.
2. Edit the JSON (`legacy_tenant_no` → 4102, `tenant_uuid` → Harbor) but keep
   `tlv` and `sig`.
3. POST again → `verified: true` with the edited identity. This token (edited JSON
   + original signature) is the Stage 13 input.

**Patched implementation**

`provenance_decision` (patched) parses the verified TLV, derives the authoritative
identity from it, and rejects any blob whose JSON disagrees
(`provenance field mismatch`); the reported `source` is `"tlv"`.

**Automated challenge-mode tests**

Host (`vm/agent` `cargo test`): `genuine_blob_verifies_in_both_modes`,
`challenge_trusts_edited_json_identity`, `forged_signature_rejected`. Live
(`scripts/verify-chain.py`, player terminal): the genuine blob verifies, and an
edited-JSON blob with the original signature is accepted with the edited identity.

**Automated patched-mode tests**

Host: `patched_binds_identity_to_signed_tlv`. Live: an organizer assertion against
the patched guest confirms the edited-JSON blob is a field mismatch.

**Unintended-path analysis**

- The signature check is a real HMAC verification; the player cannot forge a blob
  with an invalid signature (`forged_signature_rejected`), nor recover the
  provenance key (not operator-readable). The only leverage is the TLV↔JSON gap.
- The TLV itself is length-delimited, so there is no canonicalization-ambiguity
  collision within the TLV; the flaw is strictly the signed-vs-consumed mismatch.
- Editing `issued_at` or `tlv` is pointless: `tlv` is what is signed, and the
  identity fields consumed are the JSON ones.

**Progressive hint structure**

1. "The blob says the same thing twice. Which copy is signed?"
2. "Post it unchanged — what does `source` tell you?"
3. "Change the JSON, keep the signature. What does the verifier report now?"

**Organizer documentation**

Design in `organizer/attack-graph-v3.md` §2 (Stage 12). The endpoint is additive;
the Stage 08 archive path is byte-for-byte unchanged (the full chain re-verifies
Stage 08 each run). The provenance key stays root-derived and is never exposed.
