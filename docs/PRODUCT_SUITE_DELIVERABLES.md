# GHOST Product Suite — Deliverables Index

1. **Audit report:** `docs/GHOST_AUDIT_REPORT.md`
2. **Transformation plan:** `docs/GHOST_TRANSFORMATION_PLAN.md`
3. **Shell adaptation notes:** `docs/GHOST_SHELL_ADAPTATION.md`
4. **GHOST Installer (Tk wizard):** `ghost_installer/` — `ghost_wizard.py`, `engine/ghost_setup.py`, `integration/ghost_installer_api.py`
5. **GHOST Desktop:** `ghost_app/` — Tauri + React + spectral `theme.css`
6. **Rebrand script:** `scripts/rebrand_shells.py` (run only on copies)
7. **Engine:** `ghost_core/`, `ghost_api/`, `ghost_cli/`, `config/default.yaml`, etc.

## Build artifacts

| Artifact | How |
|----------|-----|
| Installer EXE | `ghost_installer/ghost_installer.spec` → PyInstaller; see `ghost_installer/build/README_BUILD.md` |
| Desktop app | `cd ghost_app && npm install && npm run build && cd src-tauri && cargo build` then `npm run tauri build` from `ghost_app` |

## Finalization (Option B)

- **Tauri** does not bundle Python; `tauri.conf.json` uses empty `bundle.resources`; runtime uses `~/.ghost/venv` + `engine_root.txt` / `GHOST_ENGINE_ROOT`.
- **API** default **8765**; desktop panels call `/health`, `/v1/metrics`, `/v1/bandit/global`, `/v1/retrieve`, `/v1/admin/*` (governance for admin).
- **Rust deployer** starts `python -m uvicorn ghost_api.app:app` with `pip install -e <repo>[embeddings]` for online deploy steps.

## Doctrine

Sovereignty, determinism, auditability, stewardship, explicit boundaries — no edits under legacy `phantom/` or `retrieval-weight-experiment/` trees.
