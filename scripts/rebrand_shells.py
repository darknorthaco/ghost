"""Controlled rebrand for ghost_app and ghost_installer (Option C — Phantom → GHOST)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "ghost_app", ROOT / "ghost_installer"]
SKIP_DIRS = {"node_modules", "target", "dist", ".git", ".vite", "__pycache__", "build"}
TEXT_EXT = {
    ".tsx",
    ".ts",
    ".css",
    ".html",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".py",
    ".toml",
    ".ps1",
    ".sh",
    ".mjs",
    ".rc",
    ".svg",
}


def skip_path(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)


def rebrand_text(s: str) -> str:
    # Longest / specific identifiers first (avoid GHOSTDeployer)
    s = s.replace("PhantomDeployer", "GhostDeployer")
    s = s.replace("PhantomApiClient", "GhostApiClient")
    s = s.replace("PhantomMetrics", "GhostMetrics")
    s = s.replace("PhantomTlsSettings", "GhostTlsSettings")
    s = s.replace("PhantomAppState", "GhostAppState")
    s = s.replace("PhantomConsole", "GhostConsole")
    # API / ports
    s = s.replace("127.0.0.1:8080", "127.0.0.1:8765")
    s = s.replace("localhost:8080", "localhost:8765")
    s = s.replace(":8080", ":8765")
    # Tauri commands (camelCase)
    s = s.replace("savePhantomTlsSettings", "saveGhostTlsSettings")
    s = s.replace("getPhantomHealth", "getGhostHealth")
    s = s.replace("deployPhantom", "deployGhost")
    s = s.replace("save_phantom_tls_settings", "save_ghost_tls_settings")
    s = s.replace("get_phantom_health", "get_ghost_health")
    s = s.replace("deploy_phantom", "deploy_ghost")
    # Packages / paths
    s = s.replace("phantom_core", "ghost_core")
    s = s.replace("phantom-core", "ghost-core")
    s = s.replace("phantom_config", "ghost_config")
    s = s.replace("phantom_audit", "ghost_audit")
    s = s.replace("phantomctl", "ghostctl")
    s = s.replace("PHANTOM_OFFLINE_BUNDLE", "GHOST_OFFLINE_BUNDLE")
    s = s.replace("/phantom.png", "/ghost.svg")
    s = s.replace("phantom.png", "ghost.svg")
    s = s.replace("phantom.svg", "ghost.svg")
    s = s.replace("phantom-mask", "ghost-mask")
    s = s.replace("phantomPulse", "ghostPulse")
    s = s.replace("phantom-mask-container", "ghost-mask-container")
    s = s.replace("phantom-mask-svg", "ghost-mask-svg")
    s = s.replace("com.darknorth.phantom", "com.darknorth.ghost")
    # Brand names (after specific Phantom* types)
    s = s.replace("Phantom", "GHOST")
    s = s.replace("PHANTOM", "GHOST")
    s = s.replace("phantom", "ghost")
    return s


def rename_phantom_files(base: Path) -> None:
    """Rename paths containing 'phantom' → 'ghost' (deepest paths first)."""
    if not base.is_dir():
        return
    all_paths = sorted(
        [p for p in base.rglob("*") if "phantom" in p.name.lower()],
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for path in all_paths:
        if skip_path(path):
            continue
        new_name = path.name.replace("phantom", "ghost").replace("Phantom", "ghost")
        if new_name != path.name:
            dest = path.with_name(new_name)
            if not dest.exists():
                path.rename(dest)


def main() -> None:
    public = ROOT / "ghost_app" / "public"
    if (public / "phantom.svg").exists() and not (public / "ghost.svg").exists():
        shutil.copy2(public / "phantom.svg", public / "ghost.svg")

    for base in TARGETS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_dir() or skip_path(path):
                continue
            suf = path.suffix.lower()
            if suf not in TEXT_EXT and path.suffix not in TEXT_EXT:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new = rebrand_text(text)
            if new != text:
                path.write_text(new, encoding="utf-8")

    for base in TARGETS:
        rename_phantom_files(base)


if __name__ == "__main__":
    main()
