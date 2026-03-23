# GHOST × DKA toolset

**Manual in the box** — what DKA is, how it shaped GHOST, and how engineers can reuse the lens for future work.

---

## What DKA (DarkNorthAnalysis) is

**DKA** is a **hybrid analysis lens**, not a runtime dependency and **not** GHOST’s governing law. It combines:

1. **Lived experience** — failure modes that actually happen in the field (silent errors, drift, deploy collapse, missing logs).
2. **Hardened DevOps discipline** — explicit boundaries, deterministic pipelines, audit trails, no silent state transitions.
3. **Meadows systems thinking** — stocks and flows, feedback loops, leverage points, resilience under perturbation.
4. **Adaptive analysis** — pattern recognition, causal chains, clustering failures, inferring where small changes fix whole classes of problems.

GHOST is **forged** with this lens; it is **ruled** by **GHOST_MANIFEST.md** and **GHOST_DOCTRINE.md**.

---

## Tier 4 Prompt Engineering Discipline (DKA Standard)

DKA is not only a **lens** for analysis; it is also a **methodology** and, for agentic engineering, a **prompting discipline**. The tiers below describe how rigorously a prompt constrains an autonomous implementer.

### DKA prompting tiers (for agentic engineering systems)

DKA recognizes **four** tiers of prompt sophistication:

| Tier | Name | Character |
|------|------|-----------|
| **1** | Naive | Unbounded, underspecified, high variance. **Not acceptable** for sovereign systems. |
| **2** | Structured | Clear tasks and some context, but too much left to agent discretion. |
| **3** | Constrained | Explicit boundaries, typed contracts, safety rules, deterministic outputs (where GHOST Phase 5 v2-class work lived). |
| **4** | Self-enforcing | Prompts that encode their own **verification**, **failure modes**, and **anti-patterns** — the DKA **gold standard**. |

### Tier 4 prompt requirements (DKA standard)

A prompt reaches **Tier 4** when it includes **all** of the following:

1. **Acceptance criteria (self-verification)** — The prompt defines what “done” means in a way the agent can check itself.  
   *Examples:* `predictive_failure.rs` compiles with zero warnings; all prediction functions accept only immutable references; `predictive_fdx.jsonl` entries contain all required fields; `PreflightReport` round-trips through serde without loss.  
   This reduces silent drift and forces the agent to validate its own output.

2. **Explicit failure modes** — The prompt defines behavior when inputs are missing, malformed, or insufficient.  
   *Examples:* if fewer than three FDX entries exist for a step → return `uncertain`; if `worker_signals.jsonl` is missing → discovery prediction returns `unavailable`; if `error_code` is absent → use `"0"`.  
   This cuts undefined behavior and hallucinated certainty.

3. **Anti-patterns (explicitly forbidden)** — The prompt bans dangerous or ambiguous patterns.  
   *Examples:* do not use `unwrap()` in predictive code; do not silently fall back to defaults; do not log predictions at `INFO` level; do not reuse deploy/discovery FDX schema types for prediction.  
   This prevents accidental architectural violations.

4. **Output verification hooks** — The agent must produce a **post-implementation audit**.  
   *Examples:* list all functions that touch mutable state (should be empty); list all file paths written (should be only `predictive_fdx.jsonl`); confirm `signature_key` is pure and side-effect-free.  
   This forces an adversarial re-read of the implementation.

5. **Reviewer persona (adversarial check)** — The agent adopts a **hostile reviewer** stance after implementation.  
   *Example:* “Review your own output as a hostile code reviewer whose only job is to find boundary violations — any function that writes to state outside `predictive_fdx.jsonl`, any silent default, any `unwrap`. List findings before declaring done.”  
   This is the single highest-leverage addition for agentic coding.

### Why this belongs in the DKA toolkit

DKA is not only a design philosophy — it is a **governance engine** for adaptive systems. **Tier 4** prompting:

- Reduces variance  
- Prevents silent architectural drift  
- Enforces determinism  
- Improves safety  
- Makes agentic coding more reproducible  
- Aligns with DKA’s emphasis on boundaries, stocks and flows, and leverage points  

It is the natural evolution of DKA as GHOST becomes more autonomous.

---

## How DKA shaped GHOST (implemented phases)

