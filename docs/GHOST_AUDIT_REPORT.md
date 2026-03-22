# GHOST Product Suite — Workspace Audit Report

**Date:** Generated during transformation. **Constraint:** `phantom/` and `retrieval-weight-experiment/` were not modified; they remain reference trees.

---

## 1. Phantom installer wizard shell — **YES, EXISTS**

| Location | Role |
|----------|------|
| `phantom/installer/phantom_wizard.py` | Tkinter entry; delegates to `gui/wizard.py` |
| `phantom/installer/gui/wizard.py` | Multi-screen wizard controller |
| `phantom/installer/gui/screens/*.py` | Welcome, system scan, worker selection, model download, installation, completion, reboot, resume, etc. |
| `phantom/installer/backend_interface/*` | Config writer, dependency fetcher, reboot manager, installer driver, model downloader, worker discovery |
| `phantom/installer/modules/*` | venv, component manager, worker discovery, port verifier, manifest |
| `phantom/installer/config/ui_config.yaml` | UI theme tokens (primary `#3b82f6`, etc.) |
| `phantom/installer/build/` | PyInstaller spec, Nuitka, `build_exe.py`, `freeze_manifest.json` |

**Stack:** Python + Tkinter GUI, optional CLI (`phantom_installer.py`), PowerShell/bash wrappers.

---

## 2. Phantom desktop application GUI shell — **YES, EXISTS**

| Location | Role |
|----------|------|
| `phantom/phantom_app/` | **Tauri 2 + React (TSX) + Vite** desktop shell |
| `phantom/phantom_app/src/App.tsx` | Phases: wizard → controller selection → deploy → ceremony → TOC with sidebar (console, workers, routing, models, deployments, audit, chat, etc.) |
| `phantom/phantom_app/src-tauri/` | Rust backend: `phantom_deployer.rs`, `offline_bundle.rs`, TLS, resource bundling of `phantom_core/` |
| `phantom/phantom_app/src/styles/theme.css` | Dark blue / slate tokens (`--accent-blue: #00a6ff`, backgrounds `#0a0a0f`–`#1e1e2a`) |
| `phantom/phantom_app/src/styles/deploy.css` | Wizard/deploy animations (`.phantom-mask-*`, `@keyframes phantomPulse`) |

**Integration point:** Frontend `fetch('http://127.0.0.1:8080/health')` and Tauri `invoke()` commands (`deploy_phantom`, `get_phantom_health`, `save_phantom_tls_settings`, etc.).

---

## 3. UI assets, tokens, CSS, themes, icons, branding

| Asset | Path |
|-------|------|
| Logo (UI) | `phantom_app/public/phantom.png` (referenced); `phantom.svg`, `tauri.svg`, `vite.svg` |
| Tauri icons | `phantom_app/src-tauri/icons/*.png`, `icon.ico`, `icon.icns` |
| Primary theme | `src/styles/theme.css` |
| Deploy/wizard | `src/styles/deploy.css`, `toc.css` |
| Installer UI config | `installer/config/ui_config.yaml` (title “Phantom Distributed Compute Fabric”, blue/purple) |
| Matrix demo (non-core) | `phantom/ui/redblue_matrix/` (web + React Native examples) |
| Simple web example | `phantom/ui/examples/simple_web_ui/` |

---

## 4. Phantom-specific names, strings, IDs, service labels

- **Product:** “Phantom”, “Phantom — Sovereign Distributed Compute”, “Phantom Distributed Compute Fabric”, “Phantom Tactical Operations Center”.
- **Tauri:** `productName: "Phantom"`, `identifier: "com.darknorth.phantom"`, window title, bundle `resources/phantom_core/**/*`.
- **Paths:** `~/.phantom/`, `phantom_config.json`, `phantom_audit.jsonl`, `phantomctl` (docs).
- **npm:** `name: "phantom_app"`.
- **Worker:** Port patterns 8080 controller, 8090 worker (GHOST uses 8765 for API in current engine).

---

## 5. Plugin architecture (Phantom)

| Layer | Detail |
|-------|--------|
| **Workers** | `phantom_core/linux-worker/plugins/` — `PluginManager`, task-type → plugin (`execute_task`). |
| **Tauri** | `tauri_plugin_opener` only in `lib.rs`; no JS plugin SDK in the desktop app itself. |
| **Desktop** | Panels are **React components** (sidebar routing), not dynamic third-party plugins. “Plugin” parity for GHOST = **same panel architecture + extension points** (load future GHOST plugins from a known directory/API). |

---

## 6. Existing GHOST installer / GUI scaffolding (before this task)

- **None** under `ghost_installer/` or `ghost_app/` — only Python package `ghost_*`, `ghost_api`, `ghost_cli`, FastAPI, tests.
- Engine: local SQLite, `/v1/*` on port **8765** (default).

---

## 7. Integration points (Phantom UI ↔ engine)

1. **HTTP:** `127.0.0.1:8080` health and controller API.
2. **Tauri commands:** Deploy bundle, TLS save, health, offline bundle paths — Rust `lib.rs` + `phantom_deployer.rs`.
3. **Bundled resources:** `phantom_core/` copied into Tauri bundle for deployment.
4. **Installer:** Writes config under user home, sets up venv, optional model download, worker discovery.

**GHOST mapping:** Point HTTP to `http://127.0.0.1:8765` (or config-driven); replace deploy pipeline with `pip install`, `ghost init-db`, `ghost token-register`, `ghost serve`; TLS/worker steps optional and explicit.

---

## 8. Summary verdict

| Item | Status |
|------|--------|
| Installer wizard shell | **Present** (Tkinter + Python modules + build scripts) |
| Desktop GUI shell | **Present** (Tauri + React) |
| Reusable without editing `phantom/` | **Yes** — copy to `ghost_installer/` and `ghost_app/`, then rebrand/bind |
| Single EXE for Windows | **Pattern exists** (`installer/build/phantom_installer.spec`, Nuitka docs); GHOST needs analogous `ghost_installer` spec |

---

*End of audit report.*
