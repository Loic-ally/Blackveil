# BLACK VEIL — attack graph v3 (Stages 09–15)

**Private organizer material. Not a player artifact.**

Design date: **2026-10-30**. This is the Phase A dependency graph and technical
architecture for the advanced half. It builds strictly on the entry state in
[advanced-extension-assessment.md](advanced-extension-assessment.md) §4 and reuses
the extension points in §2. It is a design; implementation status per stage is in
`PROGRESS.md` and each `docs/stages/stage-XX.md`.

## 0. Theme continuity (not a repeat of the unsigned integer)

Stages 01–08 exposed one failure: **numeric identity is trusted where UUID
identity is authenticated.** Stages 09–15 reveal that this is a *symptom* of a
deeper architectural failure: AETHER's migration left **two parallel trust
languages** — the legacy numeric/"trusted-transport" model and the modern
UUID/signed model — and the boundary between them is crossed, re-serialized and
re-interpreted by independent components that never agreed on a canonical
meaning. Each new stage attacks a *different* seam of that boundary (native
compat shim, process confinement, privilege domain, serialization/canon,
cross-service provenance, historical record), not the same unsigned field.

## 1. Dependency graph

```
STAGE 08  agent numeric confusion (operator shell + envelope control)
    |  capability: can drive the agent and read /v1/build metadata
    v
STAGE 09  THE FORGOTTEN BINARY            [reverse engineering]
    |  the agent delegates legacy records to a second native binary, the
    |  "aether-indexer", speaking a binary TLV protocol ("legacy-envelope/0").
    |  A compat-shim parser defect honors an obsolete "trusted-transport" flag.
    |  capability: make the indexer emit a provisioning descriptor that NAMES a
    |  confined helper and its IPC endpoint (a reference, not a secret).
    v
STAGE 10  NAMESPACE LABYRINTH             [linux internals]
    |  the named helper ("provisioner") runs in its own mount + pid namespace
    |  with a distinct service UID. Correlating /proc, UID/GID maps, mount views
    |  and an abstract-namespace socket reveals the legitimate IPC transition.
    |  capability: send requests to the provisioner over the discovered channel.
    v
STAGE 11  FALSE ROOT                       [privilege boundaries]
    |  the provisioner has a controlled design mistake granting root INSIDE its
    |  user namespace / sandbox. Player must prove namespace-root != guest-root
    |  != host. capability: read a sandbox-scoped provisioning artifact (a
    |  signed provenance blob in two serializations).
    v
STAGE 12  THE INTEGRITY PARADOX            [applied cryptography]
    |  the provenance blob is signed over one canonicalization (indexer TLV) but
    |  verified in another context (agent/worker JSON). A field authenticated in
    |  one context means something else in the other. No primitive is broken.
    |  capability: a provenance token that is validly-signed-in-context.
    v
STAGE 13  THE BROKEN TRUST CHAIN           [distributed systems]
    |  requires >=3 components: API historical mapping (web) + worker provenance
    |  record + the Stage 12 token. Chained, they let the player assert a service
    |  identity end-to-end that no single service would accept alone.
    |  capability: obtain the deployment-manifest reference.
    v
STAGE 14  EVERYTHING WAS LOGGED            [digital forensics]
    |  reconstruct the ORIGINAL migration incident from distributed evidence
    |  (API audit, worker records, journald, indexer traces, migration metadata,
    |  signed artifacts) with realistic complexity (worker/guest clock offset,
    |  retries, numeric-vs-UUID representations). Produce a verifiable timeline.
    |  capability: the incident key fields needed to build the final proof.
    v
STAGE 15  THE BLACK VEIL                   [final, multi-disciplinary]
       combine migration understanding + web evidence + RE (09) + linux (10/11)
       + crypto (12) + provenance (13) + timeline (14). A subtle public-site
       clue becomes meaningful only now. Submit a composed proof to an ISOLATED
       organizer validator (separate service/network, holds the key). No file
       read yields the answer.
```

