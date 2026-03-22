"""One-shot rename phantom_* Rust modules and identifiers to ghost_* (ghost_app/src-tauri only)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ghost_app" / "src-tauri" / "src"

# Longest-first token replacements in file content
REPLACEMENTS: list[tuple[str, str]] = [
    ("upgrade_phantom_deployment", "upgrade_ghost_deployment"),
    ("remove_windows_firewall_phantom_rules", "remove_windows_firewall_ghost_rules"),
    ("read_phantom_tls_for_local_worker", "read_ghost_tls_for_local_worker"),
    ("install_phantom_core", "install_ghost_core"),
    ("stop_phantom_services", "stop_ghost_services"),
    ("uninstall_phantom", "uninstall_ghost"),
    ("phantom_deployer", "ghost_deployer"),
    ("phantom_api", "ghost_api"),
    ("phantom_state", "ghost_state"),
    ("PhantomTlsSettings", "GhostTlsSettings"),
    ("PhantomDeployer", "GhostDeployer"),
    ("PhantomApiClient", "GhostApiClient"),
    ("PhantomMetrics", "GhostMetrics"),
    ("phantom_config.json", "ghost_config.json"),
    ("phantom_root", "ghost_root"),
    ("phantom.crt", "ghost.crt"),
    ("phantom.key", "ghost.key"),
    ("phantom.service", "ghost.service"),
    ("phantom-controller.local", "ghost-controller.local"),
    ("phantom-controller", "ghost-controller"),
    (".phantom", ".ghost"),
    ("phantom_core", "ghost_core"),
    ("PHANTOM_OFFLINE_BUNDLE", "GHOST_OFFLINE_BUNDLE"),
    ("PhantomController", "GhostController"),
    ("PhantomWorker", "GhostWorker"),
    ("PhantomDiscovery", "GhostDiscovery"),
    ("PhantomSocket", "GhostSocket"),
    ("phantom_uninstall", "ghost_uninstall"),
    ("phantom_upgrade", "ghost_upgrade"),
    ("phantom_tls", "ghost_tls"),
    ("`phantom`", "`ghost`"),
    ('"phantom"', '"ghost"'),
    ("http://127.0.0.1:8080", "http://127.0.0.1:8765"),
]


def process_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new = text
    for old, new_s in REPLACEMENTS:
        new = new.replace(old, new_s)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> None:
    # Rename module files first so `mod ghost_*` matches filenames after text replace
    b = ROOT / "backend"
    for old_name, new_name in [
        ("phantom_api.rs", "ghost_api.rs"),
        ("phantom_deployer.rs", "ghost_deployer.rs"),
        ("phantom_state.rs", "ghost_state.rs"),
    ]:
        o = b / old_name
        n = b / new_name
        if o.exists() and not n.exists():
            shutil.move(str(o), str(n))
    for path in sorted(ROOT.rglob("*.rs")):
        process_file(path)


if __name__ == "__main__":
    main()
