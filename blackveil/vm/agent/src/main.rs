use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

type HmacSha256 = Hmac<Sha256>;

const MAP_PATH: &str = "/etc/aether-agent/tenant-map.csv";
const ARCHIVE_DIR: &str = "/var/lib/aether-agent";
const KEY_PATH: &str = "/etc/aether-agent/worker.key";
const PRINCIPAL: &str = "svc:aether-reporting";
const BUILD_ID: &str = "agent/1.4.2-migration-protocol";
// Accepted clock difference between worker and guest, in seconds.
const REPLAY_WINDOW_SECS: u64 = 120;

type SeenEnvelopes = Arc<Mutex<HashMap<String, u64>>>;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Envelope {
    job_id: String,
    principal: String,
    tenant_uuid: String,
    legacy_tenant_no: u64,
    #[serde(default)]
    issued_at: u64,
    signature: String,
}

#[derive(Serialize)]
struct ArchiveResponse<'a> {
    job_id: &'a str,
    tenant_uuid: &'a str,
    resolved_legacy_tenant_no: u64,
    records: serde_json::Value,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mode = std::env::var("AETHER_AGENT_MODE").unwrap_or_else(|_| "challenge".into());
    if mode != "challenge" && mode != "patched" {
        return Err("AETHER_AGENT_MODE must be challenge or patched".into());
    }
    let key = fs::read_to_string(KEY_PATH)?.trim().to_owned();
    if key.len() < 64 || !key.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("worker key must contain at least 32 bytes of hexadecimal".into());
    }
    let tenants = load_tenant_map(MAP_PATH)?;
    let seen: SeenEnvelopes = Arc::default();
    let listener = TcpListener::bind("0.0.0.0:8080")?;
    eprintln!("{BUILD_ID} listening on 0.0.0.0:8080 ({mode})");
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                let mode = mode.clone();
                let key = key.clone();
                let tenants = tenants.clone();
                let seen = seen.clone();
                thread::spawn(move || handle(stream, &mode, &key, &tenants, &seen));
            }
            Err(error) => eprintln!("agent listener: {error}"),
        }
    }
    Ok(())
}

fn load_tenant_map(path: &str) -> Result<HashMap<String, u64>, Box<dyn std::error::Error>> {
    let mut tenants = HashMap::new();
    for line in fs::read_to_string(path)?.lines() {
        let mut fields = line.split(',');
        let uuid = fields.next().unwrap_or_default().trim();
        let number = fields.next().unwrap_or_default().trim().parse::<u64>()?;
        if fields.next().is_some() || !is_uuid(uuid) || tenants.insert(uuid.to_owned(), number).is_some() {
            return Err("invalid tenant map".into());
        }
    }
    if tenants.is_empty() {
        return Err("tenant map is empty".into());
    }
    Ok(tenants)
}

fn handle(mut stream: TcpStream, mode: &str, key: &str, tenants: &HashMap<String, u64>, seen: &SeenEnvelopes) {
    let _ = stream.set_read_timeout(Some(std::time::Duration::from_secs(3)));
    let request = match read_request(&mut stream) {
        Ok(request) => request,
        Err(status) => return respond(&mut stream, status, serde_json::json!({"error":"invalid request"})),
    };
    let (method, path, body) = request;
    match (method.as_str(), path.as_str()) {
        ("GET", "/healthz") => respond(&mut stream, 200, serde_json::json!({"status":"ok","agent":BUILD_ID})),
        ("GET", "/v1/build") => respond(&mut stream, 200, serde_json::json!({"service":BUILD_ID,"protocol":"legacy-envelope/1"})),
        ("POST", "/v1/legacy/archive") => match serde_json::from_slice::<Envelope>(&body) {
            Ok(envelope) => serve_archive(&mut stream, mode, key, tenants, seen, &envelope),
            Err(_) => respond(&mut stream, 400, serde_json::json!({"error":"invalid envelope"})),
        },
        _ => respond(&mut stream, 404, serde_json::json!({"error":"not found"})),
    }
}

fn serve_archive(stream: &mut TcpStream, mode: &str, key: &str, tenants: &HashMap<String, u64>, seen: &SeenEnvelopes, envelope: &Envelope) {
    if envelope.principal != PRINCIPAL || !is_uuid(&envelope.tenant_uuid) || !is_safe_job_id(&envelope.job_id) {
        return respond(stream, 403, serde_json::json!({"error":"service identity rejected"}));
    }
    let canonical = match tenants.get(&envelope.tenant_uuid) {
        Some(number) => *number,
        None => return respond(stream, 404, serde_json::json!({"error":"tenant not found"})),
    };
    let signed = signing_bytes(envelope, mode == "patched");
    if !verify_signature(key, &signed, &envelope.signature) {
        return respond(stream, 403, serde_json::json!({"error":"service signature rejected"}));
    }
    if mode == "patched" && envelope.legacy_tenant_no != canonical {
        return respond(stream, 403, serde_json::json!({"error":"tenant identity mismatch"}));
    }
    if mode == "patched" && !accept_once(seen, envelope) {
        return respond(stream, 403, serde_json::json!({"error":"envelope expired or replayed"}));
    }
    let selected = if mode == "challenge" { envelope.legacy_tenant_no } else { canonical };
    let archive_path = format!("{ARCHIVE_DIR}/archive-{selected}.json");
    if !Path::new(&archive_path).is_file() {
        return respond(stream, 404, serde_json::json!({"error":"archive not found"}));
    }
    let records = match fs::read_to_string(archive_path).ok().and_then(|text| serde_json::from_str(&text).ok()) {
        Some(records) => records,
        None => return respond(stream, 500, serde_json::json!({"error":"archive unavailable"})),
    };
    let response = ArchiveResponse {
        job_id: &envelope.job_id,
        tenant_uuid: &envelope.tenant_uuid,
        resolved_legacy_tenant_no: selected,
        records,
    };
    match serde_json::to_value(response) {
        Ok(value) => respond(stream, 200, value),
        Err(_) => respond(stream, 500, serde_json::json!({"error":"response encoding failed"})),
    }
}

