
use serde::Deserialize;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::thread;

const SOCKET_PREFIX: &str = "aether-prov";
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

fn authorized(mode: Mode, epoch: &str, credential: &str, req: &Request) -> bool {
    match mode {
        Mode::Challenge => !epoch.is_empty() && req.epoch == epoch,
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

fn provision<R>(mode: Mode, base: &Path, arg: &str, read: R) -> Value
where
    R: Fn(&Path) -> std::io::Result<String>,
{
    match resolve_template(mode, base, arg) {
        Err(reason) => json!({"error": reason}),
        Ok(path) => match read(&path) {
            Ok(body) => json!({"ok": true, "op": "provision", "template": arg, "rendered": body.trim_end()}),
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
    let credential = std::fs::read_to_string("/etc/aether-provisioner/ticket")
        .unwrap_or_default()
        .trim()
        .to_owned();

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
        let ok = provision(Mode::Challenge, base, "../provenance.blob",
                           |p| { assert!(p.ends_with("../provenance.blob")); Ok("BLOB".into()) });
        assert_eq!(ok["ok"], json!(true));
        assert_eq!(ok["rendered"], json!("BLOB"));
        let denied = provision(Mode::Challenge, base, "../../../etc/aether-agent/worker.key",
                               |_| Err(std::io::Error::from(std::io::ErrorKind::PermissionDenied)));
        assert!(denied["error"].as_str().unwrap().starts_with("render failed"));
        assert!(!denied.to_string().contains("worker.key"));
        let patched = provision(Mode::Patched, base, "../provenance.blob", |_| Ok("BLOB".into()));
        assert_eq!(patched["error"], json!("invalid template"));
    }
}
