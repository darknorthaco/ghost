"""One-shot controlled rebrand for ghost_app and ghost_installer copies only."""

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
    # ".rs",  # Rust module paths must match filenames; patch lib.rs separately
    ".toml",
    ".ps1",
    ".sh",
    ".mjs",
    ".rc",
}


def skip_path(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts)


def rebrand_text(s: str) -> str:
    # API default for GHOST engine
    s = s.replace("127.0.0.1:8080", "127.0.0.1:8765")
    s = s.replace("localhost:8080", "localhost:8765")
    # Identifier-style (longest first)
    s = s.replace("savePhantomTlsSettings", "saveGhostTlsSettings")
    s = s.replace("getPhantomHealth", "getGhostHealth")
    s = s.replace("deployPhantom", "deployGhost")
    s = s.replace("save_phantom_tls_settings", "save_ghost_tls_settings")
    s = s.replace("get_phantom_health", "get_ghost_health")
    s = s.replace("deploy_phantom", "deploy_ghost")
    s = s.replace("phantom_core", "ghost_core")
    s = s.replace("phantom-core", "ghost-core")
    s = s.replace("phantom_config", "ghost_config")
    s = s.replace("phantom_audit", "ghost_audit")
    s = s.replace("phantomctl", "ghostctl")
    s = s.replace("/phantom.png", "/ghost.svg")
    s = s.replace("phantom.png", "ghost.svg")
    s = s.replace("phantom.svg", "ghost.svg")
    s = s.replace("phantom-mask", "ghost-mask")
    s = s.replace("phantomPulse", "ghostPulse")
    s = s.replace("PhantomConsole", "GhostConsole")
    s = s.replace("phantom-mask-container", "ghost-mask-container")
    s = s.replace("phantom-mask-svg", "ghost-mask-svg")
    s = s.replace("com.darknorth.phantom", "com.darknorth.ghost")
    # Brand names
    s = s.replace("Phantom", "GHOST")
    s = s.replace("PHANTOM", "GHOST")
    s = s.replace("phantom", "ghost")
    return s


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
            if path.suffix.lower() not in TEXT_EXT and path.suffix not in TEXT_EXT:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            new = rebrand_text(text)
            if new != text:
                path.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    main()
