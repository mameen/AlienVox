//! Local privacy-preserving telemetry for the dev TTS loop.
//!
//! Events are JSONL so they are easy to inspect now and easy to bridge to
//! OpenTelemetry later. Never record source text here; record only sizes, timing,
//! engine/model identifiers, and operational status.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::LazyLock;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TelemetryConfig {
    pub rate: i32,
    pub pitch: i32,
    pub volume: u8,
    pub hot_ttl_seconds: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TtsTelemetryEvent<'a> {
    pub event: &'a str,
    pub request_id: &'a str,
    pub engine: &'a str,
    pub model: &'a str,
    pub voice: &'a str,
    pub text_chars: usize,
    pub text_bytes: usize,
    pub config: TelemetryConfig,
    pub latency_ms: Option<u128>,
    pub status: Option<&'a str>,
    pub detail: Option<&'a str>,
}

static SESSION_ID: LazyLock<String> = LazyLock::new(|| format!("session-{}", now_ms()));

pub fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or_default()
}

pub fn new_request_id() -> String {
    new_play_id()
}

pub fn session_id() -> &'static str {
    SESSION_ID.as_str()
}

pub fn init_session() -> &'static str {
    let id = session_id();
    eprintln!("[Telemetry] session started: {id}");
    id
}

pub fn new_play_id() -> String {
    format!("play-{}", now_ms())
}

pub fn record(event: &TtsTelemetryEvent<'_>) {
    if let Err(err) = record_inner(event) {
        eprintln!("[Telemetry] failed to record {}: {err}", event.event);
    }
}

pub fn record_worker_line(line: &str) {
    let Some(payload) = line.strip_prefix("ALIENVOX_TELEMETRY ") else {
        return;
    };
    let payload = normalize_worker_payload(payload);
    if let Err(err) = append_telemetry_line(&payload) {
        eprintln!("[Telemetry] failed to append worker line: {err}");
    }
}

fn normalize_worker_payload(payload: &str) -> String {
    let Ok(mut value) = serde_json::from_str::<serde_json::Value>(payload) else {
        return payload.to_string();
    };
    value["sessionId"] = serde_json::json!(session_id());
    if value.get("playId").is_none() {
        value["playId"] = value
            .get("requestId")
            .cloned()
            .unwrap_or_else(|| serde_json::json!(""));
    }
    value.to_string()
}

fn record_inner(event: &TtsTelemetryEvent<'_>) -> Result<(), String> {
    let mut value = serde_json::to_value(event).map_err(|err| err.to_string())?;
    value["timestampUnixMs"] = serde_json::json!(now_ms());
    value["sessionId"] = serde_json::json!(session_id());
    value["playId"] = value["requestId"].clone();
    append_telemetry_line(&value.to_string())
}

fn append_telemetry_line(payload: &str) -> Result<(), String> {
    eprintln!("[Telemetry] {payload}");

    let path = telemetry_log_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|err| format!("failed to create {}: {err}", parent.display()))?;
    }
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|err| format!("failed to open {}: {err}", path.display()))?;
    writeln!(file, "{payload}").map_err(|err| err.to_string())
}

fn telemetry_log_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join(".telemetry")
        .join(format!("{}_AlienVox.log", session_id()))
}
