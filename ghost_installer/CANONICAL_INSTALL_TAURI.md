# Canonical installer: Tauri desktop app

As of Phase 2 (production readiness), **GHOST’s single supported installation path is the Tauri-based GHOST application** in `ghost_app/`.

## This directory (`installer/`)

The Python wizard, CLI orchestrator, and integration tests under `installer/` remain in the tree for:

- Reference implementations of worker discovery, model download, and config writers  
- Automated tests (`ghost_core/tests/test_wizard_backend.py`, etc.)  
- Emergency use when `GHOST_ALLOW_LEGACY_INSTALLER=1` is set  

They **must not** be presented to end users as the default install path. User-facing documentation lives in **`INSTALL.md`** (repository root).

## Entry points gated by default

| Script | Behavior without env override |
|--------|-------------------------------|
| `ghost_installer.py` | Exits with code 2 + message |
| `ghost_wizard.py` | Exits with code 2 + message |
| `ghost_installer_windows.py` | Exits with code 2 + message |
| `windows_gui_installer.py` | Exits with code 2 + message |
| `demo_installer.py` | Exits with code 2 + message |

Override: **`GHOST_ALLOW_LEGACY_INSTALLER=1`**

## Uninstaller scripts

`ghost_uninstaller.*` remain available for environments that still rely on legacy layouts; prefer **`uninstall_ghost`** from the Tauri app for the `~/.ghost` / `%USERPROFILE%\.ghost` layout.
