# GHOST Doctrine

**Mind of the system** — principles and architectural commitments that govern design and change.

GHOST is governed by **GHOST_MANIFEST.md** (soul) and this document (mind). Operational rules for tooling live in **GHOST.cursorrules** (body).

---

## 1. Observability

**Principle:** Critical flows must be **inspectable** after the fact. Operators own their data; the system does not “remember” on their behalf in opaque buffers.

**Commitments**

- Deploy, discovery, installer, and remediation paths emit structured telemetry to:
  - `deploy_fdx.jsonl`, `discovery_fdx.jsonl`, `installer_fdx.jsonl`
  - Remediation phases on `deploy_fdx.jsonl` (`phase: remediation`, retrieval / execute / retry_step)
- **No silent failures** for paths we control: errors propagate to the UI where the stack is wired for it, and are recorded in FDX or sibling JSONL as appropriate.
- **No hallucinated success**: phases and markers must not imply “deployed” or “healthy” without evidence; legacy paths that skip remediation must be documented (see `docs/FDX_OBSERVABILITY.md`).

**Modules:** `fdx_log.rs`; consumers such as `ghost_deployer.rs`, `deploy_remediation.rs`; Python installer FDX for `installer_fdx.jsonl`.

**Reference:** `docs/FDX_OBSERVABILITY.md` (Phases 1–5).

---

## 2. Self‑healing (deploy)

**Principle:** Recovery is **bounded**, **logged**, and **reversible in intent** (we do not destroy user data silently; we perform explicit, documented actions).

**Commitments**

- Pre‑scan deploy steps (0–9) may invoke **one** remediation cycle per failure: retrieval ranking → optional action → **at most one** retry of the same step (except **diagnostic_only**, which does not auto‑retry).
- Remediation strategies are **enumerated** (e.g. `retry_step`, `pip_toolchain_refresh`, `diagnostic_only`) — not open‑ended shell.
- Every retrieval query and outcome is **auditable** on `deploy_fdx.jsonl`; outcomes feed **`~/.ghost/retrieval/remediation_cases.jsonl`** for future ranking.
- **Non‑remediable** conditions (e.g. port bind conflicts classified as diagnostic‑only) **fail fast** with clear errors to the operator.

**Modules:** `deploy_remediation.rs`, `ghost_deployer.rs`; ranking inputs from `fdx_retrieval.rs`.

---

## 3. Retrieval‑driven intelligence

**Principle:** Decisions that could be arbitrary are instead **grounded in local history**, with **deterministic** ranking — reinforcement of what worked, down‑weighting of what failed, without external models or network calls.

**Commitments**

- The **corpus** includes:
  - Parsed error lines from FDX logs under `~/.ghost/logs/`
  - Append‑only **`remediation_cases.jsonl`** (error signature, step, strategy, outcome, OS family)
- **Remediation strategy selection** uses token similarity, Laplace‑smoothed success rates, strategy collapse, and **lexicographic** tie‑breaks so runs are reproducible.
- **Worker routing** uses **`worker_signals.jsonl`** and Laplace weights; **`router_reliability.py`** may append **`worker_routing_fdx.jsonl`** with rationale and weights used.

**Modules:** `fdx_retrieval.rs`, `deploy_remediation.rs`; Python: `reliability_store.py`, `router.py`, `router_reliability.py`.

**Reference:** `docs/FDX_OBSERVABILITY.md` — Phase 3.

---

## 3b. Worker health & discovery integrity (Phase 4)

**Principle:** Discovery outputs are **validated**, **scored**, and **audited**; empty discovery may trigger **one** retrieval-informed second pass.

**Commitments**

- **`worker_health_fdx.jsonl`** records health scores, predictive availability labels, and discovery session boundaries (`fdx_log::append_worker_health`).
- **`discovery_fdx.jsonl`** records **`discovery_integrity`** (dedupe, port/signature issues) and **retrieval fallback** start/end.
- **`worker_health_discovery.rs`** integrates pre-scan and manual LAN scan; appends **`worker_signals.jsonl`** compatible with Python `reliability_store`.

