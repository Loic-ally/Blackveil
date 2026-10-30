# Stage 09 — The Forgotten Binary

**Stage ID**

`BV-09-FORGOTTEN-BINARY`

**Domain**

Advanced reverse engineering (native ELF, custom binary protocol).

**Player objective**

From the `operator` shell, discover that the agent delegates `legacy-envelope/0`
records to a second native service, `aether-indexer`; reverse-engineer its
undocumented binary record format; and find the compatibility-shim defect that
lets an unauthenticated client resolve a record. The resolve returns a
*provisioning descriptor* — the reference that opens Stage 10.

**Starting knowledge (entry condition)**

The Stage 08 end state: an `operator` shell in the guest; the ability to drive
`aether-agent` on `127.0.0.1:8080`; and `GET /v1/build`, which now also advertises
a `legacy-envelope/0` fallback handled by the indexer. The indexer binary
`/usr/local/sbin/aether-indexer` is world-readable (for analysis); its transport
key `/etc/aether-indexer/transport.key` is `root:aether-indexer` and **not**
operator-readable.

**System components**

- `aether-indexer` (Rust, `vm/indexer/`), a systemd service listening on
  `127.0.0.1:9090` in the guest.
- Wire format `legacy-envelope/0` (big-endian): `magic b"AEI\0"`, `version(1)`,
  `rec_type(1)`, `length(2)`, `payload(length)`, and for `version=0x01` a 32-byte
  `HMAC-SHA256(transport.key, header||payload)` trailer.
- `rec_type`: `0x10` QUERY (modern, signed), `0x01` TRUSTED_TRANSPORT (obsolete,
  legacy `version=0x00`).

**Root cause (precise)**

`parse_record` in `vm/indexer/src/main.rs`. The legacy compatibility path
(`version == 0x00`, `rec_type == 0x01`) was ported from the private-bus era, where
a kernel transport layer attested a one-byte "origin marker" (`0xA7`). The
challenge build trusts that marker **from the client-supplied payload** and skips
the HMAC entirely: a record whose payload ends in `0xA7` is treated as
pre-authenticated, and the indexer resolves the tenant UUID carried in the rest of
the payload. The modern signed path (`version == 0x01`) is unaffected and verifies
the HMAC correctly.

**Documented vs implemented difference** (the RE insight): the protocol notes say
the trusted-transport marker is set only by the bus driver and never by a client.
The implementation accepts it from any client. There is no readable file stating
the marker value, the field offsets, or that the legacy path skips the HMAC — the
player recovers all of this from the binary.

**Realistic origin**

The indexer predates the UUID migration. Rather than delete the legacy transport,
the migration kept a compatibility shim "temporarily". The shim's security
depended on a transport attestation that no longer exists, so the marker check
became a client-controlled bypass.

**Player-discoverable clues**

1. `aether-agent`'s `GET /v1/build` advertises `legacy-envelope/0` and a local
   indexer port.
2. A listening socket on `127.0.0.1:9090` (e.g. `ss -ltnp`, `/proc/net/tcp`).
3. The world-readable `aether-indexer` ELF for static/dynamic analysis.
4. Sending a modern record with a bad/absent HMAC is rejected (`"signature"`),
   proving the modern path is authenticated — which motivates finding the legacy
   path.
5. Strings/symbols hint at a legacy compat path, but the marker value and the
   missing HMAC check are only confirmable by reading the parse logic.

**Reproducible intended solution**

1. Identify the indexer and its port from the agent metadata and the guest's
   listening sockets.
2. Reverse the ELF to recover the record layout, the two versions/types, and the
   legacy marker `0xA7`.
3. Craft a `version=0x00, rec_type=0x01` record whose payload is the target tenant
   UUID (36 bytes) followed by `0xA7`; send it to `:9090`.
4. Receive the provisioning descriptor naming `aether-provisioner` and its IPC
   endpoint. This is the Stage 10 entry (a reference, not a secret).

**Patched implementation**

In `patched` mode (`AETHER_AGENT_MODE=patched`), the legacy transport is
decommissioned: any `version=0x00` record is rejected
(`"legacy transport decommissioned"`). Only signed `version=0x01` QUERY records
are served, so the crafted legacy record no longer resolves.

**Automated challenge-mode tests**

`vm/indexer` `cargo test` (host, deterministic, no guest):
`modern_signed_query_resolves`, `legacy_marker_bypasses_hmac_in_challenge`,
`legacy_without_marker_rejected`, `modern_tampered_signature_rejected`,
`modern_wrong_type_rejected`, `malformed_records_error_without_panic`.

**Automated patched-mode tests**

`legacy_transport_rejected_when_patched` (legacy record refused), and
`modern_signed_query_resolves` asserts the modern path is identical under the
patch. Guest-level player-terminal verification is added to
`scripts/verify-chain.py` when the indexer is wired into the guest (Phase B
integration; tracked in `PROGRESS.md`).

**Unintended-path analysis**

- The transport key is not operator-readable, so the player cannot forge a
  *modern* signed record; the only unauthenticated resolve is the intended legacy
  bypass.
- Rust memory safety means the length field cannot cause an out-of-bounds read; an
  over-declared length yields a clean `Short` error, not a disclosure. The defect
  is a *logic* bypass (trusting a client marker), not memory corruption — so there
  is no accidental info-leak shortcut.
- The descriptor is a reference only; it grants no capability by itself, so
  resolving a record for an arbitrary UUID does not skip Stage 10.

**Progressive hint structure**

1. "The agent mentions an older protocol. What else is listening in the guest?"
2. "The modern record is signed. Is every record type signed?"
3. "The legacy transport trusted something the bus used to provide. What sets it
   now?"
4. "The last byte of a legacy payload decides everything. Read the parser."

**Organizer documentation**

Design and dependency in `organizer/attack-graph-v3.md` §2 (Stage 09). Isolation:
the indexer binds guest loopback only, joins no new network, and exposes no host
port; its key stays root-owned. Build weight and the host-test inner loop are in
`organizer/advanced-extension-assessment.md` §7.
