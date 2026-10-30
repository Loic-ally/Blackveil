# Stage 10 — Namespace Labyrinth

**Stage ID**

`BV-10-NAMESPACE-LABYRINTH`

**Domain**

Linux internals (process/namespace inspection, abstract sockets, procfs).

**Player objective**

Using the provisioning descriptor from Stage 09, locate and reach the confined
`aether-provisioner` service. It listens on a per-boot *abstract* unix socket and
only completes a handshake when the request carries the correct boot epoch.
Reaching it requires correlating several world-readable observations, not a single
readable file.

**Starting knowledge (entry condition)**

The Stage 09 descriptor, which names `aether-provisioner`, a generic endpoint hint
`@aether-prov`, and "see namespace layout". The player still holds only the
`operator` shell.

**System components**

- `aether-provisioner` (Rust, `vm/provisioner/`), run by systemd as the
  `aether-prov` account with `PrivateTmp`/`PrivateMounts` (a private mount
  namespace) but **no** private network namespace, so its socket is reachable.
- A per-boot abstract unix socket `@aether-prov.<boot8>`, where `boot8` is the
  first 8 hex of `/proc/sys/kernel/random/boot_id`.
- World-readable evidence: `/proc/net/unix` (the abstract name),
  `/proc/sys/kernel/random/boot_id` (the epoch), `/proc/<pid>/mountinfo` (the
  private-mount difference), and the provisioner binary (the request protocol).

**Root cause (precise)**

This is primarily a *discovery* stage, not a memory/logic vulnerability. The
legitimate transition is only findable by correlating three independent,
world-readable facts: the descriptor (which service), the abstract socket name in
`/proc/net/unix`, and the boot epoch that the `describe` handshake requires
(`handle_request` in `vm/provisioner/src/main.rs`). Isolated inspection of any one
is insufficient: the descriptor alone gives only a generic endpoint; the socket
name alone does not reveal the required epoch field; the epoch alone is useless
without the exact socket and the request shape.

**Realistic origin**

The provisioner was confined (own account, private mounts) during the migration
hardening, and a lightweight per-boot handshake was added "so only same-boot
components talk to it". The handshake token is the boot id prefix — which is
world-readable, so the confinement looks stronger than it is.

**Player-discoverable clues**

1. The Stage 09 descriptor: service name + `@aether-prov` + "namespace layout".
2. `/proc/net/unix` shows the full abstract name `@aether-prov.<boot8>`.
3. `/proc/sys/kernel/random/boot_id` yields `<boot8>`.
4. Comparing `/proc/self/mountinfo` with the provisioner's confirms a private
   mount namespace (service confinement).
5. The world-readable binary reveals the JSON request shape and the epoch gate.

**Reproducible intended solution**

1. From the descriptor, learn the provisioner exists and its endpoint family.
2. Read `/proc/net/unix`; find `@aether-prov.<boot8>`.
3. Read `boot_id`; derive `<boot8>`.
4. Reverse the binary for the request shape; connect to the abstract socket and
   send `{"op":"describe","epoch":"<boot8>"}`.
5. Receive the describe reply, including the Stage 11 reference (`next:
   false-root`).

**Patched implementation**

In `patched` mode the provisioner ignores the boot epoch and requires a `ticket`
that is provisioned `root:aether-prov` (not world-readable), so the
world-readable correlation no longer authorizes the handshake
(`{"error":"handshake"}`).

**Automated challenge-mode tests**

Host (`vm/provisioner` `cargo test`): `challenge_describe_requires_boot_epoch`,
`challenge_wrong_epoch_rejected`, `unknown_op_rejected`. Live
(`scripts/verify-chain.py`, player terminal): discover the socket in
`/proc/net/unix`, derive the epoch from `boot_id`, handshake successfully, and get
the Stage 11 reference; a wrong epoch is refused; the ticket is not
operator-readable.

**Automated patched-mode tests**

Host: `patched_ignores_epoch_requires_ticket`. Live: an organizer assertion
against the patched guest confirms the epoch-only handshake is refused.

**Unintended-path analysis**

- The abstract socket is in the guest's main network namespace (no
  `PrivateNetwork`), so it is reachable — but only by a client that also supplies
  the epoch; a blind connect without the epoch is refused.
- The `provision` op (Stage 11) is refused here, so reaching the socket does not
  skip Stage 11.
- The patched ticket is not world-readable, so the challenge correlation cannot be
  reused against a patched deployment.
- `/proc/<pid>/fd` and `/proc/<pid>/root` of the provisioner are owner-only, so
  the operator cannot read the provisioner's private files or map the socket inode
  that way; the intended path uses only world-readable `/proc` data.

**Progressive hint structure**

1. "The descriptor names a service and an endpoint. What is actually listening?"
2. "Unix sockets have a table too. Which one is abstract?"
3. "The socket name carries a per-boot suffix. Where does the guest keep that?"
4. "The handshake wants the same value you can already read. Read the binary for
   the field name."

**Organizer documentation**

Design in `organizer/attack-graph-v3.md` §2 (Stage 10). Isolation: the provisioner
joins no network namespace change that would hide its socket, binds only an
abstract unix socket (no host port), and its ticket stays root-owned. The private
mount namespace is a confining measure and a player-visible signal, not a host
boundary.
