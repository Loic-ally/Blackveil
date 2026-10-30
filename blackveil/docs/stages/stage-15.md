# Stage 15 — The Black Veil

**Stage ID**

`BV-15-THE-BLACK-VEIL`

**Domain**

Final, multi-disciplinary synthesis + isolated proof validation.

**Player objective**

Assemble a single final proof from discoveries spanning both halves of the
challenge and submit it to the organizer's isolated validator, which mints the
BLACK VEIL flag only for a complete, correct proof.

**Starting knowledge (entry condition)**

- The incident attestation from Stage 14.
- The cross-tenant deployment manifest from Stage 13 (`deploy-4102`, Harbor).
- The understanding, from Stages 12 and 14, that the trust model binds identity to
  a *domain label* — which the public site exposes.

**The website clue**

The public landing page carries a cosmetic-looking build marker,
`<meta name="aether-migration-channel" content="veil/v0">` (set in
`web/app/layout.tsx`). Only after Stage 12 (domain-separated signing) and Stage 14
does its role become clear: `veil/v0` is the domain label the final proof is bound
to. It cannot be guessed as relevant without the later investigation, and the proof
is incomplete without it.

**System components**

- The public web app (the clue).
- The agent endpoints that produced the attestation (Stage 14) and the manifest
  identity (Stage 13).
- `aether-validator` (`organizer/validator/validate.py`): an isolated organizer
  service on a dedicated internal network (`validator`), with **no host port**,
  holding the deployment key. Its code is mounted read-only from `organizer/`, so
  it is never baked into any player image.

**Root cause / final synthesis**

No single artifact is the flag. The validator recomputes, from the deployment key,
the expected incident attestation, the cross-tenant manifest/pivot, the Harbor
identity and the published veil tag, and mints the flag only when the submitted
bundle matches all of them. The proof therefore *is* the chain: native RE (09),
Linux internals (10), privilege boundaries (11), the integrity paradox (12),
distributed trust (13), and the forensic reconstruction (14), tied to the public
identity clue (15).

**Reproducible intended solution**

1. Gather the incident attestation (14), the manifest/pivot identity (13), and the
   `veil/v0` tag from the public site.
2. Submit `{attestation, veil_tag, manifest, pivot_number, tenant_uuid}` to the
   validator.
3. The validator returns the flag `BV{…}` on a complete proof, or the list of
   missing/wrong elements otherwise.

**Validator isolation (organizer-controlled)**

- Separate Compose service under the `validator` profile; dedicated internal
  network; no host-published port.
- Holds `AETHER_AGENT_KEY`; the flag is derived from it, so only the validator can
  mint it. The key and the validator code never enter `web`, `api`, or `vm` images.
- Submission is organizer-mediated (the score is taken inside the validator's own
  network), matching "isolated from player-controlled infrastructure".

**Automated tests**

Host (`organizer/validator`): the validator's `evaluate` self-checks (expected
bundle → flag; missing field → reported). Live (`scripts/verify-chain.py`): read
the site clue, bring up the validator, submit an incomplete proof (rejected with
`missing`) and the full proof (flag minted). Part of `make chain-verify`
(Stages 01–15, exit 0).

**Unintended-path analysis**

- The flag is an HMAC over the deployment key; it cannot be computed by the player
  or read from any image — only minted by the validator for a correct proof.
- Each bundle element is checked against key-derived truth, so a partial or guessed
  proof fails and names what is missing (no brute-force oracle: the attestation and
  manifest already required the full chain).
- The validator has no host port and holds the only copy of the flag secret, so it
  cannot be reached or extracted from player infrastructure.

**Progressive hint structure**

1. "The incident step said `the-black-veil`. What proof would a validator want?"
2. "Three things from three stages — plus one more that's been in plain sight."
3. "The site's build marker isn't cosmetic once you know what signs the trust."

**Organizer documentation**

Design in `organizer/attack-graph-v3.md` §2 (Stage 15) and
`organizer/final-proof-design.md`. The validator is private organizer
infrastructure; never expose it to players.
