# BLACK VEIL — difficulty analysis (Stages 09–15)

**Private organizer material. Not a player artifact.** Difficulty here is
*discoverable technical depth*, never guessing, brute force, or waiting. The
estimates are design intent; a real rating needs the blind playtest in
`playtest-plan.md` (not yet performed — see that file).

Per stage: knowledge domains · independent observations required · core reasoning ·
likely shortcuts (and why they fail) · typical wrong hypotheses · evidence quality
· proof of completion.

## Stage 09 — The Forgotten Binary
- **Domains:** ELF/binary RE, custom wire protocols, HMAC basics.
- **Observations:** build metadata; the `:9090` socket; the binary's parse logic;
  the behavioural diff (signed path rejects, legacy path accepts).
- **Reasoning:** reconstruct an undocumented TLV; spot that the legacy compat path
  trusts a client marker and skips the MAC.
- **Shortcuts:** `strings` alone → no (marker/semantics are in code, not strings).
- **Wrong hypotheses:** "need the signing key" (no — legacy path needs none).
- **Evidence quality:** deterministic; binary is the ground truth.
- **Proof:** the provisioning descriptor returned by the crafted record.

## Stage 10 — Namespace Labyrinth
- **Domains:** Linux procfs, namespaces, abstract unix sockets.
- **Observations:** descriptor; `/proc/net/unix`; `boot_id`; mountinfo diff.
- **Reasoning:** correlate three world-readable facts; a single one is insufficient.
- **Shortcuts:** connect blindly → rejected without the boot epoch.
- **Wrong hypotheses:** "read the service's files via `/proc/<pid>/root`" (owner-
  only).
- **Evidence quality:** deterministic per boot.
- **Proof:** a successful `describe` handshake.

## Stage 11 — The Privileged Reader
- **Domains:** privilege boundaries, path confinement, Linux ownership.
- **Observations:** the `provision` op; the store path; the benign vs traversal
  behaviour; the denied guest-root read.
- **Reasoning:** the deputy's read power is real but bounded to `aether-prov`;
  namespace/service root ≠ guest root.
- **Shortcuts:** read the store directly → denied (0750/0640).
- **Wrong hypotheses:** "I have root, I can read `worker.key`" (no — bounded).
- **Evidence quality:** deterministic.
- **Proof:** the extracted provenance blob + a bounded denial.

## Stage 12 — The Integrity Paradox
- **Domains:** applied crypto, serialization/canonicalization.
- **Observations:** the blob's two representations; `sig` verifies the TLV;
  `source:"json"` on an unmodified post.
- **Reasoning:** the signed bytes and the consumed fields differ; edit JSON, keep
  the signature.
- **Shortcuts:** forge a signature → no (HMAC; key unavailable).
- **Wrong hypotheses:** "break the MAC" / "edit the TLV" (pointless).
- **Evidence quality:** deterministic test vectors in-code.
- **Proof:** a token accepted with an edited identity.

## Stage 13 — The Broken Trust Chain
- **Domains:** distributed-systems trust, service identity.
- **Observations:** worker job ref; agent-verified token; API mapping — three
  tiers.
- **Reasoning:** each service trusts a partial assertion; nothing binds the whole;
  combine them for a cross-tenant manifest.
- **Shortcuts:** single-service analysis → insufficient by construction.
- **Wrong hypotheses:** "just change a number again" (the manifest checks mapping
  consistency; the leverage is the signed-vs-asserted gap).
- **Evidence quality:** deterministic.
- **Proof:** the cross-tenant `deploy-4102` manifest.

## Stage 14 — Everything Was Logged
- **Domains:** digital forensics, timeline reconstruction.
- **Observations:** three evidence sources; the heartbeat anchor; the retry; the
  foreign `resolved_no`.
- **Reasoning:** correct the clock offset, dedupe the retry, attribute the pivot.
- **Shortcuts:** sort by raw timestamp → wrong (clock offset); last-event-wins →
  wrong (retry).
- **Wrong hypotheses:** "the logs contradict" (they reconcile after the offset).
- **Evidence quality:** deterministic, seeded from the key.
- **Proof:** the scorer-issued incident attestation.

## Stage 15 — The Black Veil
- **Domains:** synthesis across all of the above.
- **Observations:** the incident attestation; the manifest identity; the public
  site clue.
- **Reasoning:** the proof *is* the chain; the public build marker is the domain
  label.
- **Shortcuts:** read a flag file → none exists; the flag is minted only by the
  isolated validator.
- **Wrong hypotheses:** "the flag is somewhere on disk" (it is key-derived in the
  validator).
- **Evidence quality:** deterministic; validator is the oracle.
- **Proof:** `BV{…}` from the validator.

## Overall shape
The first half (01–05) is web authorization reasoning; the native half (06–11)
demands Linux and RE depth; the synthesis half (12–15) demands crypto, distributed
reasoning and forensics, tied back to a web clue. Each gate requires a concrete
capability from the prior stage, so progress is earned, not guessed. A calibrated
time estimate is deferred to the blind playtest.
