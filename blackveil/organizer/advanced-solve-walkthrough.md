# BLACK VEIL — advanced solve walkthrough (Stages 09–15)

**Private organizer material. Not a player artifact.** For the 01–08 solve see
`docs/WALKTHROUGH.md`; this continues from the Stage 08 end state (operator shell
in the guest, able to drive the agent). Every step uses only player-reachable
interfaces; the live equivalent is `scripts/verify-chain.py`.

## Stage 09 — The Forgotten Binary
1. `GET http://127.0.0.1:8080/v1/build` and read `/var/lib/aether-migration/README`:
   a `legacy-envelope/0` indexer listens on `127.0.0.1:9090`.
2. Confirm the socket: `ss -ltn` / `grep 9090 /proc/net/tcp`.
3. Reverse `/usr/local/sbin/aether-indexer` (world-readable): recover the record
   format (`AEI\0`, version, rec_type, u16 length, payload, HMAC trailer) and that
   the legacy `version=0x00, rec_type=0x01` path trusts a trailing `0xA7` marker
   and skips the HMAC.
4. Send a crafted record `AEI\0`+`00 01`+len+`<uuid>`+`A7` to `:9090`; receive the
   provisioning descriptor naming `aether-provisioner` + `@aether-prov`.

## Stage 10 — Namespace Labyrinth
1. From the descriptor, look for the provisioner. `cat /proc/net/unix` → find
   `@aether-prov.<boot8>`.
2. `cat /proc/sys/kernel/random/boot_id` → `<boot8>` (first 8 hex, dashes removed).
3. Compare `/proc/self/mountinfo` with the service's to confirm the private mount
   namespace (confinement signal).
4. Connect to the abstract socket and send
   `{"op":"describe","epoch":"<boot8>"}` → the describe reply with `next:
   false-root`.

## Stage 11 — False Root
1. `{"op":"provision","epoch":"<boot8>","arg":"default.tmpl"}` → the deputy renders
   a store template (confirms it reads as its own identity).
2. `arg":"../provenance.blob"` → the deputy escapes the store and returns the
   provenance blob. Save it.
3. `arg":"../../../etc/aether-agent/worker.key"` → `render failed`: the elevation
   is bounded to `aether-prov`, not guest root.

## Stage 12 — The Integrity Paradox
1. POST the blob to `http://127.0.0.1:8080/v1/provenance` → `verified`, `source:
   "json"`.
2. Edit the JSON identity (`legacy_tenant_no`→4102, `tenant_uuid`→Harbor), keep
   `tlv`+`sig`.
3. POST again → accepted with the edited identity. Keep this token.

## Stage 13 — The Broken Trust Chain
1. Gather three facts: the worker `job_id` from the Stage 07 capture; the forged
   token (12); Harbor's `uuid`↔`4102` mapping (read the Stage 03 migration for
   4102).
2. POST `{"provenance":<forged>,"mapping":{...Harbor},"job_ref":"<job_id>"}` to
   `/v1/manifest` → `deploy-4102` for Harbor, `next: everything-was-logged`,
   `evidence: /var/lib/aether-migration/incident`.

## Stage 14 — Everything Was Logged
1. Read the evidence set. `NOTES` points at the `hb-0` heartbeat.
2. `offset = gts(hb-0 in agent-trace) − ts(hb-0 in worker.jsonl)`.
3. Collapse the retry; find the agent trace whose `resolved_no` (4102) differs from
   the actor's own (4101) → `pivot_job`.
4. POST `{"offset":…,"pivot_job":…,"pivot_number":4102}` to `/v1/incident` → the
   incident attestation, `next: the-black-veil`.

## Stage 15 — The Black Veil
1. On the public site, read `<meta name="aether-migration-channel"
   content="veil/v0">`. After Stages 12/14 you recognize `veil/v0` as the proof's
   domain label.
2. Submit `{attestation, veil_tag:"veil/v0", manifest:"deploy-4102",
   pivot_number:4102, tenant_uuid:<Harbor>}` to the organizer validator.
3. The validator returns `BV{…}`. An incomplete bundle returns the missing
   elements.

## Mode note
Under patched mode (`AETHER_IDENTITY_MODE=patched`, `AETHER_AGENT_MODE=patched`)
each exploit closes: the indexer decommissions the legacy transport (09); the
provisioner requires a ticket and confines rendering (10/11); the provenance
verifier and manifest bind identity to the signed TLV (12/13). The forensic scorer
(14) and validator (15) are correctness oracles, identical in both modes.