Parallel/branch research is allowed: 09 (RE) and the forensic reading of 14's
evidence can begin early, but each *gate* capability above is required to unlock
the next controlled transition.

## 2. Per-stage architecture (component, root cause, entry, gate, patch, verify)

### Stage 09 — The Forgotten Binary (RE)
- **New component:** `vm/indexer/` Rust binary `aether-indexer`, installed at
  `/usr/local/sbin/aether-indexer`, systemd socket/unit, listening on a local
  endpoint the agent calls for `legacy-envelope/0` records. Custom length-prefixed
  TLV wire format (version, record-type, len, fields, trailer).
- **Root cause (challenge):** a version-compatibility shim: when a record carries
  the legacy `transport=0x01` ("trusted transport") type byte, a bounds check on
  a 16-bit length uses the *declared* length before validating it against the
  buffer, so a crafted record makes the shim treat an attacker-chosen trailer as
  a pre-authenticated origin marker — skipping HMAC. Realistic: the old transport
  was trusted on a private bus; the shim was kept for backward compatibility.
- **Entry:** operator shell + agent `/v1/build` reveals a `legacy-envelope/0`
  fallback; the indexer binary is operator-readable (for RE) but its config/keys
  are not.
- **Gate output:** indexer emits a *provisioning descriptor* naming the
  provisioner service + its IPC endpoint. Not a secret — a reference.
- **Patch:** validate declared length against remaining buffer before use; the
  trusted-transport type is rejected (decommissioned).
- **Verify:** host — Rust `#[test]` vectors for the parser (challenge accepts the
  craft, patched rejects). Guest — player terminal crafts the record and reads
  the descriptor; patched guest refuses.

### Stage 10 — Namespace Labyrinth (Linux internals)
- **New component:** `aether-provisioner` service launched in its own mount + pid
  namespace (systemd `PrivateMounts`, `PrivatePID`-style or an `unshare` wrapper
  available unprivileged in-guest), distinct service UID, communicating over an
  abstract-namespace unix socket.
- **Root cause:** not a vuln — a *discovery* stage. The legitimate transition is
  only findable by correlating: the descriptor (09), `/proc/<pid>/status` UID
  maps, `/proc/<pid>/mountinfo` differences, and the socket in the abstract
  namespace. Isolated inspection of any one is insufficient.
- **Entry:** the Stage 09 descriptor.
- **Gate output:** the player can send well-formed requests to the provisioner.
- **Patch:** patched mode tightens what the descriptor discloses / closes the
  readable correlation, so the transition is not discoverable without the
  intended capability (keeps challenge/patched parity).
- **Verify:** player terminal enumerates `/proc` + mounts + socket and reaches
  the provisioner; patched mode blocks the shortcut.

### Stage 11 — The Privileged Reader (privilege boundaries)
- **New component:** the provisioner accepts a bounded provisioning request; a
  controlled design mistake (trusting a client-supplied value that selects a
  privileged action *within the sandbox user namespace*) yields root **inside the
  provisioner's user namespace** — mapped to an unprivileged UID in the guest.
- **Root cause:** namespace-root confusion: the service equates "root in my
  userns" with "authorized", but the userns root maps to a non-privileged guest
  UID (no host or guest-host capability). Original, not a public CVE.
- **Entry:** provisioner access (10).
- **Gate output:** a sandbox-scoped artifact: a signed provenance blob in two
  serializations. The stage's containment assertion: from namespace-root the
  player still cannot read guest `worker.key`, cannot write outside the sandbox,
  cannot touch the host.
- **Patch:** the service validates the mapped credential, not the namespace UID.
- **Verify:** player terminal gains userns-root and reads the artifact; tests
  assert the containment boundary holds (guest key still unreadable, host
  unreachable) in both modes.

