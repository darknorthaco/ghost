# GHOST Transformation Plan (Phantom shells → GHOST)

## Goals

1. **Recycle** installer and desktop shells by **copy** (not edit) from `phantom/installer` → `ghost_installer/`, `phantom/phantom_app` → `ghost_app/`.
2. **Rebrand** all user-visible and identifier strings Phantom → GHOST / ghost.
3. **Spectral palette** replace blue-accent dark theme with GHOST colors (see `ghost_app/src/styles/theme.css`).
4. **Engine bind:** Desktop → `http://127.0.0.1:8765` (GHOST FastAPI); installer → venv + `pip install -e ".[embeddings]"` + `ghost init-db` + optional governance token + `ghost serve`.
5. **Do not** modify `phantom/` or `retrieval-weight-experiment/`.

## Phases

| Phase | Work |
|-------|------|
| A | Copy trees excluding `node_modules`, `target`, `dist`, build caches |
| B | Controlled string/asset rebrand + rename `phantom.png` usage → `ghost.svg` |
| C | Tauri `tauri.conf.json`: product name, identifier, window title, bundle resource paths for future `ghost_core` or pip-based layout |
| D | Rust `lib.rs`: rename invoke commands to `deploy_ghost`, `get_ghost_health`, etc. (incremental) |
| E | Installer: add `ghost_wizard.py`, `ghost_installer_driver.py` calling GHOST CLI; audit log file under `%USERPROFILE%\.ghost\logs\install.log` |
| F | PyInstaller / NSIS: new spec `ghost_installer.spec` mirroring Phantom build README |
| G | Desktop: panels wired to `/health`, `/v1/metrics`, `/v1/bandit/{scope}` (incremental) |

## Remaining work (post-scaffold)

- Full **Tauri** Rust command renames and removal of `phantom_core` bundle until replaced by pip-installed `ghost` package path.
- **Windows service** registration script (optional, admin) — separate PowerShell, policy-gated.
- **Plugin panel** dynamic loading — mirror worker plugin pattern via GHOST plugin manifest directory (future).
- **End-to-end** build: `npm run tauri build` inside `ghost_app` after `npm install`.

---

*See also `docs/GHOST_SHELL_ADAPTATION.md` after implementation.*
