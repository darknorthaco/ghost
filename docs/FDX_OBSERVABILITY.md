# FDX observability — deploy, discovery, installer

FDX (**F**ailure-**D**iagnosis e**X**change) is append-only JSONL telemetry for the GHOST desktop pipeline. It implements explicit boundaries, audit trails, and **no silent state transitions** for deploy-related flows: every step emits **start**, **success**, or **error** where applicable.

## Where logs live

| Platform | Directory |
|----------|-----------|
| Windows | `%USERPROFILE%\.ghost\logs\` |
| POSIX | `~/.ghost/logs/` |

| File | Stream | Writers |
|------|--------|---------|
| `deploy_fdx.jsonl` | Pre-scan deploy steps (0–9), pre-scan lifecycle, legacy `deploy_ghost` | Rust (`fdx_log`) |
| `discovery_fdx.jsonl` | UDP/LAN discovery, manual scan, scan-log mirror | Rust |
| `installer_fdx.jsonl` | Python installer (`ghost_setup`) — venv, pip, init-db | Python |
| `remediation` lines on `deploy_fdx.jsonl` | Retrieval query, execute, retry (Phase 3) | Rust |
| `worker_health_fdx.jsonl` | Health scores, predictive availability, discovery session (Phase 4) | Rust (`fdx_log::append_worker_health`) |
| `discovery_fdx.jsonl` (Phase 4) | `discovery_integrity` phase — integrity pass, retrieval fallback | Rust |
| `predictive_fdx.jsonl` (Phase 5) | Preflight predictions only (`deploy` \| `discovery` \| `worker` \| `routing` \| `preflight` summary) | Rust (`predictive_failure.rs`) |

Human-readable installer text still goes to `install.log` in the same folder.

## Log line schema

Each line is one JSON object:

| Field | Type | Meaning |
|-------|------|---------|
| `timestamp` | string | UTC RFC3339 |
| `phase` | string | Logical pipeline (e.g. `deploy`, `pre_scan`, `deploy_legacy`, `discovery`, `installer`) |
| `step` | string | Stable step id (e.g. `step_0_create_venv`, `lan_discovery`) |
| `status` | string | `start` \| `success` \| `error` \| `info` |
| `message` | string | Short human summary |
| `details` | object? | Structured metadata |
| `error` | string? | Error text when `status` is `error` |
| `context` | object? | Extra correlation (e.g. `step_index`) |

**Interpretation:** grep or stream-parse by `phase` + `step` + `status`. The last `error` for a given `step` before a successful retry (if any) pinpoints failure.

## End-to-end deploy map (DKA steps 0–10)

Information flows: **UI → Tauri command → `GhostDeployer` → subprocesses / HTTP / UDP**. Stocks include **venv**, **engine tree**, **`ghost_config.json`**, **`controller_placement.json`**, **state markers**, **running controller/worker processes**.

| DKA step | Pre-scan / Rust step id | Preconditions (summary) | Postconditions | Failure propagation |
|----------|-------------------------|-------------------------|----------------|---------------------|
| 0 Engine source | `engine_resolve` (FDX before step loop) | Resolvable engine root (`GHOST_ENGINE_ROOT`, `engine_root.txt`, dev tree) | Paths recorded in FDX | Offline bundle resolve errors return to UI; phase → FrontPorch |
| 1 venv | `step_0_create_venv` | Host Python | `~/.ghost/venv` usable | `Err` → FDX error → UI |
| 2 pip / deps | `step_1_install_python_deps` | venv pip | deps installed | Same |
| 3 engine editable install | `step_2_install_ghost_core` | `requirements.txt` / bundle layout | `-e` install | Same |
| 4 GPU / plugins | `step_3_verify_gpu_plugins` | engine importable | check completes | Same |
| 5 service (optional) | `step_4_install_service` | OS hooks | best-effort | Same if step returns Err |
| 6 bootstrap configs | `step_5_bootstrap_config` | templates / paths | `ghost_config.json`, placement files | Same |
| 7 uvicorn :8765 | `step_6_start_controller` | free port, Python env | API listening | Same |
| 8 firewall / ports | `step_7_open_ports` | platform | rules or no-op | Same |
| 9 state markers | `step_8_initialize_state` | dirs | state files | Same |
| 10 local worker | `step_9_start_local_worker` | worker binary / script | worker process | Same |
| 10 LAN / UDP (ceremony path) | `lan_discovery` + `discovery_fdx` | network (unless offline) | manifests / synthetic offline worker | Panic → FDX `error`; zero workers → `discovery_failed` flag (not always hard error) |

**Feedback loops:** Deploy progress events reinforce UI state; **balancing** loop: any `Err` from `run_deployment_pre_scan` resets **`AppPhase` → `FrontPorch`** and returns the error to the UI (`FrontPorchDeploy` error box). Legacy **`deploy_ghost`** now **fails fast** (returns `Err`, resets phase) instead of warning-only continuation.

## Dependency / path matrix (expected vs actual)

| Concept | Expected resolution | Brittle when |
|---------|---------------------|--------------|
| `GHOST_ENGINE_ROOT` | Env points at repo root with `config/default.yaml` | Var set to wrong tree; YAML missing |
| `~/.ghost/engine_root.txt` | Written by Python installer / setup | Stale path after repo move |
| Bundled / dev engine | Tauri `find_engine_source` | Packaged layout differs from dev |
| `requirements.txt` | Under `ghost_engine_repo_root()` | Assumes monorepo layout |
| `config/default.yaml` | Under engine root | Missing → engine resolve fails |
| `controller_placement.json` | Bootstrap step | Invalid JSON → step error |
| Worker binary | Step 9 launcher | Missing → explicit Err |
| Port 8765 | Controller step | In use → start failure → logged + UI |

## Silent or under-logged failure modes (mitigations)

| Issue | Before | After |
|-------|--------|-------|
| `deploy_ghost` continued after step failure | “Deployed” with broken system | **Fail fast** + FDX `error` + phase **FrontPorch** |
| Discovery thread panic | String error only | **FDX** `pre_scan` / `lan_discovery` **error** |
| Manual LAN scan lines | UI only | **`discovery_fdx.jsonl`** via `emit_scan_log_opt` |
| Python venv / pip failures | `install.log` only | **`installer_fdx.jsonl`** start/success/error |
| Pre-scan top-level failure | Phase reset, easy to miss why | **`deploy_fdx.jsonl`** `pre_scan` **error** with message |

Remaining gaps to be aware of: **worker registration** failures during manual scan still return `Ok(ScanResult)` with `registered < scanned` — FDX records per-worker **error** lines; consider surfacing aggregate failure in UI if product requires strict all-or-nothing registration.

## Resilience checks (manual)

Simulate each scenario and confirm: **visible UI error** (where command is used), **`deploy_fdx` / `installer_fdx` / `discovery_fdx` line**, **no stuck `Deploying` phase**.

1. Missing Python on PATH → step 0 Err  
2. pip network failure → step 1/2 Err  
3. Missing `requirements.txt` → step 2 Err  
4. Missing engine source → pre-scan / resolve Err  
5. Missing `config/default.yaml` → engine resolution / later step Err  
6. Invalid `controller_placement.json` → bootstrap Err  
7. Port 8765 in use → controller start Err  
8. Missing worker artifact → step 9 Err  
9. UDP discovery timeout → `discovery_failed: true`; ceremony still runs; check `discovery_fdx` and diagnostics in discovery log  

## Reporting issues

Attach (redact secrets):

1. Last 50 lines of `deploy_fdx.jsonl`, `discovery_fdx.jsonl`, `worker_health_fdx.jsonl`, and if relevant `installer_fdx.jsonl`  
2. `install.log` tail  
3. App phase / on-screen error text  
4. OS, Python version, and whether offline bundle was used  

This gives engineers a **causal chain** from intent (Deploy) through each boundary without relying on memory or silent success.

---

## Retrieval-Driven Deploy Intelligence (DKA Phase 3)

Phase 3 adds a **local, deterministic retrieval layer** on top of FDX: past errors and remediation outcomes inform the next bounded action. This is **inspired by** the *idea* of usefulness-weighted retrieval (reinforce what worked, down-rank what failed) as explored in projects such as the [retrieval-weight experiment](https://github.com/kusp-dev/retrieval-weight-experiment) — **not** by copying its code or depending on it.

### How FDX logs become a retrieval corpus

1. **Raw streams** — `deploy_fdx.jsonl`, `discovery_fdx.jsonl`, and `installer_fdx.jsonl` are read from `logs/` and scanned for `status: "error"` lines. Token overlap (Jaccard on normalized words) measures similarity between a **current** failure and **historical** error text.
2. **Outcome stock** — `~/.ghost/retrieval/remediation_cases.jsonl` stores explicit **cases** after each remediation attempt: `error_signature`, `deploy_step`, `strategy_attempted`, `outcome` (`success` | `failure`), `os_family`, `case_id` (hash of step + normalized error). This file is append-only and user-owned.
3. **Ranking** — For each allowed strategy, a **weight** is computed as `similarity × Laplace-smoothed success rate` over past cases using that strategy. Candidates are **collapsed per strategy** (max weight), then sorted by weight with **lexicographic tie-break** on strategy id so the choice is **reproducible** for the same files and query.

### How retrieval informs remediation

When a pre-scan deploy step fails:

- The engine emits **`remediation` / `retrieval` / `start`** and **`success`** lines on `deploy_fdx.jsonl` with `chosen_strategy`, `retrieved_case_ids`, `rationale`, and `candidate_count`.
- A **bounded** action runs at most once: `retry_step` (no-op then re-run), `pip_toolchain_refresh` (upgrade pip/setuptools/wheel in `~/.ghost/venv` then re-run), or **`diagnostic_only`** (e.g. port already in use — **no** automatic retry; failure returns to the UI).
- After the optional retry, **`remediation` / `retry_step`** logs success or error, and a line is appended to **`remediation_cases.jsonl`** for future retrieval.

No network calls; no hidden global services.

The legacy Tauri command **`deploy_ghost`** (direct step loop) does **not** yet invoke this remediation wrapper; the **Front Porch pre-scan** path (`run_deployment_pre_scan`) does — prefer pre-scan for retrieval-driven recovery.

### How retrieval informs worker selection (Taskmaster / orchestrator)

The Python package **`ghost_orchestrator`** exposes:

- **`reliability_store`** — append **`worker_signals.jsonl`** (`worker_id`, `ok`, optional `latency_ms`) from task outcomes or health checks.
- **`laplace_reliability_weights()`** — deterministic `(successes+1)/(total+2)` per worker.
- **`deterministic_route(..., reliability_weights=...)`** — multiplies the baseline routing score by a **bounded** factor `max(0.25, min(1.5, 0.5 + weight))` so history **nudges** but does not erase explicit capacity/GPU logic.
- **`deterministic_route_with_retrieval_audit`** — loads weights from disk, routes, and appends a JSON line to **`~/.ghost/retrieval/worker_routing_fdx.jsonl`** including `rationale` and the weight map used.

Timeouts are **not** auto-mutated in this slice; **`mean_latency_ms(worker_id)`** is available from `reliability_store` for callers that want to adjust probes deterministically from history.

### Inspect or reset the retrieval store

| Path | Purpose |
|------|---------|
| `~/.ghost/retrieval/remediation_cases.jsonl` | Deploy remediation learning (safe to delete to cold-start) |
| `~/.ghost/retrieval/worker_signals.jsonl` | Worker outcome corpus for routing |
| `~/.ghost/retrieval/worker_routing_fdx.jsonl` | Audit of routing decisions (“why this worker”) |

**Reset:** delete the files above (or the whole `retrieval/` directory). FDX logs under `logs/` are unchanged and remain the raw telemetry source.

### Relation to the retrieval-weight experiment (conceptual only)

Both systems share the **systems-level idea**: treat historical signals as a **stock**, retrieve what resembles the present situation, and **weight** actions by observed usefulness — with **decay** implied by newer cases overwriting the empirical distribution as you append lines. GHOST’s implementation uses **explicit JSONL**, **deterministic sorting**, and **FDX audit lines** instead of bandits or neural retrievers, in line with DKA doctrine (sovereignty, auditability, no silent success).

---

## Worker health & discovery integrity (DKA Phase 4)

Phase 4 closes the loop between **discovery**, **readiness**, and **historical worker signals**.

### Module

- **`worker_health_discovery.rs`** — used by pre-scan LAN discovery (`ghost_deployer`) and **`scan_and_register_workers`** (manual LAN scan).

### Worker health scoring

After manifests pass integrity, each worker gets a **deterministic 0–100 score** logged to **`worker_health_fdx.jsonl`** (`phase: worker_health`, `step: health_score`): signature verification, non-zero port, presence of `worker_id`, and **Laplace `predictive_p`** from **`~/.ghost/retrieval/worker_signals.jsonl`** (same schema as Python `reliability_store`).

### Discovery integrity

- **Deduping:** duplicate `worker_id` in one batch → first wins (sorted order), others dropped; issues listed in FDX.
- **Checks:** port `0` and **unsigned** manifests generate **info** issues (not silent).
- **FDX:** `discovery_fdx.jsonl`, `phase: discovery_integrity`, `step: integrity_check`.

### Predictive availability

For each discovered worker, **`predictive_availability`** lines record a label: `likely_up` | `likely_down` | `uncertain` from **readiness probe success** + Laplace `predictive_p` (thresholds are fixed in code — deterministic).

### Retrieval-driven discovery fallback

If the **first** discovery pass returns **zero** workers after integrity, the engine consults **`remediation_cases.jsonl`**: when **successes > failures** for discovery-adjacent entries (errors mentioning discover / 8095 / worker / udp, or deploy steps mentioning `lan`), it runs **one** second UDP window with timeout **`min(max(base×1.5, base+500ms), 120s)`** and **`early_exit = false`**. All decisions are logged on **`worker_health_fdx.jsonl`** and **`discovery_fdx.jsonl`**.

### Signals appended

Successful discovery appends **`worker_signals.jsonl`** lines (`source: discovery_phase4` or `offline_synthetic`) so Phase 3 routing can consume the same stock.

### Reset

Deleting **`worker_health_fdx.jsonl`** only removes health audit history; **`worker_signals.jsonl`** lives under **`retrieval/`** (see Phase 3 table).

---

## Predictive preflight (DKA Phase 5)

Phase 5 adds **read-only** failure **forecasts** for operators. It does **not** change deploy state, workers, venv, or engine; it does **not** retry steps or invoke remediation.

### Stream

- **`predictive_fdx.jsonl`** — one JSON object per line, written only by `predictive_failure::run_preflight_and_log` (invoked from Tauri `predictive_preflight_check`).

### Schema (line object)

| Field | Type | Meaning |
|-------|------|---------|
| `timestamp` | string | UTC RFC3339 |
| `domain` | string | `deploy` \| `discovery` \| `worker` \| `routing` \| `preflight` (summary row) |
| `outcome` | string | Model-specific label (e.g. `likely_fail`, `likely_up`, `stable`, `summary`) |
| `predictive_p` | number | Scalar risk or summary score in \([0,1]\) (see module rationale) |
| `rationale` | string | Short human explanation |
| `context` | object | **String values only** (serialized as JSON object with string values) |
| `signature_key` | string? | Present for deploy rows when a worst-case deploy signature was identified |

### Inputs (read-only)

Tail reads from **`deploy_fdx.jsonl`**, **`worker_health_fdx.jsonl`**, **`discovery_fdx.jsonl`**, and **`~/.ghost/retrieval/worker_signals.jsonl`**. Deploy grouping uses a deterministic **`signature_key`**: `{step_index}|{error_code}|{first 48 chars of error text}` with `error_code` from exit/HTTP fields in FDX context/details or `"0"`.

### UI

**Front Porch** exposes an optional **Preflight Check** button; results are informational only.
