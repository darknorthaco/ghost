# How Phantom shells were adapted to GHOST

## Copy-only rule

- Source trees were **copied** from `phantom/installer` → `ghost_installer/` and `phantom/phantom_app` → `ghost_app/` with **no edits** under `phantom/`.
- Build artifacts (`node_modules`, `src-tauri/target`, `dist`) were excluded from the copy.

## Rebranding

- Script `scripts/rebrand_shells.py` performs **ordered** replacements (Phantom → GHOST, `phantom_core` → `ghost_core`, API port 8080 → **8765**, invoke names aligned where TS was updated).
- Desktop **console** component file renamed: `PhantomConsole.tsx` → `GhostConsole.tsx`.
- **Public assets:** `public/ghost.svg` copied from `phantom.svg`; HTML references `ghost.svg` favicon.
- **Tauri Rust:** `lib.rs` command symbols aligned for the three primary deployment/TLS/health commands: `save_ghost_tls_settings`, `deploy_ghost`, `get_ghost_health`.

## Spectral theme

- `ghost_app/src/styles/theme.css` — GHOST palette (`#0F0F0F`, `#1A1A1A`, `#E6E6E6`, `#FFFFFF`) plus `--accent-blue` aliases pointing at spectral accents so existing `deploy.css` / `toc.css` layout remains.
- `ghost_installer/gui/wizard.py` — `WinXPTheme` sidebar/background colors moved from blue XP style to **charcoal / pale black / ghost grey** while keeping the same wizard structure.

## Engine integration

| Surface | Binding |
|---------|---------|
| Desktop health | `fetch http://127.0.0.1:8765/health` — treats `status === 'ok'` (and legacy `'healthy'`) |
| FastAPI | Existing `ghost_api` on port **8765** |
| Installer automation | `ghost_installer/engine/ghost_setup.py` — venv, `pip install -e .[embeddings]`, `ghost init-db`, optional `uvicorn` launch; logs under `~/.ghost/logs/install.log` |
| Wizard entry | `ghost_installer/ghost_wizard.py` → existing `gui/wizard.py` Tk flow |

## Finalization (this pass)

- **Rust:** `ghost_root`, `ghost_config.json`, `~/.ghost`; deploy **`start_controller`** runs `uvicorn ghost_api.app:app` (editable install); **`install_python_deps`** uses `pip install -e <repo>[embeddings]` when online.
- **Tauri bundle:** `bundle.resources` is **empty** (Option B — no embedded Python tree).
- **Installer API module:** `integration/ghost_installer_api.py` (replaces legacy filename).
- **PyInstaller:** `ghost_installer/ghost_installer.spec` + `ghost_installer/build/README_BUILD.md`.
- **Desktop UI:** Metrics merge `/health` + `/v1/metrics`; Bandit/Routing panels use `/v1/bandit/global`; Chat uses `/v1/retrieve`; Deployments probes `/v1/metrics`.

---

*See `docs/GHOST_AUDIT_REPORT.md` and `docs/GHOST_TRANSFORMATION_PLAN.md`.*
