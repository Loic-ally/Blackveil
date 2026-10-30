# Stage 14 — Everything Was Logged

**Stage ID**

`BV-14-EVERYTHING-WAS-LOGGED`

**Domain**

Digital forensics (multi-source timeline reconstruction).

**Player objective**

Using the evidence set the Stage 13 manifest points at, reconstruct the original
migration incident: recover the guest clock offset, see past a retry, and identify
the cross-tenant pivot (the request whose resolved tenant number differs from the
actor's). Submit the reconstruction to the scorer to obtain an incident
attestation (a Stage 15 input).

**Starting knowledge (entry condition)**

The Stage 13 manifest, whose `evidence` field points at
`/var/lib/aether-migration/incident/`.

**System components / evidence**

Under `/var/lib/aether-migration/incident/` (operator-readable), seeded
deterministically by `render-cloud-init.py`:
- `deployment.jsonl` — dispatch IDs, service principal, retry reason and migration-map fallback; correlate dispatches with worker and API events.
- `worker.jsonl` — worker archive records (UTC, actor by number), including a
  retry of the same job.
- `agent-trace.log` — guest agent traces on a clock offset from UTC.
- `api-audit.jsonl` — application audit events (UTC, actor by UUID).
- `migration-metadata.json` — the UUID↔number map and the incident window.
- `NOTES` — the clock-sync caveat and how to align via the heartbeat.
The scorer is the agent endpoint `POST /v1/incident` (`incident_decision`).

**Root cause (precise — reconstruction, not a vulnerability)**

The evidence is internally consistent only after correcting a deterministic guest
clock offset (the agent trace runs `offset` seconds ahead of UTC). The heartbeat
`hb-0` appears in both `worker.jsonl` (UTC) and `agent-trace.log` (guest clock),
so `offset = gts(hb-0) − ts(hb-0)`. A retry duplicates one request and must be
collapsed. The pivot is the agent trace whose `resolved_no` (4102, Harbor) differs
from the actor's own number (4101, North) — the original cross-tenant abuse that
the whole chain descends from. The correct `(offset, pivot_job, pivot_number)` is
machine-checkable against the seed.

**Realistic origin**

The guest's clock drifted (no NTP) during the migration window, so the native
traces and the application/worker logs disagree on wall-clock time; a transient
failure caused a retry. A real incident reconstruction must reconcile these before
attributing the pivot.

**Player-discoverable clues**

1. The manifest's `evidence` path.
2. `NOTES` states the clock caveat and names the heartbeat anchor.
3. The same `job` appears in worker and agent evidence with different clocks and a
   retry; one agent trace resolves a foreign number.

**Reproducible intended solution**

1. Read the evidence. Align `hb-0` across worker/agent to get `offset`.
2. Correlate the deployment dispatch IDs with worker requests. Collapse the lease retry, then use the API actor UUID and migration map to identify the agent trace with a foreign `resolved_no`.
3. Submit `{offset, pivot_job, pivot_number: 4102}` to `/v1/incident` → an
   incident attestation and `next: the-black-veil`.

**Patched / correctness oracle**

Forensics has no "vulnerable vs patched" build; the scorer is the correctness
oracle and behaves identically in both modes. It accepts only the exact
reconstruction: a wrong offset, pivot job, or target number is rejected
(`reconstruction incorrect`). This is the stage's patched-equivalent assertion.

**Automated tests**

Host (`vm/agent` `cargo test`): `incident_scorer_accepts_correct_reconstruction`,
`incident_scorer_rejects_wrong_offset_and_target`. Live
(`scripts/verify-chain.py`, player terminal): read the evidence, derive the offset
from the heartbeat, identify the pivot, obtain the attestation, and confirm a
wrong offset is rejected.

**Unintended-path analysis**

- The attestation is an HMAC over the seed and the pivot job; it cannot be forged
  without the worker key, so guessing the pivot without the offset still fails the
  scorer (all three fields are checked).
- The retry and the clock offset prevent a naive "last event wins" or "sort by raw
  timestamp" shortcut from producing the correct pivot time.
- The evidence is read-only data; no field here grants privilege by itself.

**Progressive hint structure**

1. "The manifest told you where to look. What's in that directory?"
2. "Two clocks disagree. What appears in both?"
3. "One request resolves a number its actor never owned. Which job?"

**Organizer documentation**

Design in `organizer/attack-graph-v3.md` §2 (Stage 14). The evidence and the
scorer seed are derived deterministically from the worker key, so they are stable
per deployment and regenerated on reset. The attestation feeds the Stage 15
validator.