fn signing_bytes(envelope: &Envelope, include_legacy: bool) -> Vec<u8> {
    let base = format!("{}\n{}\n{}", envelope.job_id, envelope.principal, envelope.tenant_uuid);
    if include_legacy {
        format!("{base}\n{}\n{}", envelope.legacy_tenant_no, envelope.issued_at).into_bytes()
    } else {
        base.into_bytes()
    }
}

// ponytail: in-memory only; an agent restart forgets envelopes still inside the
// window. Persist seen signatures if guest restarts become player-triggerable.
fn accept_once(seen: &SeenEnvelopes, envelope: &Envelope) -> bool {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).map(|elapsed| elapsed.as_secs()).unwrap_or(0);
    if now.abs_diff(envelope.issued_at) > REPLAY_WINDOW_SECS {
        return false;
    }
    let mut seen = seen.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    seen.retain(|_, issued| now.abs_diff(*issued) <= REPLAY_WINDOW_SECS);
    // Hex decoding accepts either case, so key on one spelling of the signature.
    seen.insert(envelope.signature.to_ascii_lowercase(), envelope.issued_at).is_none()
}

fn verify_signature(key_hex: &str, message: &[u8], signature: &str) -> bool {
    let key = match decode_hex(key_hex) {
        Some(key) => key,
        None => return false,
    };
    let signature = match decode_hex(signature) {
        Some(signature) => signature,
        None => return false,
    };
    let mut mac = match HmacSha256::new_from_slice(&key) {
        Ok(mac) => mac,
        Err(_) => return false,
    };
    mac.update(message);
    mac.verify_slice(&signature).is_ok()
}

fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if value.len() % 2 != 0 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return None;
    }
    value.as_bytes().chunks_exact(2).map(|pair| {
        let high = (pair[0] as char).to_digit(16)?;
        let low = (pair[1] as char).to_digit(16)?;
        Some(((high << 4) | low) as u8)
    }).collect()
}

fn read_request(stream: &mut TcpStream) -> Result<(String, String, Vec<u8>), u16> {
    let mut bytes = Vec::with_capacity(4096);
    let mut chunk = [0u8; 2048];
    let mut body_start = None;
    let mut expected = 0usize;
    loop {
        let read = stream.read(&mut chunk).map_err(|_| 400u16)?;
        if read == 0 { return Err(400); }
        bytes.extend_from_slice(&chunk[..read]);
        if bytes.len() > 16 * 1024 { return Err(413); }
        if body_start.is_none() {
            if let Some(index) = bytes.windows(4).position(|window| window == b"\r\n\r\n") {
                let header_end = index + 4;
                let header = std::str::from_utf8(&bytes[..index]).map_err(|_| 400u16)?;
                expected = header.lines().skip(1).find_map(|line| {
                    let (name, value) = line.split_once(':')?;
                    if name.eq_ignore_ascii_case("content-length") { value.trim().parse().ok() } else { None }
                }).unwrap_or(0);
                if expected > 8192 { return Err(413); }
                body_start = Some(header_end);
            }
        }
        if let Some(start) = body_start {
            if bytes.len() >= start + expected {
                let header = std::str::from_utf8(&bytes[..start - 4]).map_err(|_| 400u16)?;
                let request_line = header.lines().next().ok_or(400u16)?;
                let mut parts = request_line.split_whitespace();
                let method = parts.next().ok_or(400u16)?.to_owned();
                let path = parts.next().ok_or(400u16)?.to_owned();
                if parts.next().is_none() || parts.next().is_some() { return Err(400); }
                return Ok((method, path, bytes[start..start + expected].to_vec()));
            }
        }
    }
}

fn respond(stream: &mut TcpStream, status: u16, value: serde_json::Value) {
    let reason = match status { 200 => "OK", 400 => "Bad Request", 403 => "Forbidden", 404 => "Not Found", 413 => "Payload Too Large", _ => "Internal Server Error" };
    let body = value.to_string();
    let response = format!("HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
    let _ = stream.write_all(response.as_bytes());
}

fn is_uuid(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 36 && [8, 13, 18, 23].iter().all(|index| bytes[*index] == b'-') &&
        bytes.iter().enumerate().all(|(index, byte)| [8, 13, 18, 23].contains(&index) || byte.is_ascii_hexdigit())
}

fn is_safe_job_id(value: &str) -> bool {
    (1..=64).contains(&value.len()) && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

