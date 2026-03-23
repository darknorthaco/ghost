# GHOST / DKA Roadmap Checklist

## ✔ Phase 1 — FDX Observability (Completed)
- deploy_fdx.jsonl
- discovery_fdx.jsonl
- installer_fdx.jsonl
- Rust FDX logger (fdx_log.rs)
- UI error surfacing + AppPhase reset
- docs/FDX_OBSERVABILITY.md

## ✔ Phase 2 — Self-Healing Deploy (Completed)
- deploy_remediation.rs
- bounded remediation + retry
- remediation FDX entries
- deterministic remediation paths

## ✔ Phase 3 — Retrieval-Driven Intelligence (Completed)
- fdx_retrieval.rs (Jaccard + Laplace)
- remediation_cases.jsonl
- deterministic remediation ranking
- reliability_store.py + worker_signals.jsonl
- reliability-aware routing

## ✔ Phase 4 — Worker Health & Discovery Integrity (Completed)
- worker health scoring
- discovery integrity checks
- predictive worker availability
- retrieval-driven discovery fallback
- FDX for worker health + discovery

## ✔ Phase 5 — Predictive Failure Modeling (Completed)
- `predictive_failure.rs` — read-only modeling (immutable inputs; no retries/remediation/state mutation except append `predictive_fdx.jsonl`)
- Deterministic deploy `signature_key`; window N = 20 on `deploy_fdx.jsonl`; Laplace `predictive_p` per step/signature group
- Discovery / worker / routing predictions from `worker_health_fdx.jsonl`, `worker_signals.jsonl`, `discovery_fdx.jsonl`, Phase 4 Laplace success
- Tauri `predictive_preflight_check` → `PreflightReport` / `PredictionResult` with string-keyed `context`
- Front Porch **Preflight Check** button (informational only)
- `docs/ARCHITECTURAL_SWEEP_PHASE5.md` — Phantom-era debris review (Removed / Kept)

## ✔ Governance Stack (Completed)
- GHOST_MANIFEST.md
- GHOST_DOCTRINE.md
- GHOST.cursorrules
- GHOST_DKA_TOOLSET.md

## ✔ Optional
- README pointer to GHOST_MANIFEST.md
