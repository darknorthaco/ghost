//! Phase 4 — Worker health scoring, discovery integrity, predictive availability,
//! retrieval-driven discovery fallback, and `worker_health_fdx.jsonl` audit lines.
//! All local, deterministic, bounded (at most one extra discovery window).

use super::discovery::discover_single_window;
use super::discovery::DiscoveredManifest;
use super::discovery::DISCOVERY_PORT;
use super::discovery_log::{DependencyInitEntry, DiscoveryLog, DiscoveryLogBuilder, FullDeployLogEntry};
use super::fdx_log::{self, FdxEntry};
use super::fdx_retrieval::load_persisted_cases;
use serde::Deserialize;
use serde_json::json;
use std::collections::BTreeMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

#[derive(Debug, Clone, Deserialize)]
struct WorkerSignalLine {
    worker_id: String,
    ok: bool,
    #[serde(default)]
    #[allow(dead_code)]
    latency_ms: Option<u64>,
}

fn retrieval_dir(ghost_root: &Path) -> std::path::PathBuf {
    ghost_root.join("retrieval")
}

fn worker_signals_path(ghost_root: &Path) -> std::path::PathBuf {
    retrieval_dir(ghost_root).join("worker_signals.jsonl")
}

/// Laplace-smoothed P(success) per worker from `worker_signals.jsonl` (same schema as Python).
pub fn laplace_predictive_p(ghost_root: &Path, worker_id: &str) -> f64 {
    let path = worker_signals_path(ghost_root);
    let Ok(content) = std::fs::read_to_string(&path) else {
        return 0.55;
    };
    let mut ok = 0u32;
    let mut bad = 0u32;
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(sig): Result<WorkerSignalLine, _> = serde_json::from_str(line) else {
            continue;
        };
        if sig.worker_id != worker_id {
            continue;
        }
        if sig.ok {
            ok += 1;
        } else {
            bad += 1;
        }
    }
    let n = ok + bad;
    if n == 0 {
        0.55
    } else {
        (ok as f64 + 1.0) / (n as f64 + 2.0)
    }
}

/// Append one signal (JSONL) — compatible with `ghost_orchestrator.reliability_store`.
pub fn append_worker_signal(
    ghost_root: &Path,
    worker_id: &str,
    ok: bool,
    latency_ms: Option<u64>,
    source: &str,
) {
    let _ = std::fs::create_dir_all(retrieval_dir(ghost_root));
    let path = worker_signals_path(ghost_root);
    let line = serde_json::json!({
        "worker_id": worker_id,
        "ok": ok,
        "latency_ms": latency_ms,
        "source": source,
    });
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{}", line);
    }
}

/// If remediation history suggests an extended discovery window helped, return bounded extended ms.
pub fn extended_discovery_timeout_ms(ghost_root: &Path, base_ms: u64) -> Option<u64> {
    let cases = load_persisted_cases(ghost_root);
    let mut succ = 0i32;
    let mut fail = 0i32;
    for c in &cases {
        let es = c.error_signature.to_lowercase();
        let ds = c.deploy_step.to_lowercase();
        if !es.contains("discover")
            && !es.contains("8095")
            && !es.contains("worker")
            && !es.contains("udp")
            && !ds.contains("lan")
        {
            continue;
        }
        match c.outcome.as_str() {
            "success" => succ += 1,
            "failure" => fail += 1,
            _ => {}
        }
    }
    if succ <= fail {
        return None;
    }
    let ext = base_ms.saturating_mul(3).saturating_div(2).clamp(base_ms.saturating_add(500), 120_000);
    Some(ext)
}

#[derive(Debug, Clone)]
pub struct IntegrityReport {
    pub issues: Vec<String>,
    #[allow(dead_code)]
    pub duplicate_worker_ids: Vec<String>,
}