### Stage 12 — The Integrity Paradox (crypto)
- **Mechanism:** the provenance blob is signed by the indexer over its TLV
  canonicalization; the worker/agent verify an equivalent JSON. A field (e.g.
  the origin/service identity) is covered in one canonical form but
  re-interpreted in the other, so a blob valid "as TLV provenance" is accepted as
  a different assertion "as JSON provenance." Established libs only
  (`hmac`/`sha2`, or `ed25519-dalek` for an asymmetric provenance signer).
- **Root cause:** missing domain separation + non-canonical cross-format
  verification. No primitive broken; it is a logical/ canonicalization flaw.
- **Entry:** the Stage 11 artifact.
- **Gate output:** a provenance token validly-signed-in-context the player can
  present to the distributed chain.
- **Patch:** versioned, domain-separated, single-canonical signing; cross-format
  verification rejected.
- **Verify:** deterministic test vectors (host) + player constructs the token;
  patched rejects.

### Stage 13 — The Broken Trust Chain (distributed systems)
- **Mechanism:** the API exposes (from the web side) a historical identity
  mapping; the worker stores a provenance record keyed by numeric identity; the
  agent/indexer accept the Stage 12 token. Only by combining all three can the
  player assert a *service* identity across the boundary (e.g., act as
  `svc:aether-reporting` for a tenant they do not own, end-to-end, producing a
  cross-tenant provenance-bearing artifact).
- **Root cause:** no end-to-end binding of identity across the three hops; each
  trusts its neighbor's partial assertion.
- **Entry:** Stage 12 token + web-side mapping + worker record (>=3 components).
- **Gate output:** a deployment-manifest reference.
- **Patch:** a single bound identity carried and checked at each hop.
- **Verify:** player path touches all three interfaces; patched refuses.

### Stage 14 — Everything Was Logged (forensics)
- **Mechanism:** seeded, deterministic historical evidence of the *original*
  migration incident, spread across API audit events, worker execution records,
  guest journald, indexer traces, migration metadata and signed artifacts.
  Realistic complexity: a fixed worker↔guest clock offset (consistent with the
  120 s window), retries, and numeric-vs-UUID representations of the same actor.
- **Root cause:** not a vuln — a reconstruction task with a machine-checkable
  answer (the ordered incident timeline / the attacker's pivot path identifiers).
- **Entry:** manifest reference (13) points at the evidence set.
- **Gate output:** the incident key fields for the final proof.
- **Patch:** n/a (forensic); "patched mode" = the incident is fully attributable
  (no ambiguity) once correct binding exists, used as the correctness oracle.
- **Verify:** a scorer checks the submitted timeline against the seed.

### Stage 15 — The Black Veil (final)
- **Mechanism:** compose a final proof from: the migration model, a web-side
  clue (a subtle, real artifact already shipped on the public site — e.g. a
  build/meta value — that is only interpretable after Stage 12/14), the RE
  finding, the linux capability, the crypto token, the provenance chain and the
  timeline. Submit to an **isolated validator** service.
- **Validator:** separate Compose service on a dedicated network not reachable
  from the player host; holds the validation key; exposes only a submit endpoint;
  returns pass/fail + which findings were missing. Never shipped in web/api/vm
  images. Organizer brings it up for scoring.
- **Verify:** `scripts/verify-chain.py` (full) composes the proof through the
  player path and submits it; a wrong or partial proof is rejected.

## 3. Isolation review (per the assessment §6)

Every new service joins only internal networks; none publishes a host port. All
new privilege lives inside the guest user namespaces (Stage 11) and is proven not
to cross to guest-host or physical host. The validator is organizer-only. No new
Docker socket, device, host mount or privileged container. Challenge/patched
parity and hard-fail-on-missing-guest are preserved for every stage.

## 4. Build order (Phase B→E) and verification gate

B: 09, 10 · C: 11 · D: 12, 13 · E: 14, 15. A stage is committed only when its
host unit tests run green and (for guest-integrated stages) the player-terminal
path is exercised against a rebuilt guest. Unbuilt stages remain documented, not
stubbed as passing. The chain verifier is extended stage by stage; the full
`make chain-verify` only claims 01–NN for stages actually wired and verified.
