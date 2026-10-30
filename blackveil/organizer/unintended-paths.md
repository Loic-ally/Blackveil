# BLACK VEIL — unintended paths (Stages 09–15)

**Private organizer material. Not a player artifact.** Consolidated bypass analysis
and the structural mitigation for each. Per-stage detail is in each
`docs/stages/stage-XX.md`.

## Guest-wide containment (applies to 09–14)
- The `operator` account is uid 1000, no sudo, locked; it cannot read
  `/etc/aether-agent/*` or `/etc/aether-provisioner/ticket` or the confined store
  (verified live in `scripts/verify-chain.py` and the isolation audit).
- All new services bind guest loopback or an abstract unix socket only; none
  publishes a host port (`scripts/check-network.sh`). No new privileged container,
  device, Docker socket, or host mount.
- All new secrets are root-derived from `AETHER_AGENT_KEY`; none is world-readable.

## Stage 09
- **Forge a modern signed record:** blocked — the transport key is not
  operator-readable; only the keyless legacy path is open.
- **Memory-corruption via the length field:** not possible — Rust bounds-checks;
  an over-declared length is a clean `Short` error, not a disclosure. The defect is
  a *logic* bypass by design.
- **Resolve for an arbitrary tenant to skip ahead:** the descriptor is a reference
  only; it grants nothing without Stage 10.

## Stage 10
- **Blind connect to the socket:** rejected without the boot epoch.
- **Map the socket to its PID via `/proc/<pid>/fd`:** owner-only; the intended path
  uses only world-readable `/proc` data.
- **Read the patched ticket:** not operator-readable, so the challenge correlation
  cannot be reused against a patched deployment.

## Stage 11
- **Read the store directly:** denied (`0750`/`0640`, `root:aether-prov`).
- **Traverse to a guest-root secret:** denied; the deputy is `aether-prov`, bounded
  by Linux ownership (not by the service, so the bound holds despite the flaw).
- **Path disclosure via differential errors:** the deputy returns only the error
  *kind*, never the resolved path.

## Stage 12
- **Forge/alter the signature or TLV:** HMAC verification is real; the key is
  unavailable. The only leverage is the signed-vs-consumed gap.
- **Canonicalization collision inside the TLV:** the TLV is length-delimited, so no
  ambiguity collision exists; the flaw is strictly TLV↔JSON.

## Stage 13
- **Invent a mapping or job:** the mapping must match the agent's tenant map; the
  job must be well-formed; the provenance must carry a valid signature. Single-
  service analysis is insufficient by construction.
- **Reuse the Stage 08 numeric trick:** the manifest checks mapping↔asserted-
  identity agreement; the real leverage is the Stage 12 gap applied across tiers.

## Stage 14
- **Guess the pivot without the offset:** all three fields (offset, job, number)
  are checked; the attestation is an HMAC, unforgeable without the key.
- **Naive timeline (raw sort / last-wins):** defeated by the clock offset and the
  retry.

## Stage 15
- **Find a flag on disk / in an image:** none exists; the flag is key-derived and
  minted only by the isolated validator.
- **Reach or extract the validator:** it has no host port, runs on a dedicated
  internal network, and its code/key never enter a player image.
- **Submit a partial proof repeatedly as an oracle:** each element already requires
  the full chain to obtain; the `missing` feedback does not leak the secret.

## Residual (accepted) items
- The patched-agent replay cache is process-local (documented in
  `vm/agent/README.md`); the operator cannot restart the agent.
- Cross-arch/KVM matrices and image CVE scanning remain open (see
  `remaining-risks.md`); these are environment, not stage-logic, gaps.
