//! aether-indexer — legacy native record indexer (Stage 09, "The Forgotten Binary").
//!
//! AETHER's modern path signs JSON envelopes (see `aether-agent`). Before the
//! UUID migration, components exchanged length-prefixed binary records over a
//! private bus and the indexer resolved them. The binary is retained as a
//! compatibility service for `legacy-envelope/0` records.
//!
//! Wire format `legacy-envelope/0` (big-endian):
//!
//! ```text
//!   offset 0  magic     4  b"AEI\0"
//!   offset 4  version   1  0x00 legacy transport, 0x01 signed
//!   offset 5  rec_type  1  0x10 QUERY, 0x01 TRUSTED_TRANSPORT (obsolete)
//!   offset 6  length    2  payload length
//!   offset 8  payload   length
//!   (version 0x01 only) trailer 32  HMAC-SHA256(key, bytes[0 .. 8+length])
//! ```
//!
//! A successful resolve returns a *provisioning descriptor* (a reference to the
//! next service, not a secret). The challenge-mode defect and its patch are in
//! `parse_record`; the documented-vs-implemented difference is in
//! `docs/stages/stage-09.md`.

use hmac::{Hmac, Mac};
use sha2::Sha256;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;
use std::time::Duration;

type HmacSha256 = Hmac<Sha256>;

const MAGIC: &[u8; 4] = b"AEI\0";
const VERSION_LEGACY: u8 = 0x00;
const VERSION_SIGNED: u8 = 0x01;
const REC_QUERY: u8 = 0x10;
const REC_TRUSTED_TRANSPORT: u8 = 0x01;
// The legacy bus set this origin marker from a kernel transport attestation.
// Documentation states userspace clients never set it; the challenge build
// trusts it from any client-supplied payload (the Stage 09 defect).
const TRUSTED_MARKER: u8 = 0xA7;
const HMAC_LEN: usize = 32;
const MAX_RECORD: usize = 4096;

const KEY_PATH: &str = "/etc/aether-indexer/transport.key";
const BUILD_ID: &str = "indexer/0.8.3-legacy-compat";
const LISTEN_ADDR: &str = "127.0.0.1:9090";

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Mode {
    Challenge,
    Patched,
}

