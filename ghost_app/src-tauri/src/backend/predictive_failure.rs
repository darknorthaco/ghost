//! Phase 5 — Predictive failure modeling (read-only except `predictive_fdx.jsonl`).
//! No remediation, no retries, no mutation of deploy/discovery/worker operational state.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::Path;

use super::worker_health_discovery::laplace_predictive_p;

// ── Public API types (Tauri / JSON camelCase) ─────────────────────────────

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PredictionResult {
    pub domain: String,
    pub outcome: String,
    pub predictive_p: f64,
    pub rationale: String,
    pub context: HashMap<String, String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature_key: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreflightReport {
    pub timestamp: String,
    pub predictions: Vec<PredictionResult>,
}

#[derive(Debug, Deserialize)]
struct FdxLine {
    #[serde(default)]
    phase: String,
    #[serde(default)]
    step: String,
    #[serde(default)]
    status: String,
    #[serde(default)]
    message: String,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    context: Option<Value>,
    #[serde(default)]
    details: Option<Value>,
}

#[derive(Debug, Serialize)]
struct PredictiveFdxRecord {
    timestamp: String,
    domain: String,
    outcome: String,
    predictive_p: f64,
    rationale: String,
    context: HashMap<String, String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    signature_key: Option<String>,
}

fn num_or_str_to_code(v: &Value) -> Option<String> {
    if let Some(n) = v.as_u64() {
        return Some(n.to_string());
    }
    if let Some(n) = v.as_i64() {
        return Some(n.to_string());
    }
    v.as_str().map(|s| s.chars().take(16).collect())
}

/// Exit code or HTTP status from FDX `context` / `details`; `"0"` if absent.
fn error_code_from_entry(e: &FdxLine) -> String {
    for node in [&e.context, &e.details] {
        let Some(obj) = node.as_ref().and_then(|v| v.as_object()) else {
            continue;
        };
        for key in ["exit_code", "http_status", "status_code", "httpStatus", "exitCode"] {
            if let Some(v) = obj.get(key) {
                if let Some(s) = num_or_str_to_code(v) {
                    return s;
                }
            }
        }
    }
    "0".to_string()
}

/// Deterministic signature: `{step_index}|{error_code}|{first 48 chars of error_message}`.
#[must_use]
pub fn signature_key(step_index: u32, error_code: &str, error_message: &str) -> String {
    let prefix: String = error_message.chars().take(48).collect();
    format!("{step_index}|{error_code}|{prefix}")
}

fn read_jsonl_tail(path: &Path, max_lines: usize) -> Vec<String> {
    let Ok(f) = File::open(path) else {
        return Vec::new();
    };
    let lines: Vec<String> = BufReader::new(f).lines().map_while(Result::ok).collect();
    if lines.len() <= max_lines {
        return lines;
    }
    lines[lines.len() - max_lines..].to_vec()
}

fn parse_fdx_line(s: &str) -> Option<FdxLine> {
    serde_json::from_str(s).ok()
}

fn step_index_from_entry(e: &FdxLine) -> Option<u32> {
    if let Some(ctx) = &e.context {
        if let Some(n) = ctx.get("step_index").and_then(|v| v.as_u64()) {
            return Some(n as u32);
        }
    }
    let step = &e.step;
    if let Some(rest) = step.strip_prefix("step_") {
        if let Some(idx) = rest
            .chars()
            .take_while(|c| c.is_ascii_digit())
            .collect::<String>()
            .parse::<u32>()
            .ok()
        {
            return Some(idx);
        }
    }
    None
}

fn is_deploy_related(e: &FdxLine) -> bool {
    matches!(e.phase.as_str(), "deploy" | "pre_scan" | "deploy_legacy")
        && (e.step.contains("step_")
            || e
                .context
                .as_ref()
                .and_then(|c| c.get("step_index"))
                .is_some())
}

/// Laplace p from success/failure counts (failure-oriented numerator).
#[must_use]
pub fn laplace_failure_p(successes: u32, failures: u32) -> f64 {
    (failures as f64 + 1.0) / (successes as f64 + failures as f64 + 2.0)
}

#[must_use]
pub fn classify_failure_p(p: f64) -> &'static str {
    if p > 0.70 {
        "likely_fail"
    } else if p < 0.30 {
        "likely_pass"
    } else {
        "uncertain"
    }
}

