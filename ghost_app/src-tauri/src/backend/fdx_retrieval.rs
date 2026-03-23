//! FDX-backed retrieval corpus for deploy remediation (DKA Phase 3).
//! Deterministic ranking: same files + same query → same strategy choice.
//! No network; no ML — structured overlap + Jaccard token similarity on error text.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashSet};
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};

/// One line from any FDX JSONL stream (tolerant of missing fields).
#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)]
pub struct FdxRecord {
    pub timestamp: String,
    pub phase: String,
    pub step: String,
    pub status: String,
    pub message: String,
    #[serde(default)]
    pub details: Option<Value>,
    #[serde(default)]
    pub error: Option<String>,
    #[serde(default)]
    pub context: Option<Value>,
}

/// Persisted remediation outcome for retrieval (append-only under ~/.ghost/retrieval/).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RemediationCaseRecord {
    pub case_id: String,
    pub created_at: String,
    pub error_signature: String,
    pub deploy_step: String,
    #[serde(default)]
    pub deploy_step_index: Option<u32>,
    pub strategy_attempted: String,
    pub outcome: String,
    pub os_family: String,
    #[serde(default)]
    pub python_version_hint: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum RemediationStrategy {
    /// Re-run the same deploy step once (no side effects).
    RetryStep,
    /// `pip install --upgrade pip setuptools wheel` in venv, then caller may retry step.
    PipToolchainRefresh,
    /// Logged decision only; no automated mutation (e.g. port in use).
    DiagnosticOnly,
}

impl RemediationStrategy {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::RetryStep => "retry_step",
            Self::PipToolchainRefresh => "pip_toolchain_refresh",
            Self::DiagnosticOnly => "diagnostic_only",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "retry_step" => Some(Self::RetryStep),
            "pip_toolchain_refresh" => Some(Self::PipToolchainRefresh),
            "diagnostic_only" => Some(Self::DiagnosticOnly),
            _ => None,
        }
    }
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct RankedCandidate {
    pub case_id: String,
    pub similarity: f64,
    pub success_rate: f64,
    pub strategy: RemediationStrategy,
    pub weight: f64,
}

#[derive(Debug, Clone)]
pub struct RetrievalDecision {
    pub chosen: RemediationStrategy,
    pub rationale: String,
    pub retrieved_case_ids: Vec<String>,
    pub candidates: Vec<RankedCandidate>,
}

fn retrieval_dir(ghost_root: &Path) -> PathBuf {
    ghost_root.join("retrieval")
}

pub fn cases_path(ghost_root: &Path) -> PathBuf {
    retrieval_dir(ghost_root).join("remediation_cases.jsonl")
}

fn read_jsonl<T: for<'de> Deserialize<'de>>(path: &Path) -> Vec<T> {
    let Ok(f) = File::open(path) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for line in BufReader::new(f).lines().map_while(Result::ok) {
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        if let Ok(v) = serde_json::from_str::<T>(t) {
            out.push(v);
        }
    }
    out
}

fn load_fdx_path(path: &Path) -> Vec<FdxRecord> {
    read_jsonl(path)
}

/// Load deploy, discovery, and installer FDX streams from `ghost_root/logs/`.
pub fn load_fdx_corpus(ghost_root: &Path) -> Vec<FdxRecord> {
    let logs = ghost_root.join("logs");
    let mut all = Vec::new();
    for name in ["deploy_fdx.jsonl", "discovery_fdx.jsonl", "installer_fdx.jsonl"] {
        let p = logs.join(name);
        all.extend(load_fdx_path(&p));
    }
    all
}

pub fn load_persisted_cases(ghost_root: &Path) -> Vec<RemediationCaseRecord> {
    read_jsonl(&cases_path(ghost_root))
}