| Phase | DKA pressure | GHOST response | Where it lives |
|-------|----------------|----------------|----------------|
| **1 — Observability** | “Failure fails to propagate”; “no audit trail” | Structured **FDX** JSONL for deploy, discovery, installer; Rust logger | `fdx_log.rs`, `*.jsonl` under `logs/`, `docs/FDX_OBSERVABILITY.md` |
| **2 — Self-healing** | “Stuck phases”; “warn and continue” as false success | **Bounded** remediation + retry; fail fast when not safe; logged phases | `deploy_remediation.rs`, `ghost_deployer.rs` |
| **3 — Retrieval intelligence** | “Same mistake repeatedly”; “no memory” | Local **corpus** over FDX + `remediation_cases.jsonl`; deterministic ranking; Laplace weighting | `fdx_retrieval.rs`, `remediation_cases.jsonl` |
| **3 — Routing** | “Bad worker keeps getting tasks” | **Reliability signals** + bounded score multiplier; optional routing audit JSONL | `reliability_store.py`, `router.py`, `router_reliability.py`, `worker_signals.jsonl`, `worker_routing_fdx.jsonl` |
| **4 — Worker health / discovery** | “Duplicate or junk manifests”; “empty scan but worker exists” | **Integrity pass** + **health scores** + **predictive labels**; **one** retrieval-informed second UDP window | `worker_health_discovery.rs`, `worker_health_fdx.jsonl`, `discovery_fdx.jsonl` (`discovery_integrity`) |
| **5 — Predictive preflight** | “Surprises after clicking Deploy”; “no visibility before commit” | **Read-only** Laplace-style forecasts over FDX tails + signals; **append-only** `predictive_fdx.jsonl`; UI preflight panel (no auto-fix) | `predictive_failure.rs`, `predictive_preflight_check`, `predictive_fdx.jsonl` |

Each phase **closes a feedback loop**: observe → decide → act → record → improve the next decision **without** cloud or hidden state.

---

## Conceptual debt paid (DKA vocabulary)

- **Information flow:** FDX streams move truth from Rust/Python to disk; retrieval reads it back for decisions.
- **Feedback loop:** Remediation outcomes append to `remediation_cases.jsonl`, reinforcing or punishing strategies.
- **Leverage point:** Deterministic ranking + logging changes **system-wide** behavior without UI churn.
- **Resilience:** Bounded retry + diagnostic-only paths avoid infinite loops and “silent stuck.”

---

## How engineers use DKA going forward

Use DKA to **design** and **audit**, not to bypass Manifest/Doctrine.

**Designing future phases** (examples — not commitments until documented):

- **Worker health:** extend **signals** (latency, timeouts) and log **why** probes changed — keep determinism.
- **Predictive preflight (implemented):** pattern counts from FDX + signals → **informational** UI + `predictive_fdx.jsonl`; never silent auto-destructive fixes from this path.
- ** richer retrieval:** still **local**, still **auditable**; if ML appears, it must be opt-in and versioned.

**Auditing a new subsystem**

1. **Flows:** Where does information enter and leave? Where can it stop?
2. **Loops:** What reinforces success? What balances runaway behavior?
3. **Boundaries:** UI vs Rust vs Python — who owns FDX for this path?
4. **Determinism:** Same files + inputs → same outcome?
5. **Sovereignty:** Any new network or third-party requirement?

**Maintenance standards**

- Extend **FDX** or sibling JSONL rather than ad-hoc logs.
- Preserve **remediation bounds** when touching `ghost_deployer` / `deploy_remediation`.
- Preserve **ranking determinism** when touching `fdx_retrieval`.
- Preserve **routing audit** semantics when touching `router_reliability` / `reliability_store`.

---

## Relationship to external “retrieval weight” ideas

Industry and research projects (e.g. ideas around **weighting** retrieval by usefulness) may **inspire** GHOST’s **local** Laplace-weighted retrieval — **without** copying external code or depending on them. GHOST’s law is **Manifest + Doctrine**; DKA is the **hammer**; those projects are **not** the **constitution**.

---

## One-line summary

**DKA is how we think; GHOST_MANIFEST and GHOST_DOCTRINE are what GHOST is; FDX and retrieval stores are what actually remember.**
