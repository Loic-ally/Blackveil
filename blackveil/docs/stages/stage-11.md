# Stage 11 — The Privileged Reader

**Stage ID**

`BV-11-PRIVILEGED-READER`

**Domain**

Privilege boundaries (service-identity confinement; namespace/host distinction).

**Player objective**

Use the provisioner's `provision` op to make its confined *deputy* render a file
from outside its template store, extracting the provenance blob (the Stage 12
input). Then recognize that this "root of the provisioning domain" is bounded: the
deputy runs as the unprivileged `aether-prov` service identity and cannot read
guest-root secrets or escape the guest.

**Starting knowledge (entry condition)**

Stage 10: a completed `describe` handshake to the provisioner over its abstract
socket, and the Stage 11 reference (`next: privileged-reader`). The player holds the
`operator` shell.

**System components**

- `aether-provisioner` `provision` op (`vm/provisioner/src/main.rs`,
  `resolve_template` / `provision`).
- A confined store `/var/lib/aether-provisioner/templates/` and the artifact
  `/var/lib/aether-provisioner/provenance.blob`, all `root:aether-prov` (dir
  `0750`, files `0640`) — unreadable by `operator`, read only by the deputy.
- The guest-root secret `/etc/aether-agent/worker.key` (`root:aether-agent`),
  used to prove the boundary.

**Root cause (precise)**

`resolve_template` (challenge) joins the caller-supplied `arg` to the store
directory with no sanitization, so `arg="../provenance.blob"` escapes the store.
The deputy performs the read as `aether-prov`, so the escape is real but bounded
to that service identity. The privilege-boundary lesson: controlling the deputy
is *not* guest root — `aether-prov` is not in the `aether-agent` group and is not
UID 0, so the same traversal to `/etc/aether-agent/worker.key` is denied.

**Realistic origin**

The provisioner renders named templates from a store. A convenience ("let callers
name any provisioning fragment") skipped path canonicalization, trusting that the
service account's own confinement was a sufficient boundary — which it is for the
host, but not within the `aether-prov` read domain.

**Player-discoverable clues**

1. The `describe` reply advertises `op=provision` with `arg=<template>`.
2. The world-readable provisioner binary shows the store path and the unsanitized
   join.
3. A benign `arg="default.tmpl"` renders normally (confirms the deputy reads the
   store as itself); the natural next test is `../`.

**Reproducible intended solution**

1. `{"op":"provision","epoch":"<boot8>","arg":"default.tmpl"}` → renders the
   template (deputy works).
2. `{"op":"provision","epoch":"<boot8>","arg":"../provenance.blob"}` → renders the
   provenance blob. Keep it for Stage 12.
3. `{"op":"provision","epoch":"<boot8>","arg":"../../../etc/aether-agent/worker.key"}`
   → `render failed` (bounded): the deputy is not guest root.

**Patched implementation**

`resolve_template` (patched) rejects any `arg` that is empty, contains `/`, or
contains `..`, confining rendering to the store (`{"error":"invalid template"}`).
Legitimate named templates still render.

**Automated challenge-mode tests**

Host (`vm/provisioner` `cargo test`): `challenge_template_escapes_store`,
`provision_renders_and_reports_bounded_denial`. Live
(`scripts/verify-chain.py`, player terminal): render the default template, escape
to the provenance blob (valid `provenance/1`), confirm a guest-root read is a
bounded denial with no path leak, and confirm the operator cannot read the store
directly.

**Automated patched-mode tests**

Host: `patched_template_confined_to_store`. Live: an organizer assertion (using
the ticket derived from the `.env` agent key) confirms the patched deputy renders
a legitimate template but refuses the traversal.

**Unintended-path analysis**

- The store is `root:aether-prov 0750/0640`, so the operator cannot read the blob
  without the deputy; the traversal is the intended path.
- The deputy reports only the error *kind*, never the resolved path, so a
  containment failure cannot be used to probe the filesystem by differential path
  disclosure.
- The elevation is bounded to `aether-prov`: no UID 0, no `aether-agent` group, no
  host access. This is enforced by Linux file ownership, not by the service, so
  the boundary holds even with the flaw.

**Progressive hint structure**

1. "`provision` takes a template name. Where does it read templates from?"
2. "A name is joined to a directory. What if the name climbs out of it?"
3. "You can read what the deputy can read. What can it NOT read?"
4. "The blob is the prize; the denied secret is the lesson."

**Organizer documentation**

Design in `organizer/attack-graph-v3.md` §2 (Stage 11). Isolation: the only new
capability is read access within the `aether-prov` identity, bounded by Linux
ownership; there is no path to guest root, host files, or any namespace escape.
The provenance blob is the Stage 12 artifact; its cryptographic structure is
analyzed there.
