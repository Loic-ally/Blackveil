//! aether-provisioner — confined provisioning service (Stages 10-11).
//!
//! Stage 10 ("Namespace Labyrinth"): the service runs under the `aether-prov`
//! account in a private mount namespace (and a private PID namespace where the
//! guest's systemd supports it), listening on a per-boot *abstract* unix socket
//! `@aether-prov.<boot8>` where `boot8` is the first 8 hex of the guest boot id.
//! Reaching it requires correlating three world-readable observations: the
//! Stage 09 descriptor (names the service), `/proc/net/unix` (the exact abstract
//! name), and `/proc/sys/kernel/random/boot_id` (the handshake epoch). The
//! request protocol is recovered from this binary (world-readable).
//!
//! Challenge mode gates `describe` on the world-readable boot epoch, so the
//! correlation is sufficient. Patched mode instead requires a `ticket` the
//! operator cannot derive from world-readable state, closing the shortcut.
//!
//! Stage 11 ("False Root") is served by the `provision` op; its controlled
//! design mistake and patch live in `handle_request` and are documented in
//! `docs/stages/stage-11.md`. Until Stage 11 lands, `provision` is refused.

use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::thread;

const SOCKET_PREFIX: &str = "aether-prov";

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Mode {
    Challenge,
    Patched,
}

#[derive(Deserialize, Default)]
#[serde(default)]
struct Request {
    op: String,
    epoch: String,
    ticket: String,
    arg: String,
}

/// Pure request handler (no I/O), covered by test vectors.
///
/// `epoch` is the world-readable boot handshake token (challenge gate).
/// `ticket` is the non-world-readable credential (patched gate).
fn handle_request(mode: Mode, epoch: &str, credential: &str, req: &Request) -> Value {
    let authorized = match mode {
        // Challenge: the boot epoch is a world-readable handshake. Combined with
        // finding the abstract socket, it is enough — the Stage 10 correlation.
        Mode::Challenge => !epoch.is_empty() && req.epoch == epoch,
        // Patched: a ticket the operator cannot read from world-readable state.
        // The epoch no longer authorizes anything.
        Mode::Patched => !credential.is_empty() && req.ticket == credential,
    };
    if !authorized {
        return json!({"error": "handshake"});
    }
    match req.op.as_str() {
        "describe" => json!({
            "ok": true,
            "service": "aether-provisioner",
            "stage": 10,
            "ops": ["describe", "provision"],
            "provision": {
                "note": "submit op=provision with a provisioning action; \
                         the legacy path maps the caller by namespace credential",
                "next": "false-root"
            }
        }),
        // Stage 11 lands the controlled privilege mistake here.
        "provision" => json!({"error": "provisioning not authorized (stage 11)"}),
        _ => json!({"error": "unknown op"}),
    }
}

fn boot_epoch() -> String {
    std::fs::read_to_string("/proc/sys/kernel/random/boot_id")
        .ok()
        .map(|id| id.trim().replace('-', "").chars().take(8).collect())
        .unwrap_or_default()
}

fn main() -> std::io::Result<()> {
    let mode = match std::env::var("AETHER_AGENT_MODE").as_deref() {
        Ok("patched") => Mode::Patched,
        _ => Mode::Challenge,
    };
    let epoch = boot_epoch();
    // Patched credential: provisioned out of band (root-owned), never world-readable.
    let credential = std::fs::read_to_string("/etc/aether-provisioner/ticket")
        .unwrap_or_default()
        .trim()
        .to_owned();

    // Abstract socket name: a leading NUL byte places it in the abstract
    // namespace. The visible name in /proc/net/unix is @aether-prov.<boot8>.
    let name = format!("{SOCKET_PREFIX}.{epoch}");
    let mut addr = vec![0u8];
    addr.extend_from_slice(name.as_bytes());
    let listener = bind_abstract(&addr)?;
    eprintln!("aether-provisioner/0.5.0 listening on @{name} ({mode:?})");

    for stream in listener.incoming().flatten() {
        let epoch = epoch.clone();
        let credential = credential.clone();
        thread::spawn(move || serve(stream, mode, &epoch, &credential));
    }
    Ok(())
}

#[cfg(target_os = "linux")]
fn bind_abstract(addr: &[u8]) -> std::io::Result<UnixListener> {
    use std::os::linux::net::SocketAddrExt;
    use std::os::unix::net::SocketAddr;
    let addr = SocketAddr::from_abstract_name(&addr[1..])?;
    UnixListener::bind_addr(&addr)
}

#[cfg(not(target_os = "linux"))]
fn bind_abstract(_addr: &[u8]) -> std::io::Result<UnixListener> {
    // Abstract sockets are Linux-only; the service only runs in the Linux guest.
    // This keeps the crate compilable on the dev host for `cargo test`.
    Err(std::io::Error::new(std::io::ErrorKind::Unsupported, "abstract sockets are Linux-only"))
}

fn serve(stream: UnixStream, mode: Mode, epoch: &str, credential: &str) {
    let mut reader = BufReader::new(match stream.try_clone() {
        Ok(clone) => clone,
        Err(_) => return,
    });
    let mut line = String::new();
    if reader.read_line(&mut line).is_err() {
        return;
    }
    let reply = match serde_json::from_str::<Request>(&line) {
        Ok(req) => handle_request(mode, epoch, credential, &req),
        Err(_) => json!({"error": "malformed request"}),
    };
    let mut stream = stream;
    let _ = writeln!(stream, "{reply}");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(op: &str, epoch: &str, ticket: &str) -> Request {
        Request { op: op.into(), epoch: epoch.into(), ticket: ticket.into(), arg: String::new() }
    }

    #[test]
    fn challenge_describe_requires_boot_epoch() {
        let ok = handle_request(Mode::Challenge, "a1b2c3d4", "", &req("describe", "a1b2c3d4", ""));
        assert_eq!(ok["ok"], json!(true));
        assert_eq!(ok["ops"], json!(["describe", "provision"]));
    }

    #[test]
    fn challenge_wrong_epoch_rejected() {
        let bad = handle_request(Mode::Challenge, "a1b2c3d4", "", &req("describe", "deadbeef", ""));
        assert_eq!(bad["error"], json!("handshake"));
        let empty = handle_request(Mode::Challenge, "a1b2c3d4", "", &req("describe", "", ""));
        assert_eq!(empty["error"], json!("handshake"));
    }

    #[test]
    fn patched_ignores_epoch_requires_ticket() {
        // The world-readable epoch no longer authorizes anything under the patch.
        let shortcut = handle_request(Mode::Patched, "a1b2c3d4", "SECRET", &req("describe", "a1b2c3d4", ""));
        assert_eq!(shortcut["error"], json!("handshake"));
        let ok = handle_request(Mode::Patched, "a1b2c3d4", "SECRET", &req("describe", "", "SECRET"));
        assert_eq!(ok["ok"], json!(true));
    }

    #[test]
    fn provision_refused_until_stage_11() {
        let r = handle_request(Mode::Challenge, "a1b2c3d4", "", &req("provision", "a1b2c3d4", ""));
        assert_eq!(r["error"], json!("provisioning not authorized (stage 11)"));
    }

    #[test]
    fn unknown_op_rejected() {
        let r = handle_request(Mode::Challenge, "a1b2c3d4", "", &req("sweep", "a1b2c3d4", ""));
        assert_eq!(r["error"], json!("unknown op"));
    }
}