pub fn normalize_error_signature(error: &str) -> String {
    error
        .chars()
        .map(|c| if c.is_ascii_whitespace() { ' ' } else { c })
        .collect::<String>()
        .to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn token_set(s: &str) -> HashSet<String> {
    normalize_error_signature(s)
        .split_whitespace()
        .map(|w| w.to_string())
        .filter(|w| w.len() > 1)
        .collect()
}

/// Jaccard similarity on word tokens; deterministic.
pub fn token_similarity(a: &str, b: &str) -> f64 {
    let sa = token_set(a);
    let sb = token_set(b);
    if sa.is_empty() && sb.is_empty() {
        return 1.0;
    }
    if sa.is_empty() || sb.is_empty() {
        return 0.0;
    }
    let inter = sa.intersection(&sb).count();
    let uni = sa.union(&sb).count();
    if uni == 0 {
        0.0
    } else {
        inter as f64 / uni as f64
    }
}

fn step_match_bonus(query_step: &str, record: &RemediationCaseRecord) -> f64 {
    if record.deploy_step == query_step {
        0.25
    } else {
        0.0
    }
}

fn os_match_bonus(os_family: &str, record: &RemediationCaseRecord) -> f64 {
    if record.os_family == os_family {
        0.15
    } else {
        0.0
    }
}

/// Success rate from persisted cases for a strategy (Laplace-smoothed).
fn strategy_success_rate(cases: &[RemediationCaseRecord], strategy: RemediationStrategy) -> f64 {
    let s = strategy.as_str();
    let mut ok = 0u32;
    let mut bad = 0u32;
    for c in cases {
        if c.strategy_attempted != s {
            continue;
        }
        match c.outcome.as_str() {
            "success" => ok += 1,
            "failure" => bad += 1,
            _ => {}
        }
    }
    let n = ok + bad;
    if n == 0 {
        0.55
    } else {
        (ok as f64 + 1.0) / (n as f64 + 2.0)
    }
}

/// Aggregate similarity of `query_error` to historical errors in FDX (error status lines).
fn fdx_error_similarity(fdx: &[FdxRecord], query_error: &str) -> f64 {
    let mut best = 0.0_f64;
    for r in fdx {
        if r.status != "error" {
            continue;
        }
        let combined = format!("{} {}", r.error.as_deref().unwrap_or(""), r.message);
        let sim = token_similarity(query_error, &combined);
        if sim > best {
            best = sim;
        }
    }
    best
}

/// Allowed strategies per deploy step index (bounded automation).
fn allowed_strategies(step_index: usize, error_lower: &str) -> Vec<RemediationStrategy> {
    if error_lower.contains("address already in use")
        || error_lower.contains("only one usage")
        || (error_lower.contains("8765") && error_lower.contains("bind"))
    {
        return vec![RemediationStrategy::DiagnosticOnly];
    }
    let mut v = vec![RemediationStrategy::RetryStep];
    if matches!(step_index, 1 | 2) {
        let pipish = error_lower.contains("pip")
            || error_lower.contains("network")
            || error_lower.contains("timeout")
            || error_lower.contains("resolution")
            || error_lower.contains("ssl")
            || error_lower.contains("certificate");
        if pipish {
            v.push(RemediationStrategy::PipToolchainRefresh);
        }
    }
    v.sort();
    v.dedup();
    v
}

/// Deterministic retrieval + strategy choice from local FDX + persisted cases.
pub fn decide_remediation(
    ghost_root: &Path,
    step_index: usize,
    deploy_step_key: &str,
    error_message: &str,
    os_family: &str,
) -> RetrievalDecision {
    let fdx = load_fdx_corpus(ghost_root);
    let persisted = load_persisted_cases(ghost_root);
    let query = normalize_error_signature(error_message);
    let err_l = error_message.to_lowercase();
    let allowed = allowed_strategies(step_index, &err_l);

    let fdx_sim = fdx_error_similarity(&fdx, &query);

    let mut candidates: Vec<RankedCandidate> = Vec::new();

    for rec in &persisted {
        let Some(strat) = RemediationStrategy::parse(&rec.strategy_attempted) else {
            continue;
        };
        if !allowed.contains(&strat) {
            continue;
        }
        let sim = token_similarity(&query, &rec.error_signature);
        let sim = sim + step_match_bonus(deploy_step_key, rec) + os_match_bonus(os_family, rec);
        let sim = (sim + fdx_sim * 0.35).min(1.5);
        let sr = strategy_success_rate(&persisted, strat);
        let weight = sim * sr;
        candidates.push(RankedCandidate {
            case_id: rec.case_id.clone(),
            similarity: sim,
            success_rate: sr,
            strategy: strat,
            weight,
        });
    }

    for strat in &allowed {
        let sr = strategy_success_rate(&persisted, *strat);
        let sim = 0.12 + fdx_sim * 0.4;
        let weight = sim * sr;
        candidates.push(RankedCandidate {
            case_id: format!("synthetic_{}", strat.as_str()),
            similarity: sim,
            success_rate: sr,
            strategy: *strat,
            weight,
        });
    }

    let mut by_strategy: BTreeMap<RemediationStrategy, RankedCandidate> = BTreeMap::new();
    for c in candidates {
        by_strategy
            .entry(c.strategy)
            .and_modify(|e| {
                if c.weight > e.weight {
                    *e = c.clone();
                }
            })
            .or_insert(c);
    }

    let mut candidates: Vec<RankedCandidate> = by_strategy.into_values().collect();
    candidates.sort_by(|a, b| {
        b.weight
            .partial_cmp(&a.weight)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.strategy.as_str().cmp(b.strategy.as_str()))
    });

    let chosen = candidates
        .first()
        .map(|c| c.strategy)
        .unwrap_or(RemediationStrategy::RetryStep);

    let top_ids: Vec<String> = candidates
        .iter()
        .take(5)
        .map(|c| c.case_id.clone())
        .collect();

    let success_hits = persisted
        .iter()
        .filter(|c| c.outcome == "success" && token_similarity(&query, &c.error_signature) > 0.2)
        .count();
    let fail_hits = persisted
        .iter()
        .filter(|c| c.outcome == "failure" && token_similarity(&query, &c.error_signature) > 0.2)
        .count();

    let rationale = format!(
        "chosen={} fdx_error_sim={:.2} similar_cases_ok={} similar_cases_fail={} top_weight={:.3}",
        chosen.as_str(),
        fdx_sim,
        success_hits,
        fail_hits,
        candidates.first().map(|c| c.weight).unwrap_or(0.0)
    );

    RetrievalDecision {
        chosen,
        rationale,
        retrieved_case_ids: top_ids,
        candidates,
    }
}

pub fn stable_case_id(step_key: &str, error_message: &str) -> String {
    let mut h = Sha256::new();
    h.update(step_key.as_bytes());
    h.update(b"|");
    h.update(normalize_error_signature(error_message).as_bytes());
    format!("{:x}", h.finalize())
}

pub fn append_remediation_case_record(ghost_root: &Path, record: &RemediationCaseRecord) -> Result<(), String> {
    let dir = retrieval_dir(ghost_root);
    std::fs::create_dir_all(&dir).map_err(|e| format!("retrieval dir: {e}"))?;
    let path = cases_path(ghost_root);
    let line = serde_json::to_string(record).map_err(|e| e.to_string())?;
    use std::io::Write;
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| format!("open cases: {e}"))?;
    writeln!(f, "{line}").map_err(|e| format!("write case: {e}"))?;
    Ok(())
}