fn ctx_num(pairs: &[(&str, String)]) -> HashMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| (k.to_string(), v.clone()))
        .collect()
}

/// Deploy step forecasts from last N `deploy_fdx` lines (N = 20, Phase 4 parity).
#[must_use]
pub fn predict_deploy_steps(ghost_root: &Path, tail_lines: usize) -> Vec<PredictionResult> {
    let path = ghost_root.join("logs").join("deploy_fdx.jsonl");
    let raw = read_jsonl_tail(&path, tail_lines);
    let mut by_step_sig: HashMap<u32, HashMap<String, (u32, u32)>> = HashMap::new();

    for line in &raw {
        let Some(e) = parse_fdx_line(line) else { continue };
        if !is_deploy_related(&e) {
            continue;
        }
        let Some(si) = step_index_from_entry(&e) else { continue };
        if si > 9 {
            continue;
        }
        let msg = e
            .error
            .clone()
            .unwrap_or_else(|| e.message.clone());
        let code = error_code_from_entry(&e);
        let key = signature_key(si, &code, &msg);
        let ent = by_step_sig.entry(si).or_default();
        let counts = ent.entry(key).or_insert((0, 0));
        if e.status == "error" {
            counts.1 += 1;
        } else if e.status == "success" {
            counts.0 += 1;
        }
    }

    let mut out = Vec::new();
    for step in 0u32..=9u32 {
        let Some(sigs) = by_step_sig.get(&step) else {
            continue;
        };
        let mut worst_p = 0.0_f64;
        let mut worst_key: Option<String> = None;
        let mut rationale_parts = Vec::new();
        for (sig, (s, f)) in sigs.iter() {
            let p = laplace_failure_p(*s, *f);
            if p > worst_p {
                worst_p = p;
                worst_key = Some((*sig).clone());
            }
            rationale_parts.push(format!("{}: s={} f={} p={:.2}", sig, s, f, p));
        }
        let outcome = classify_failure_p(worst_p).to_string();
        out.push(PredictionResult {
            domain: "deploy".to_string(),
            outcome,
            predictive_p: worst_p,
            rationale: format!(
                "step {} worst-case Laplace over signature groups: {}",
                step,
                rationale_parts.join("; ")
            ),
            context: ctx_num(&[
                ("stepIndex", step.to_string()),
                ("signatureGroups", sigs.len().to_string()),
            ]),
            signature_key: worst_key,
        });
    }
    out.sort_by(|a, b| {
        b.predictive_p
            .partial_cmp(&a.predictive_p)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    out
}

fn integrity_warnings_total(ghost_root: &Path) -> u32 {
    let health_lines = read_jsonl_tail(&ghost_root.join("logs").join("worker_health_fdx.jsonl"), 40);
    let mut total = 0u32;
    for line in &health_lines {
        let Ok(v) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        if v.get("phase").and_then(|x| x.as_str()) != Some("discovery_integrity") {
            continue;
        }
        if v.get("step").and_then(|x| x.as_str()) != Some("integrity_check") {
            continue;
        }
        if let Some(arr) = v
            .get("details")
            .and_then(|d| d.get("issues"))
            .and_then(|x| x.as_array())
        {
            total += arr.len() as u32;
        }
    }
    total
}

fn recent_discovery_failures(ghost_root: &Path, tail: usize) -> u32 {
    let lines = read_jsonl_tail(&ghost_root.join("logs").join("discovery_fdx.jsonl"), tail);
    let mut n = 0u32;
    for line in &lines {
        let Ok(v) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        let status = v.get("status").and_then(|s| s.as_str()).unwrap_or("");
        if status == "error" {
            n += 1;
            continue;
        }
        if v.get("phase").and_then(|p| p.as_str()) == Some("discovery_integrity")
            && v.get("step").and_then(|s| s.as_str()) == Some("retrieval_fallback")
            && status == "error"
        {
            n += 1;
        }
    }
    n
}

/// Discovery forecast using worker outcomes, integrity stock, and `discovery_fdx` tail.
#[must_use]
pub fn predict_discovery(
    ghost_root: &Path,
    worker_predictions: &[PredictionResult],
) -> PredictionResult {
    let workers: Vec<_> = worker_predictions
        .iter()
        .filter(|p| p.domain == "worker")
        .collect();
    let total = workers.len() as f64;
    let down_count = workers
        .iter()
        .filter(|p| p.outcome == "likely_down")
        .count();
    let down = down_count as f64;
    let offline_ratio = if total < 1.0 {
        0.0
    } else {
        down / total
    };

    let integrity_warnings_count = integrity_warnings_total(ghost_root);
    let recent_fail = recent_discovery_failures(ghost_root, 30);

    let (outcome, predictive_p, rationale) = if offline_ratio > 0.75
        || integrity_warnings_count > 3
        || recent_fail >= 2
    {
        (
            "likely_empty_discovery".to_string(),
            offline_ratio.max(0.85),
            format!(
                "offline_ratio={:.2} (likely_down/total), integrity_warnings={}, recent_discovery_failures={}",
                offline_ratio, integrity_warnings_count, recent_fail
            ),
        )
    } else if offline_ratio >= 0.25 && offline_ratio <= 0.75 {
        (
            "likely_partial_discovery".to_string(),
            0.5 + offline_ratio * 0.2,
            format!(
                "offline_ratio in [0.25,0.75]; integrity_warnings={}",
                integrity_warnings_count
            ),
        )
    } else if offline_ratio < 0.25 && integrity_warnings_count == 0 {
        (
            "likely_full_discovery".to_string(),
            0.2,
            "Low offline ratio and no integrity warnings in recent worker_health tail.".to_string(),
        )
    } else {
        (
            "likely_partial_discovery".to_string(),
            0.45,
            format!(
                "Fallback partial: offline_ratio={:.2}, integrity_warnings={}",
                offline_ratio, integrity_warnings_count
            ),
        )
    };

    PredictionResult {
        domain: "discovery".to_string(),
        outcome,
        predictive_p,
        rationale,
        context: ctx_num(&[
            ("offlineRatio", format!("{:.4}", offline_ratio)),
            ("totalWorkersScored", workers.len().to_string()),
            ("likelyDownCount", down_count.to_string()),
            ("integrityWarningsCount", integrity_warnings_count.to_string()),
            ("recentDiscoveryFailures", recent_fail.to_string()),
        ]),
        signature_key: None,
    }
}

fn offline_signal_count_for_worker(ghost_root: &Path, worker_id: &str, tail: usize) -> u32 {
    let path = ghost_root.join("retrieval").join("worker_signals.jsonl");
    let raw = read_jsonl_tail(&path, tail);
    let mut n = 0u32;
    for line in &raw {
        let Ok(v) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        if v.get("worker_id").and_then(|x| x.as_str()) != Some(worker_id) {
            continue;
        }
        let src = v.get("source").and_then(|s| s.as_str()).unwrap_or("");
        if src.contains("offline") {
            n += 1;
        }
    }
    n
}

/// Worker rows: `predictive_p` is **failure probability** (1 − Laplace success from Phase 4).
#[must_use]
pub fn predict_worker_availability(ghost_root: &Path) -> Vec<PredictionResult> {
    let path = ghost_root.join("retrieval").join("worker_signals.jsonl");
    let raw = read_jsonl_tail(&path, 60);
    let mut ids: Vec<String> = Vec::new();
    for line in &raw {
        if let Ok(v) = serde_json::from_str::<Value>(line) {
            if let Some(w) = v.get("worker_id").and_then(|x| x.as_str()) {
                if !ids.contains(&w.to_string()) {
                    ids.push(w.to_string());
                }
            }
        }
    }

    let health_tail = read_jsonl_tail(&ghost_root.join("logs").join("worker_health_fdx.jsonl"), 40);
    let mut readiness_by_worker: HashMap<String, bool> = HashMap::new();
    for line in &health_tail {
        if let Ok(v) = serde_json::from_str::<Value>(line) {
            if v.get("step").and_then(|s| s.as_str()) != Some("predictive_availability") {
                continue;
            }
            let wid = v
                .get("details")
                .and_then(|d| d.get("worker_id"))
                .and_then(|x| x.as_str())
                .unwrap_or("");
            if wid.is_empty() {
                continue;
            }
            let probe = v
                .get("details")
                .and_then(|d| d.get("readiness_probe_success"))
                .and_then(|x| x.as_bool())
                .unwrap_or(false);
            readiness_by_worker.insert(wid.to_string(), probe);
        }
    }

    let mut out = Vec::new();
    for wid in ids {
        let success_p = laplace_predictive_p(ghost_root, &wid);
        let failure_p = (1.0 - success_p).clamp(0.0, 1.0);
        let probe_ok = *readiness_by_worker.get(&wid).unwrap_or(&false);
        let offline_n = offline_signal_count_for_worker(ghost_root, &wid, 40);
        let repeated_offline = offline_n >= 2;

        let outcome = if failure_p > 0.70 || repeated_offline {
            "likely_down"
        } else if failure_p < 0.30 && probe_ok {
            "likely_up"
        } else {
            "uncertain"
        };

        out.push(PredictionResult {
            domain: "worker".to_string(),
            outcome: outcome.to_string(),
            predictive_p: failure_p,
            rationale: format!(
                "failure_p={:.2} (1−Laplace success); readiness_probe_ok={}; offline_signal_hits={}",
                failure_p, probe_ok, offline_n
            ),
            context: ctx_num(&[
                ("workerId", wid.clone()),
                ("failureP", format!("{:.4}", failure_p)),
                ("laplaceSuccessP", format!("{:.4}", success_p)),
                ("readinessProbeSuccessLastSeen", probe_ok.to_string()),
                ("offlineSignalCount", offline_n.to_string()),
            ]),
            signature_key: None,
        });
    }
    out.sort_by(|a, b| {
        b.predictive_p
            .partial_cmp(&a.predictive_p)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    out
}

fn failure_rate(slice: &[bool]) -> f64 {
    if slice.is_empty() {
        return 0.0;
    }
    let f = slice.iter().filter(|x| !**x).count() as f64;
    f / slice.len() as f64
}

#[must_use]
pub fn predict_routing_stability(ghost_root: &Path) -> PredictionResult {
    let path = ghost_root.join("retrieval").join("worker_signals.jsonl");
    let raw = read_jsonl_tail(&path, 80);
    let mut by_worker: HashMap<String, Vec<bool>> = HashMap::new();
    for line in &raw {
        if let Ok(v) = serde_json::from_str::<Value>(line) {
            let Some(wid) = v.get("worker_id").and_then(|x| x.as_str()) else {
                continue;
            };
            let ok = v.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
            by_worker.entry(wid.to_string()).or_default().push(ok);
        }
    }

    let mut max_transitions = 0u32;
    let mut worst_worker = String::new();
    let mut workers_repeated_fail = 0u32;
    let mut workers_high_fluctuation = 0u32;

    for (wid, seq) in &by_worker {
        if seq.len() < 2 {
            continue;
        }
        let mut t = 0u32;
        for w in seq.windows(2) {
            if w[0] != w[1] {
                t += 1;
            }
        }
        if t > max_transitions {
            max_transitions = t;
            worst_worker = wid.clone();
        }
        let fails = seq.iter().filter(|x| !**x).count() as u32;
        if fails >= 3 {
            workers_repeated_fail += 1;
        }
        let tail: Vec<bool> = seq.iter().rev().take(10).copied().collect();
        let tail: Vec<bool> = tail.into_iter().rev().collect();
        if tail.len() >= 6 {
            let mid = tail.len() / 2;
            let r1 = failure_rate(&tail[..mid]);
            let r2 = failure_rate(&tail[mid..]);
            if (r1 - r2).abs() > 0.4 {
                workers_high_fluctuation += 1;
            }
        }
    }

    let oscillating = max_transitions >= 4;
    let repeated_timeouts = workers_repeated_fail >= 2;
    let fluctuation_unstable = workers_high_fluctuation >= 1;

    let (outcome, predictive_p, rationale) = if oscillating || fluctuation_unstable {
        (
            "unstable",
            0.78_f64,
            format!(
                "oscillating_ok_fail max_transitions={} fluctuating_workers={} worst={}",
                max_transitions, workers_high_fluctuation, worst_worker
            ),
        )
    } else if repeated_timeouts {
        (
            "degraded",
            0.62_f64,
            format!(
                "{} workers with 3+ failed signals; possible timeouts/repeated errors.",
                workers_repeated_fail
            ),
        )
    } else {
        (
            "stable",
            0.22_f64,
            "No strong oscillation or failure streaks in worker_signals tail.".to_string(),
        )
    };

    PredictionResult {
        domain: "routing".to_string(),
        outcome: outcome.to_string(),
        predictive_p,
        rationale,
        context: ctx_num(&[
            ("maxTransitions", max_transitions.to_string()),
            ("worstWorkerId", worst_worker.clone()),
            ("workersRepeatedFailures", workers_repeated_fail.to_string()),
            ("workersFluctuationGt04", workers_high_fluctuation.to_string()),
        ]),
        signature_key: None,
    }
}

fn append_predictive_fdx(ghost_root: &Path, rec: &PredictiveFdxRecord) {
    let dir = ghost_root.join("logs");
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    let path = dir.join("predictive_fdx.jsonl");
    let line = match serde_json::to_string(rec) {
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

fn log_prediction(ghost_root: &Path, p: &PredictionResult) {
    append_predictive_fdx(
        ghost_root,
        &PredictiveFdxRecord {
            timestamp: chrono::Utc::now().to_rfc3339(),
            domain: p.domain.clone(),
            outcome: p.outcome.clone(),
            predictive_p: p.predictive_p,
            rationale: p.rationale.clone(),
            context: p.context.clone(),
            signature_key: p.signature_key.clone(),
        },
    );
}

/// Deploy → workers → discovery (uses workers) → routing. Appends `predictive_fdx.jsonl` only.
#[must_use]
pub fn run_preflight_and_log(ghost_root: &Path) -> PreflightReport {
    let mut predictions: Vec<PredictionResult> = Vec::new();

    let deploy = predict_deploy_steps(ghost_root, 20);
    for p in &deploy {
        log_prediction(ghost_root, p);
    }
    predictions.extend(deploy);

    let workers = predict_worker_availability(ghost_root);
    for p in &workers {
        log_prediction(ghost_root, p);
    }
    predictions.extend(workers.clone());

    let disc = predict_discovery(ghost_root, &workers);
    log_prediction(ghost_root, &disc);
    predictions.push(disc);

    let route = predict_routing_stability(ghost_root);
    log_prediction(ghost_root, &route);
    predictions.push(route);

    let report = PreflightReport {
        timestamp: chrono::Utc::now().to_rfc3339(),
        predictions,
    };

    let mut summary_ctx = HashMap::new();
    summary_ctx.insert(
        "predictionCount".to_string(),
        report.predictions.len().to_string(),
    );
    append_predictive_fdx(
        ghost_root,
        &PredictiveFdxRecord {
            timestamp: report.timestamp.clone(),
            domain: "preflight".to_string(),
            outcome: "summary".to_string(),
            predictive_p: 0.0,
            rationale: format!("{} prediction rows emitted", report.predictions.len()),
            context: summary_ctx,
            signature_key: None,
        },
    );

    report
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signature_key_uses_exit_style_code() {
        let k = signature_key(3, "127", "connection refused");
        assert_eq!(k, "3|127|connection refused");
    }

    #[test]
    fn laplace_failure_extremes() {
        assert!(laplace_failure_p(0, 5) > 0.7);
        assert!(laplace_failure_p(5, 0) < 0.3);
    }
}
