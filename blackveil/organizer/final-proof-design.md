# BLACK VEIL — final proof design (Stage 15)

**Private organizer material. Not a player artifact.**

## Isolation model

- `aether-validator` runs under the `validator` Compose profile on a dedicated
  internal network (`<project>_validator_internal`), with **no host-published
  port**. Ordinary `make up` does not start it.
- Its code lives in `organizer/validator/validate.py`, mounted read-only. It is
  never in the `web`, `api`, or `vm` build contexts (confirmed: those contexts do
  not include `organizer/`, and `vm/.dockerignore` excludes it), so it is never
  baked into a player image.
- It holds `AETHER_AGENT_KEY` and is the only component that derives the flag.
- Scoring is organizer-mediated: the proof is submitted from inside the
  validator's own network (the verifier execs into the container), never from a
  player-reachable surface.

## Proof bundle and checks

The player submits:

| Field | Source stage | Validator check |
|---|---|---|
| `attestation` | 14 (agent `/v1/incident`) | `HMAC(incident_seed, "incident-attestation/v0"‖pivot_job)` |
| `veil_tag` | 15 (public site meta) | equals `veil/v0` |
| `manifest` | 13 (agent `/v1/manifest`) | equals `deploy-4102` |
| `pivot_number` | 13/14 | equals `4102` (Harbor) |
| `tenant_uuid` | 03/13 | equals Harbor UUID |

where `incident_seed = HMAC(AETHER_AGENT_KEY, "aether-incident/v0")` and
`pivot_job = "mig-" + incident_seed.hex()[:8]` — identical to the agent scorer and
`render-cloud-init.py`, so the attestation the player legitimately obtained in
Stage 14 matches.

On a complete, correct bundle the validator returns
`BV{ HMAC(AETHER_AGENT_KEY, "black-veil-flag/v0")[:24] }`. Otherwise it returns
`{black_veil:false, missing:[…]}` naming the failed elements (progressive
feedback, not an oracle: the attestation and manifest already require the whole
chain to obtain).

## Why each half is required

- Web half (01–05) → `system_admin` and the migration/mapping knowledge (Harbor
  ↔ 4102) used in the manifest and bundle.
- Linux/native half (06–11) → the operator shell, the forgotten-binary bypass, the
  provisioner handshake, and the privileged-reader extraction of the provenance blob.
- Crypto/distributed/forensic half (12–14) → the integrity-paradox token, the
  cross-tenant manifest, and the incident attestation.
- Stage 15 ties them to the public identity clue and gates the flag behind the
  isolated validator.

## Regeneration / reset

All derived values key off `AETHER_AGENT_KEY`, so a fresh `.env` (via `make
setup`) yields a new flag and new seeds; `make reset` / `make vm-reset` regenerate
the guest-side material. The validator recomputes from the same key, so the chain
stays consistent after reprovisioning. `scripts/reset.sh` tears down the
`validator` profile too.

## Verification

`scripts/verify-chain.py` (full scope) performs the real submission: it reads the
site clue, brings up the validator (`--profile validator --wait`), submits an
incomplete proof (expects `missing`), then the full proof (expects `BV{…}`). This
runs as the final step of `make chain-verify` (Stages 01–15).