/// Deterministic dedupe (first wins in `worker_id` sort order), integrity checks, FDX.
pub fn dedupe_and_check_integrity(
    ghost_root: &Path,
    manifests: Vec<DiscoveredManifest>,
) -> (Vec<DiscoveredManifest>, IntegrityReport) {
    let mut issues = Vec::new();
    let mut duplicate_worker_ids = Vec::new();
    let manifest_in = manifests.len();
    let mut by_id: BTreeMap<String, DiscoveredManifest> = BTreeMap::new();

    let mut sorted: Vec<_> = manifests.into_iter().collect();
    sorted.sort_by(|a, b| a.manifest.worker_id.cmp(&b.manifest.worker_id));

    for m in sorted {
        let id = m.manifest.worker_id.clone();
        if m.port == 0 {
            issues.push(format!("worker {id}: invalid port 0"));
        }
        if !m.signature_verified {
            issues.push(format!("worker {id}: signature not verified"));
        }
        if by_id.contains_key(&id) {
            duplicate_worker_ids.push(id.clone());
            issues.push(format!("worker {id}: duplicate manifest in batch (dropped)"));
            continue;
        }
        by_id.insert(id, m);
    }

    let out: Vec<DiscoveredManifest> = by_id.into_values().collect();

    fdx_log::append_discovery(
        ghost_root,
        &FdxEntry::new(
            "discovery_integrity",
            "integrity_check",
            if issues.is_empty() { "success" } else { "info" },
            "Discovery integrity pass",
        )
        .details(json!({
            "manifest_in": manifest_in,
            "manifest_out": out.len(),
            "issues": &issues,
            "duplicate_worker_ids": &duplicate_worker_ids,
        })),
    );

    (
        out,
        IntegrityReport {
            issues,
            duplicate_worker_ids,
        },
    )
}

/// Score 0–100 from signature, port, and predictive Laplace from `worker_signals.jsonl`.
pub fn worker_health_score(ghost_root: &Path, m: &DiscoveredManifest) -> u32 {
    let mut s: u32 = 0;
    if m.signature_verified {
        s += 40;
    } else {
        s += 15;
    }
    if m.port > 0 {
        s += 25;
    }
    if !m.manifest.worker_id.is_empty() {
        s += 10;
    }
    let p = laplace_predictive_p(ghost_root, &m.manifest.worker_id);
    s += ((p * 25.0).round() as u32).min(25);
    s.min(100)
}

pub fn log_worker_health_for_manifests(ghost_root: &Path, manifests: &[DiscoveredManifest]) {
    for m in manifests {
        let score = worker_health_score(ghost_root, m);
        let p = laplace_predictive_p(ghost_root, &m.manifest.worker_id);
        fdx_log::append_worker_health(
            ghost_root,
            &FdxEntry::new(
                "worker_health",
                "health_score",
                "info",
                "Worker health score (Phase 4)",
            )
            .details(json!({
                "worker_id": m.manifest.worker_id,
                "score_0_100": score,
                "signature_verified": m.signature_verified,
                "port": m.port,
                "predictive_p": p,
                "source_ip": m.source_ip,
            })),
        );
    }
}

pub fn log_predictive_availability_batch(
    ghost_root: &Path,
    worker_ids: &[String],
    probe_ok: bool,
) {
    for wid in worker_ids {
        let label = predictive_availability_label(ghost_root, wid, probe_ok);
        fdx_log::append_worker_health(
            ghost_root,
            &FdxEntry::new(
                "worker_health",
                "predictive_availability",
                "info",
                "Predictive availability (Laplace + readiness probe)",
            )
            .details(json!({
                "worker_id": wid,
                "label": label,
                "readiness_probe_success": probe_ok,
                "predictive_p": laplace_predictive_p(ghost_root, wid),
            })),
        );
    }
}

/// Predictive label for FDX: deterministic from Laplace + readiness.
fn predictive_availability_label(ghost_root: &Path, worker_id: &str, probe_ok: bool) -> &'static str {
    let p = laplace_predictive_p(ghost_root, worker_id);
    if !probe_ok && p < 0.45 {
        "likely_down"
    } else if probe_ok && p > 0.65 {
        "likely_up"
    } else {
        "uncertain"
    }
}

