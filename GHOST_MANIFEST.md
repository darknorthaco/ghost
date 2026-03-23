# GHOST Manifest

**Soul of the system** — identity, purpose, and non‑negotiable character.

---

## What GHOST is

GHOST is a **local, sovereign, offline‑first automation and retrieval engine**. It orchestrates installation, deployment, discovery, and worker routing so that a **single household or operator** can run a capable stack with **low friction** and **high clarity**.

GHOST is **retrieval‑driven**: past failures and outcomes, captured in structured logs and local case stores, **inform** bounded remediation and routing decisions — without claiming omniscience and without hiding uncertainty.

GHOST is **self‑healing** within explicit limits: deploy flows may retry and apply **one** auditable remediation path per failure class, then **fail fast** with visible errors when automation cannot safely proceed.

GHOST is **deterministic** where it matters: given the **same history** (FDX streams, `remediation_cases.jsonl`, `worker_signals.jsonl`) and the **same inputs**, remediation ranking and reliability‑aware routing produce the **same** choices. There is no “magic” — only declared rules and append‑only evidence.

### Core values (embodied in code)

| Pillar | Meaning | Primary artifacts |
|--------|---------|-------------------|
| **Observability** | Truth over comfort; no silent success | `deploy_fdx.jsonl`, `discovery_fdx.jsonl`, `installer_fdx.jsonl`; Rust `fdx_log.rs` |
| **Self‑healing deploy** | Bounded remediation + retry, fully logged | `ghost_deployer.rs`, `deploy_remediation.rs` |
| **Retrieval‑driven intelligence** | Local corpus, explicit ranking | `fdx_retrieval.rs`, `remediation_cases.jsonl`; see `docs/FDX_OBSERVABILITY.md` |
| **Reliability‑aware routing** | History nudges orchestration, ties broken deterministically | `reliability_store.py`, `router.py`, `router_reliability.py`; `worker_signals.jsonl`, `worker_routing_fdx.jsonl` |
| **Worker health & discovery integrity** | Scored, deduped manifests; predictive labels; one retrieval‑informed discovery fallback | `worker_health_discovery.rs`; `worker_health_fdx.jsonl`; `discovery_fdx.jsonl` (`discovery_integrity`) |
| **Predictive preflight** | Read-only forecasts from recent FDX + signals; operator-visible; append-only `predictive_fdx.jsonl` | `predictive_failure.rs`; Tauri `predictive_preflight_check`; `predictive_fdx.jsonl` |

---

## What GHOST is not

- **Not a mesh controller** — GHOST does not define itself as a multi‑tenant WAN control plane or global fabric.
- **Not a WAN trust fabric** — Trust, identity, and data stay **local** and **explicit**; there is no mandate to extend GHOST into internet‑wide trust semantics.
- **Not Phantom** — GHOST is **not** Phantom under another name. It does not inherit Phantom’s identity, product role, or narrative. Lineage may inform engineering judgment; **identity and governance are GHOST’s alone**.

---

## Architectural stance (one paragraph)

GHOST treats **observability** as a first‑class product surface: structured JSONL (**FDX**) is how operators and engineers close feedback loops. **Self‑healing** is a **behavioral contract**: try, log, remediate within bounds, retry once where allowed, then surface failure clearly. **Retrieval** is a **decision aid** over that evidence — weighted, Laplace‑smoothed, deterministic — not a black box. **Routing** respects capacity and profiles first; **reliability signals** modulate scores in a bounded way, with decisions auditable in `worker_routing_fdx.jsonl`. **Discovery** is **integrity‑checked** and **health‑scored**, with **at most one** extra UDP window when local history suggests it helped before — all logged, nothing hidden.

---

## Living document

This manifest is the **authority on what GHOST is for**. Implementation details evolve; if code and manifest diverge, **reconcile toward the manifest** or **revise the manifest deliberately** — never silently.