**Reference:** `docs/FDX_OBSERVABILITY.md` — Phase 4.

---

## 3c. Predictive preflight (Phase 5)

**Principle:** Operators may request **forecasts** before acting; those forecasts are **advisory** and must not silently change operational state.

**Commitments**

- **`predictive_preflight_check`** (and `predictive_failure::run_preflight_and_log`) are **read-only** with respect to workers, venv, engine, and deploy state: **no** retries, **no** remediation, **no** orchestration side effects.
- The **only** write is **append-only** lines to **`predictive_fdx.jsonl`** under `logs/`, mirroring the FDX observability posture.
- Predictions combine **deterministic** Laplace-style counts over bounded FDX tails, Phase 4 Laplace success for workers, integrity warning counts, and **`worker_signals.jsonl`** — outcomes are **informational** for the UI.

**Modules:** `predictive_failure.rs`.

**Reference:** `docs/FDX_OBSERVABILITY.md` — Phase 5.

---

## 4. Determinism

**Principle:** Given the **same** on‑disk history and **same** inputs, automation choices are **repeatable**. Debugging and audits depend on this.

**Commitments**

- No hidden randomness in **remediation ranking** or **deterministic_route** when reliability weights are fixed.
- Sorting and tie‑break rules are **explicit** in code and docs.
- Introducing randomness (e.g. sampling, jitter) requires **manifest/doctrine update** and **explicit logging** of seeds or inputs — default posture is **no** such randomness in core paths.

---

## 5. Sovereignty

**Principle:** Core behavior does not depend on the cloud, vendor SaaS, or opaque remote orchestration.

**Commitments**

- Primary state lives under **`~/.ghost`** or **`GHOST_HOME`** (retrieval store, logs, venv, config markers).
- No mandatory telemetry to third parties for **core** deploy, discovery, remediation, or routing behavior.
- Optional integrations (if ever added) must be **opt‑in**, **documented**, and **non‑blocking** for sovereign operation.

---

## 6. Boundaries

**Principle:** Layers speak through **explicit** contracts; no “spooky” cross‑layer mutation.

**Sketch**

| Layer | Responsibility | Must not |
|-------|----------------|----------|
| **UI** (Tauri / React) | Intent, display, phase UX | Silently swallow backend errors for deploy pre‑scan |
| **Rust backend** | Deploy, FDX, retrieval, remediation, discovery command surface | Assume Python layout without resolution rules documented in code/docs |
| **Python** (orchestrator / Taskmaster side) | Registry snapshot routing, reliability signals | Replace Rust deploy or FDX ownership without a declared boundary change |

**Commitments**

- Changes that blur boundaries require **doctrine + FDX_OBSERVABILITY** updates.
- Side effects (writes under `~/.ghost`, subprocess launches) happen in **known** modules, not ad‑hoc scattered calls.

---

## 7. User experience

**Principle:** The system should feel **smart** because it is **legible** — not because it conceals errors.

**Commitments**

- Errors are **explainable** (message + FDX trail + remediation rationale where applicable).
- Self‑healing is **visible** in logs; the UI should not imply success while FDX records failure.
- Operators can **reset** retrieval state by removing `~/.ghost/retrieval/*` as documented, without breaking the core engine identity.

---

## Hierarchy

1. **GHOST_MANIFEST.md** — what GHOST *is*.
2. **GHOST_DOCTRINE.md** (this file) — how GHOST *must behave*.
3. **GHOST.cursorrules** — how we *implement* under Cursor.
4. **GHOST_DKA_TOOLSET.md** — how DKA *informed* design (lens, not law).

If doctrine and manifest conflict, **Manifest prevails**; then reconcile doctrine and code deliberately.
