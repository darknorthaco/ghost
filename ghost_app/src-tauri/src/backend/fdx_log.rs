//! FDX — structured JSONL observability (deploy / discovery / installer streams).
//! Logs live under `~/.ghost/logs/` (POSIX) or `%USERPROFILE%\.ghost\logs\` (Windows).

use serde::Serialize;
use serde_json::Value;
use std::path::Path;

#[derive(Serialize, Clone, Debug)]
pub struct FdxEntry {
    pub timestamp: String,
    pub phase: String,
    pub step: String,
    pub status: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<Value>,
}

impl FdxEntry {
    pub fn new(
        phase: impl Into<String>,
        step: impl Into<String>,
        status: impl Into<String>,
        message: impl Into<String>,
    ) -> Self {
        Self {
            timestamp: chrono::Utc::now().to_rfc3339(),
            phase: phase.into(),
            step: step.into(),
            status: status.into(),
            message: message.into(),
            details: None,
            error: None,
            context: None,
        }
    }

    pub fn details(mut self, v: Value) -> Self {
        self.details = Some(v);
        self
    }

    pub fn error(mut self, e: impl Into<String>) -> Self {
        self.error = Some(e.into());
        self
    }

    pub fn context(mut self, v: Value) -> Self {
        self.context = Some(v);
        self
    }
}

fn append_line(ghost_root: &Path, filename: &str, entry: &FdxEntry) {
    let dir = ghost_root.join("logs");
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    let path = dir.join(filename);
    let line = match serde_json::to_string(entry) {
        Ok(s) => s,
        Err(_) => return,
    };
    use std::io::Write;
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let _ = writeln!(f, "{}", line);
    }
}

pub fn append_deploy(ghost_root: &Path, entry: &FdxEntry) {
    append_line(ghost_root, "deploy_fdx.jsonl", entry);
}

pub fn append_discovery(ghost_root: &Path, entry: &FdxEntry) {
    append_line(ghost_root, "discovery_fdx.jsonl", entry);
}

/// Phase 4 — worker health scoring, predictive signals, discovery integrity audit.
pub fn append_worker_health(ghost_root: &Path, entry: &FdxEntry) {
    append_line(ghost_root, "worker_health_fdx.jsonl", entry);
}
