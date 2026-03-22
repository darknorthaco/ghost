"""Structured installation steps for GHOST — offline-first, auditable."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

# Default: repository root containing pyproject.toml (parent of ghost_installer/)
def default_engine_root() -> Path:
    env = os.environ.get("GHOST_ENGINE_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def install_log_path() -> Path:
    p = Path.home() / ".ghost" / "logs" / "install.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(install_log_path(), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def ensure_venv(venv_dir: Path) -> Path:
    """Create a venv if missing; return path to python.exe (Windows)."""
    py = venv_dir / "Scripts" / "python.exe"
    if sys.platform != "win32":
        py = venv_dir / "bin" / "python"
    if py.exists():
        logging.info("venv exists: %s", venv_dir)
        return py
    logging.info("creating venv at %s", venv_dir)
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    return py


def write_engine_root_marker(ghost_home: Path, engine_root: Path) -> None:
    """Record repo root so the desktop app can run uvicorn without bundling Python."""
    p = ghost_home / "engine_root.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(engine_root.resolve()), encoding="utf-8")
    logging.info("wrote engine root marker: %s", p)


def pip_install_ghost(engine_root: Path, pip_exe: Path, extras: str = "[embeddings]", ghost_home: Path | None = None) -> None:
    """Editable install of GHOST from source."""
    spec = f"{engine_root}{extras}"
    logging.info("pip install -e %s", spec)
    subprocess.run(
        [str(pip_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        check=True,
    )
    subprocess.run([str(pip_exe), "-m", "pip", "install", "-e", spec], check=True)
    if ghost_home is not None:
        write_engine_root_marker(ghost_home, engine_root)


def run_ghost_init_db(python_exe: Path) -> None:
    root = default_engine_root()
    logging.info("ghost init-db (cwd=%s)", root)
    subprocess.run(
        [str(python_exe), "-m", "ghost_cli.main", "init-db"],
        cwd=str(root),
        check=True,
    )


def run_ghost_serve(python_exe: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start API server (blocking; for post-install launch or subprocess)."""
    logging.info("ghost serve %s:%s", host, port)
    root = default_engine_root()
    subprocess.run(
        [
            str(python_exe),
            "-m",
            "uvicorn",
            "ghost_api.app:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(root),
        check=False,
    )
