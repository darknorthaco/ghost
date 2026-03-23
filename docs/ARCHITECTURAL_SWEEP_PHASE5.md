# Architectural sweep — Phase 5 (Phantom-era debris)

This document records a repository pass for **leftover Phantom-era scaffolding**, **dead code**, and **naming/documentation drift**, under the **Phase 5 removal safety contract**:

A removal or edit is **safe** only if:

- `cargo check` passes for `ghost_app` / `src-tauri`
- Existing tests pass
- No intentional observable behavior changes
- No FDX schema changes for existing streams (deploy / discovery / installer / worker health)
- No breaking API surface changes for shipped commands
- No UI regressions for primary flows

---

## Removed

| Item | Reason | Safety justification |
|------|--------|----------------------|
| Trailing non-Rust text after `predictive_failure.rs` tests (`…}` then stray lines) | Accidental paste / merge artifact; broke `cargo check` | Deletion restores compilation only; no runtime behavior existed |
| Unused `use std::path::Path` in `trust_store.rs` `#[cfg(test)]` module | Unused import warning in tests | Test-only import; zero behavioral effect |
| “Mesh” wording in `tls_transport.rs` doc comments | Naming drift vs GHOST manifest (“not a mesh controller”) | Comment-only; no wire protocol or API change |
| “Phantom-style” wording in `docs/FDX_OBSERVABILITY.md` | Documentation drift in routing narrative | Doc-only clarification to “baseline routing score” |

---

## Kept

| Item | Reason it is load-bearing |
|------|---------------------------|
| `phantom/` and `_phantom_upstream/` trees (if present) | Explicit **reference** copies; workspace rules forbid mutating them; they are not part of the GHOST app build |
| `docs/GHOST_SHELL_ADAPTATION.md`, `docs/GHOST_AUDIT_REPORT.md`, `docs/GHOST_TRANSFORMATION_PLAN.md` | **Historical** record of Phantom → GHOST adaptation; removing would erase intentional lineage documentation |
| `trust_store.rs`, `ws_client.rs`, `tls_transport.rs`, `service_manager.rs`, unused `DeployStep`, `discover_workers`, discovery_log builder helpers | Currently **unreferenced** or warning-only in places, but remain **declared modules/types** for future TLS, service control, and discovery evolution; deleting would shrink public `backend` surface and risk unintended API loss without a versioned deprecation plan |
| `WorkerManifest` alias and `WorkerManifest::host` / `gpu_info` | Compatibility shims for `ghost_deployer` / manifest field access patterns; removal risks call-site churn across a large deploy module |
| ACKNOWLEDGMENTS / README references to Phantom | Acknowledged **influence** and separation of identity — appropriate non-historical context |

---

## Follow-ups (not done in this sweep)

- Broader deletion of dormant transport / trust / WS modules would require a **versioned deprecation** pass and explicit Manifest amendment if any external tool depended on symbols.
- A dedicated `cargo fix` / `clippy` dead-code cleanup across `ghost_deployer.rs` is deferred to avoid large diffs unrelated to Phase 5 predictive work.
