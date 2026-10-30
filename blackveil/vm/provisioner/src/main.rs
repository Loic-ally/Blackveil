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
//! Stage 11 ("The Privileged Reader") is served by the `provision` op; its controlled
//! design mistake and patch live in `handle_request` and are documented in
//! `docs/stages/stage-11.md`. Until Stage 11 lands, `provision` is refused.

use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::thread;

const SOCKET_PREFIX: &str = "aether-prov";
// Confined provisioning store, owned root:aether-prov (dir 0750, files 0640): the
// operator cannot read it directly, only through the provision deputy below.
const TEMPLATE_DIR: &str = "/var/lib/aether-provisioner/templates";

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

/// The handshake gate (pure). `epoch` is the world-readable boot token (challenge
/// gate); `credential` is the non-world-readable ticket (patched gate).
fn authorized(mode: Mode, epoch: &str, credential: &str, req: &Request) -> bool {
    match mode {
        // Challenge: the boot epoch is a world-readable handshake. Combined with
        // finding the abstract socket, it is enough — the Stage 10 correlation.
        Mode::Challenge => !epoch.is_empty() && req.epoch == epoch,
        // Patched: a ticket the operator cannot read from world-readable state.
        Mode::Patched => !credential.is_empty() && req.ticket == credential,
    }
}

fn describe() -> Value {
    json!({
        "ok": true,
        "service": "aether-provisioner",
        "stage": 10,
        "ops": ["describe", "provision"],
        "provision": {
            "note": "submit op=provision with arg=<template>; the provisioning \
                     deputy renders it from the confined store as its own identity",
            "next": "privileged-reader"
        }
    })
}

/// Resolve a provisioning template path (pure, covered by test vectors).
///
/// Stage 11 defect (challenge): `arg` is joined to the store directory with no
/// sanitization, so `../provenance.blob` (or any aether-prov-readable path)
/// escapes the store. The deputy runs as `aether-prov`, so the escape is bounded
/// to that service identity — it is NOT guest root. Patched mode rejects any
/// separator or parent reference, confining rendering to the store.
fn resolve_template(mode: Mode, base: &Path, arg: &str) -> Result<PathBuf, &'static str> {
    if mode == Mode::Patched {
        if arg.is_empty() || arg.contains('/') || arg.contains("..") {
            return Err("invalid template");
        }
    }
    if arg.is_empty() {
        return Err("invalid template");
    }
    Ok(base.join(arg))
}

/// Render a provision request. I/O is injected as `read` so the control flow is
/// unit-testable without a filesystem.
fn provision<R>(mode: Mode, base: &Path, arg: &str, read: R) -> Value
where
    R: Fn(&Path) -> std::io::Result<String>,
{
    match resolve_template(mode, base, arg) {
        Err(reason) => json!({"error": reason}),
        Ok(path) => match read(&path) {
            Ok(body) => json!({"ok": true, "op": "provision", "template": arg, "rendered": body.trim_end()}),
            // Report only the error kind, never the resolved path, so containment
            // failures (e.g. a root-owned secret) read as a clean denial.
            Err(error) => json!({"error": format!("render failed: {:?}", error.kind())}),
        },
    }
}

fn handle_request(mode: Mode, epoch: &str, credential: &str, req: &Request) -> Value {
    if !authorized(mode, epoch, credential, req) {
        return json!({"error": "handshake"});
    }
    match req.op.as_str() {
        "describe" => describe(),
        "provision" => provision(mode, Path::new(TEMPLATE_DIR), &req.arg, |path| std::fs::read_to_string(path)),
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
    // One write: a Display of a Value emits many tiny writes on an unbuffered
    // socket, which a single client read can tear. Build the line, then write once.
    let mut stream = stream;
    let _ = stream.write_all(format!("{reply}\n").as_bytes());
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
    fn unknown_op_rejected() {
        let r = handle_request(Mode::Challenge, "a1b2c3d4", "", &req("sweep", "a1b2c3d4", ""));
        assert_eq!(r["error"], json!("unknown op"));
    }

    #[test]
    fn challenge_template_escapes_store() {
        // Stage 11 defect: traversal escapes the store (bounded to aether-prov).
        let base = Path::new("/var/lib/aether-provisioner/templates");
        let p = resolve_template(Mode::Challenge, base, "../provenance.blob").unwrap();
        assert_eq!(p, Path::new("/var/lib/aether-provisioner/templates/../provenance.blob"));
    }

    #[test]
    fn patched_template_confined_to_store() {
        let base = Path::new("/var/lib/aether-provisioner/templates");
        assert_eq!(resolve_template(Mode::Patched, base, "../provenance.blob"), Err("invalid template"));
        assert_eq!(resolve_template(Mode::Patched, base, "a/b"), Err("invalid template"));
        assert_eq!(resolve_template(Mode::Patched, base, ""), Err("invalid template"));
        assert_eq!(resolve_template(Mode::Patched, base, "default.tmpl").unwrap(),
                   Path::new("/var/lib/aether-provisioner/templates/default.tmpl"));
    }

    #[test]
    fn provision_renders_and_reports_bounded_denial() {
        let base = Path::new("/store");
        // Challenge traversal reads what the deputy (aether-prov) can read.
        let ok = provision(Mode::Challenge, base, "../provenance.blob",
                           |p| { assert!(p.ends_with("../provenance.blob")); Ok("BLOB".into()) });
        assert_eq!(ok["ok"], json!(true));
        assert_eq!(ok["rendered"], json!("BLOB"));
        // A guest-root secret the deputy cannot read is a clean denial, no path leak.
        let denied = provision(Mode::Challenge, base, "../../../etc/aether-agent/worker.key",
                               |_| Err(std::io::Error::from(std::io::ErrorKind::PermissionDenied)));
        assert!(denied["error"].as_str().unwrap().starts_with("render failed"));
        assert!(!denied.to_string().contains("worker.key"));
        // Patched refuses the traversal before any read.
        let patched = provision(Mode::Patched, base, "../provenance.blob", |_| Ok("BLOB".into()));
        assert_eq!(patched["error"], json!("invalid template"));
    }
}