#[derive(PartialEq, Eq, Debug)]
enum Outcome {
    /// Record accepted; the resolved tenant UUID.
    Authenticated(String),
    /// Record well-formed but refused, with a stable reason.
    Rejected(&'static str),
}

#[derive(PartialEq, Eq, Debug)]
enum ParseError {
    Short,
    BadMagic,
    BadVersion,
    TooLarge,
}

/// Pure record decision. No I/O, so it is covered directly by test vectors.
fn parse_record(mode: Mode, key: &[u8], buf: &[u8]) -> Result<Outcome, ParseError> {
    if buf.len() > MAX_RECORD {
        return Err(ParseError::TooLarge);
    }
    if buf.len() < 8 {
        return Err(ParseError::Short);
    }
    if &buf[0..4] != MAGIC {
        return Err(ParseError::BadMagic);
    }
    let version = buf[4];
    let rec_type = buf[5];
    let length = u16::from_be_bytes([buf[6], buf[7]]) as usize;
    let payload_end = 8usize.checked_add(length).ok_or(ParseError::TooLarge)?;

    match version {
        VERSION_SIGNED => {
            // Modern path: the whole header+payload is HMAC-authenticated.
            let end = payload_end.checked_add(HMAC_LEN).ok_or(ParseError::TooLarge)?;
            if buf.len() < end {
                return Err(ParseError::Short);
            }
            let payload = &buf[8..payload_end];
            let trailer = &buf[payload_end..end];
            if !hmac_ok(key, &buf[0..payload_end], trailer) {
                return Ok(Outcome::Rejected("signature"));
            }
            if rec_type != REC_QUERY {
                return Ok(Outcome::Rejected("record type"));
            }
            match parse_uuid(payload) {
                Some(tenant) => Ok(Outcome::Authenticated(tenant)),
                None => Ok(Outcome::Rejected("tenant")),
            }
        }
        VERSION_LEGACY => {
            // Legacy compatibility shim.
            if mode == Mode::Patched {
                // Patched: the legacy transport was decommissioned. Only signed
                // records are served; no compat path exists.
                return Ok(Outcome::Rejected("legacy transport decommissioned"));
            }
            if rec_type != REC_TRUSTED_TRANSPORT {
                return Ok(Outcome::Rejected("record type"));
            }
            if buf.len() < payload_end {
                return Err(ParseError::Short);
            }
            let payload = &buf[8..payload_end];
            // DEFECT (challenge): the shim was ported from the private-bus era,
            // where the transport layer attested the origin marker. Here it
            // trusts a client-supplied trailing marker byte and skips the HMAC
            // entirely — so any client that knows the marker is "pre-authorized".
            match payload.last().copied() {
                Some(TRUSTED_MARKER) => match parse_uuid(&payload[..payload.len() - 1]) {
                    Some(tenant) => Ok(Outcome::Authenticated(tenant)),
                    None => Ok(Outcome::Rejected("tenant")),
                },
                _ => Ok(Outcome::Rejected("origin marker")),
            }
        }
        _ => Err(ParseError::BadVersion),
    }
}

fn hmac_ok(key: &[u8], message: &[u8], signature: &[u8]) -> bool {
    let mut mac = match HmacSha256::new_from_slice(key) {
        Ok(mac) => mac,
        Err(_) => return false,
    };
    mac.update(message);
    mac.verify_slice(signature).is_ok()
}

fn parse_uuid(payload: &[u8]) -> Option<String> {
    if payload.len() != 36 {
        return None;
    }
    let text = std::str::from_utf8(payload).ok()?;
    let bytes = text.as_bytes();
    let dashes = [8, 13, 18, 23];
    let ok = dashes.iter().all(|i| bytes[*i] == b'-')
        && bytes
            .iter()
            .enumerate()
            .all(|(i, b)| dashes.contains(&i) || b.is_ascii_hexdigit());
    ok.then(|| text.to_owned())
}

/// The provisioning descriptor returned on a resolved record: a reference to the
/// next service (Stage 10 entry), never a secret.
fn descriptor(tenant: &str) -> serde_json::Value {
    serde_json::json!({
        "service": BUILD_ID,
        "protocol": "legacy-envelope/0",
        "resolved_tenant_uuid": tenant,
        "provisioner": {
            "service": "aether-provisioner",
            "endpoint": "@aether-prov",
            "note": "legacy provisioning channel; see namespace layout"
        }
    })
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mode = match std::env::var("AETHER_AGENT_MODE").as_deref() {
        Ok("patched") => Mode::Patched,
        Ok("challenge") | Err(_) => Mode::Challenge,
        Ok(other) => return Err(format!("AETHER_AGENT_MODE invalid: {other}").into()),
    };
    let key = fs::read(KEY_PATH)
        .ok()
        .map(|raw| decode_hex(String::from_utf8_lossy(&raw).trim()))
        .unwrap_or_default()
        .unwrap_or_default();
    let listener = TcpListener::bind(LISTEN_ADDR)?;
    eprintln!("{BUILD_ID} listening on {LISTEN_ADDR} ({mode:?})");
    for stream in listener.incoming().flatten() {
        let key = key.clone();
        thread::spawn(move || handle(stream, mode, &key));
    }
    Ok(())
}

fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if value.len() % 2 != 0 || !value.bytes().all(|b| b.is_ascii_hexdigit()) {
        return None;
    }
    (0..value.len() / 2)
        .map(|i| u8::from_str_radix(&value[2 * i..2 * i + 2], 16).ok())
        .collect()
}

fn handle(mut stream: TcpStream, mode: Mode, key: &[u8]) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    let mut buf = Vec::with_capacity(512);
    let mut chunk = [0u8; 512];
    loop {
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => {
                buf.extend_from_slice(&chunk[..n]);
                if buf.len() > MAX_RECORD {
                    break;
                }
                // A full record is header + declared length (+ HMAC for signed).
                if record_complete(&buf) {
                    break;
                }
            }
            Err(_) => break,
        }
    }
    let reply = match parse_record(mode, key, &buf) {
        Ok(Outcome::Authenticated(tenant)) => descriptor(&tenant).to_string(),
        Ok(Outcome::Rejected(reason)) => serde_json::json!({"error": reason}).to_string(),
        Err(_) => serde_json::json!({"error": "malformed record"}).to_string(),
    };
    let _ = stream.write_all(reply.as_bytes());
}

fn record_complete(buf: &[u8]) -> bool {
    if buf.len() < 8 {
        return false;
    }
    let length = u16::from_be_bytes([buf[6], buf[7]]) as usize;
    let need = match buf[4] {
        VERSION_SIGNED => 8 + length + HMAC_LEN,
        _ => 8 + length,
    };
    buf.len() >= need
}

#[cfg(test)]
mod tests {
    use super::*;