/// Pre-scan discovery: optional retrieval-driven second window if first pass is empty.
pub fn discover_with_integrity_and_fallback(
    ghost_root: &Path,
    broadcast_addrs: &[String],
    total_timeout_ms: u64,
    early_exit_on_first_worker: bool,
    dependency_init_entries: Vec<DependencyInitEntry>,
    full_deploy_entries: Vec<FullDeployLogEntry>,
) -> (Vec<DiscoveredManifest>, DiscoveryLog) {
    fdx_log::append_worker_health(
        ghost_root,
        &FdxEntry::new("worker_health", "discovery_session", "start", "Discovery with integrity + fallback gate")
            .details(json!({
                "total_timeout_ms": total_timeout_ms,
                "early_exit": early_exit_on_first_worker,
            })),
    );

    let mut interfaces: Vec<String> = vec!["127.0.0.1".to_string()];
    interfaces.extend(broadcast_addrs.iter().cloned());
    let mut log = DiscoveryLogBuilder::new(interfaces, DISCOVERY_PORT);
    for e in dependency_init_entries.clone() {
        log.add_dependency_init_entry(e);
    }
    log.add_full_deploy_entries(full_deploy_entries.clone());
    log.push_raw("Single-window discovery (127.0.0.1 + broadcast)…");

    let m1 = discover_single_window(
        broadcast_addrs,
        total_timeout_ms,
        early_exit_on_first_worker,
        Some(&mut log),
    );
    log.push_raw(&format!("Done: {} worker(s) discovered (pass 1)", m1.len()));

    let (mut merged, report) = dedupe_and_check_integrity(ghost_root, m1);
    log_worker_health_for_manifests(ghost_root, &merged);

    if merged.is_empty() {
        if let Some(ext_ms) = extended_discovery_timeout_ms(ghost_root, total_timeout_ms) {
            fdx_log::append_worker_health(
                ghost_root,
                &FdxEntry::new(
                    "worker_health",
                    "retrieval_fallback",
                    "success",
                    "Retrieval-driven extended discovery window",
                )
                .details(json!({
                    "base_timeout_ms": total_timeout_ms,
                    "extended_timeout_ms": ext_ms,
                    "rationale": "remediation_cases.jsonl shows more successes than failures for discovery-adjacent errors",
                })),
            );
            fdx_log::append_discovery(
                ghost_root,
                &FdxEntry::new(
                    "discovery_integrity",
                    "retrieval_fallback",
                    "start",
                    "Second discovery window (no early exit)",
                )
                .details(json!({ "timeout_ms": ext_ms })),
            );

            log.push_raw(&format!(
                "Retrieval-driven fallback: second window {} ms (no early exit)",
                ext_ms
            ));
            let m2 = discover_single_window(broadcast_addrs, ext_ms, false, Some(&mut log));
            log.push_raw(&format!("Done: {} worker(s) discovered (pass 2)", m2.len()));

            let (m2, _r2) = dedupe_and_check_integrity(ghost_root, m2);
            merged = merge_by_worker_id(merged, m2);
            log_worker_health_for_manifests(ghost_root, &merged);
            fdx_log::append_discovery(
                ghost_root,
                &FdxEntry::new(
                    "discovery_integrity",
                    "retrieval_fallback",
                    if merged.is_empty() { "error" } else { "success" },
                    "Second discovery window complete",
                )
                .details(json!({ "worker_count": merged.len() })),
            );
        } else {
            fdx_log::append_worker_health(
                ghost_root,
                &FdxEntry::new(
                    "worker_health",
                    "retrieval_fallback",
                    "info",
                    "No retrieval-driven fallback (insufficient positive remediation history)",
                ),
            );
        }
    }

    for m in &merged {
        append_worker_signal(
            ghost_root,
            &m.manifest.worker_id,
            true,
            None,
            "discovery_phase4",
        );
    }

    fdx_log::append_worker_health(
        ghost_root,
        &FdxEntry::new("worker_health", "discovery_session", "success", "Discovery session complete")
            .details(json!({
                "worker_count": merged.len(),
                "first_pass_integrity_issue_count": report.issues.len(),
            })),
    );

    let worker_count = merged.len();
    let discovery_log = log.build(worker_count);
    (merged, discovery_log)
}

fn merge_by_worker_id(
    a: Vec<DiscoveredManifest>,
    b: Vec<DiscoveredManifest>,
) -> Vec<DiscoveredManifest> {
    let mut map: BTreeMap<String, DiscoveredManifest> = BTreeMap::new();
    for m in a.into_iter().chain(b) {
        let id = m.manifest.worker_id.clone();
        map.entry(id).or_insert(m);
    }
    map.into_values().collect()
}

/// Manual LAN scan path: same integrity + optional fallback (empty deps for log builder).
pub fn manual_discover_with_integrity_and_fallback(
    ghost_root: &Path,
    broadcast_addrs: &[String],
    total_timeout_ms: u64,
    early_exit_on_first_worker: bool,
) -> Vec<DiscoveredManifest> {
    let (m, _) = discover_with_integrity_and_fallback(
        ghost_root,
        broadcast_addrs,
        total_timeout_ms,
        early_exit_on_first_worker,
        Vec::new(),
        Vec::new(),
    );
    m
}
