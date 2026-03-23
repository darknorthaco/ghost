//! Bounded deploy remediation + FDX retrieval audit (DKA Phase 2/3).
//! At most one automated side-effect and one step retry per failure (except diagnostic-only).

use super::fdx_log::{self, FdxEntry};
use super::fdx_retrieval::{
    append_remediation_case_record, decide_remediation, stable_case_id, RemediationCaseRecord,
    RemediationStrategy,
};
use super::ghost_deployer::venv_pip;
use super::hide_console::hide_child_console;
use std::path::Path;
use tokio::process::Command;

pub fn log_retrieval_to_deploy_fdx(
    ghost_root: &Path,
    step_index: usize,
    deploy_step_key: &str,
    decision: &super::fdx_retrieval::RetrievalDecision,
) {
    fdx_log::append_deploy(
        ghost_root,
        &FdxEntry::new("remediation", "retrieval", "start", "Retrieval-driven remediation query")
            .context(serde_json::json!({
                "step_index": step_index,
                "deploy_step_key": deploy_step_key,
            })),
    );
    fdx_log::append_deploy(
        ghost_root,
        &FdxEntry::new("remediation", "retrieval", "success", "Retrieval ranked strategies")
            .details(serde_json::json!({
                "chosen_strategy": decision.chosen.as_str(),
                "rationale": decision.rationale,
                "retrieved_case_ids": decision.retrieved_case_ids,
                "candidate_count": decision.candidates.len(),
            })),
    );
}

pub async fn execute_strategy(ghost_root: &Path, s: RemediationStrategy) -> Result<(), String> {
    match s {
        RemediationStrategy::RetryStep => Ok(()),
        RemediationStrategy::DiagnosticOnly => Ok(()),
        RemediationStrategy::PipToolchainRefresh => {
            let pip = venv_pip(&ghost_root.to_path_buf());
            if !pip.exists() {
                return Err("venv pip not found; cannot refresh toolchain".to_string());
            }
            let mut cmd = Command::new(&pip);
            cmd.args([
                "install",
                "--upgrade",
                "pip",
                "setuptools",
                "wheel",
            ]);
            hide_child_console(&mut cmd);
            let out = cmd
                .output()
                .await
                .map_err(|e| format!("pip toolchain refresh spawn failed: {e}"))?;
            if !out.status.success() {
                return Err(format!(
                    "pip toolchain refresh failed: {}",
                    String::from_utf8_lossy(&out.stderr)
                ));
            }
            Ok(())
        }
    }
}

/// After first step failure: query corpus, optionally run one remediation, retry step once.
/// Returns `Ok(())` only if the retry succeeds. `DiagnosticOnly` skips retry and returns `Err`.
pub async fn remediate_and_retry_once<F, Fut>(
    ghost_root: &Path,
    step_index: usize,
    deploy_step_key: &str,
    first_error: &str,
    mut run_step: F,
) -> Result<(), String>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<(), String>>,
{
    let os_family = std::env::consts::OS;
    let decision = decide_remediation(
        ghost_root,
        step_index,
        deploy_step_key,
        first_error,
        os_family,
    );
    log_retrieval_to_deploy_fdx(ghost_root, step_index, deploy_step_key, &decision);

    if decision.chosen == RemediationStrategy::DiagnosticOnly {
        fdx_log::append_deploy(
            ghost_root,
            &FdxEntry::new(
                "remediation",
                "execute",
                "error",
                "No automatic retry — diagnostic-only strategy",
            )
            .details(serde_json::json!({
                "chosen_strategy": decision.chosen.as_str(),
                "rationale": decision.rationale,
            }))
            .error(first_error),
        );
        return Err(first_error.to_string());
    }

    if let Err(e) = execute_strategy(ghost_root, decision.chosen).await {
        fdx_log::append_deploy(
            ghost_root,
            &FdxEntry::new("remediation", "execute", "error", "Remediation action failed")
                .error(&e)
                .details(serde_json::json!({
                    "chosen_strategy": decision.chosen.as_str(),
                })),
        );
        return Err(format!("{first_error} (remediation failed: {e})"));
    }

    fdx_log::append_deploy(
        ghost_root,
        &FdxEntry::new("remediation", "execute", "success", "Remediation action completed")
            .details(serde_json::json!({
                "chosen_strategy": decision.chosen.as_str(),
            })),
    );

    let retry_outcome = run_step().await;
    let case_id = stable_case_id(deploy_step_key, first_error);
    let record = RemediationCaseRecord {
        case_id,
        created_at: chrono::Utc::now().to_rfc3339(),
        error_signature: super::fdx_retrieval::normalize_error_signature(first_error),
        deploy_step: deploy_step_key.to_string(),
        deploy_step_index: Some(step_index as u32),
        strategy_attempted: decision.chosen.as_str().to_string(),
        outcome: if retry_outcome.is_ok() {
            "success".to_string()
        } else {
            "failure".to_string()
        },
        os_family: os_family.to_string(),
        python_version_hint: None,
    };
    let _ = append_remediation_case_record(ghost_root, &record);

    match retry_outcome {
        Ok(()) => {
            fdx_log::append_deploy(
                ghost_root,
                &FdxEntry::new("remediation", "retry_step", "success", "Deploy step succeeded after remediation")
                    .details(serde_json::json!({
                        "step_index": step_index,
                        "strategy": decision.chosen.as_str(),
                    })),
            );
            Ok(())
        }
        Err(e2) => {
            fdx_log::append_deploy(
                ghost_root,
                &FdxEntry::new("remediation", "retry_step", "error", "Deploy step still failing after remediation")
                    .error(&e2)
                    .details(serde_json::json!({
                        "step_index": step_index,
                        "strategy": decision.chosen.as_str(),
                    })),
            );
            Err(e2)
        }
    }
}