    const KEY: &[u8] = b"0123456789abcdef0123456789abcdef";
    const UUID: &str = "4f3e2d1c-0b9a-4876-9d5c-4b3a29180716";

    fn signed_query(payload: &[u8]) -> Vec<u8> {
        let mut rec = Vec::new();
        rec.extend_from_slice(MAGIC);
        rec.push(VERSION_SIGNED);
        rec.push(REC_QUERY);
        rec.extend_from_slice(&(payload.len() as u16).to_be_bytes());
        rec.extend_from_slice(payload);
        let mut mac = HmacSha256::new_from_slice(KEY).unwrap();
        mac.update(&rec);
        rec.extend_from_slice(&mac.finalize().into_bytes());
        rec
    }

    fn legacy_trusted(payload: &[u8]) -> Vec<u8> {
        let mut rec = Vec::new();
        rec.extend_from_slice(MAGIC);
        rec.push(VERSION_LEGACY);
        rec.push(REC_TRUSTED_TRANSPORT);
        rec.extend_from_slice(&(payload.len() as u16).to_be_bytes());
        rec.extend_from_slice(payload);
        rec
    }

    #[test]
    fn modern_signed_query_resolves() {
        let rec = signed_query(UUID.as_bytes());
        assert_eq!(
            parse_record(Mode::Challenge, KEY, &rec).unwrap(),
            Outcome::Authenticated(UUID.to_string())
        );
        // The modern path is identical under the patch.
        assert_eq!(
            parse_record(Mode::Patched, KEY, &rec).unwrap(),
            Outcome::Authenticated(UUID.to_string())
        );
    }

    #[test]
    fn modern_tampered_signature_rejected() {
        let mut rec = signed_query(UUID.as_bytes());
        *rec.last_mut().unwrap() ^= 0xff;
        assert_eq!(
            parse_record(Mode::Challenge, KEY, &rec).unwrap(),
            Outcome::Rejected("signature")
        );
    }

    #[test]
    fn modern_wrong_type_rejected() {
        let mut rec = signed_query(UUID.as_bytes());
        rec[5] = 0x99; // rec_type
                       // Re-sign so the only failure is the type check.
        let payload_end = rec.len() - HMAC_LEN;
        let mut mac = HmacSha256::new_from_slice(KEY).unwrap();
        mac.update(&rec[..payload_end]);
        rec[payload_end..].copy_from_slice(&mac.finalize().into_bytes());
        assert_eq!(
            parse_record(Mode::Challenge, KEY, &rec).unwrap(),
            Outcome::Rejected("record type")
        );
    }

    #[test]
    fn legacy_marker_bypasses_hmac_in_challenge() {
        // The Stage 09 defect: a client-supplied marker is trusted, no key used.
        let mut payload = UUID.as_bytes().to_vec();
        payload.push(TRUSTED_MARKER);
        let rec = legacy_trusted(&payload);
        assert_eq!(
            parse_record(Mode::Challenge, &[], &rec).unwrap(),
            Outcome::Authenticated(UUID.to_string())
        );
    }

    #[test]
    fn legacy_transport_rejected_when_patched() {
        let mut payload = UUID.as_bytes().to_vec();
        payload.push(TRUSTED_MARKER);
        let rec = legacy_trusted(&payload);
        assert_eq!(
            parse_record(Mode::Patched, &[], &rec).unwrap(),
            Outcome::Rejected("legacy transport decommissioned")
        );
    }

    #[test]
    fn legacy_without_marker_rejected() {
        let rec = legacy_trusted(UUID.as_bytes()); // no trailing marker
        assert_eq!(
            parse_record(Mode::Challenge, &[], &rec).unwrap(),
            Outcome::Rejected("origin marker")
        );
    }

    #[test]
    fn malformed_records_error_without_panic() {
        assert_eq!(parse_record(Mode::Challenge, KEY, b"AEI").unwrap_err(), ParseError::Short);
        assert_eq!(
            parse_record(Mode::Challenge, KEY, b"XXXX\x01\x10\x00\x00").unwrap_err(),
            ParseError::BadMagic
        );
        let mut rec = signed_query(UUID.as_bytes());
        rec[4] = 0x07; // unknown version
        assert_eq!(parse_record(Mode::Challenge, KEY, &rec).unwrap_err(), ParseError::BadVersion);
        // Declared length overruns the buffer → Short, never a panic.
        let mut rec = legacy_trusted(UUID.as_bytes());
        rec[6] = 0xff;
        rec[7] = 0xff;
        assert!(parse_record(Mode::Challenge, &[], &rec).is_err());
    }
}
