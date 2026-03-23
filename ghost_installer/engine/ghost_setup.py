"""Structured installation steps for GHOST — offline-first, auditable."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from . import fdx_log

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
        fdx_log.append_installer(
            phase="installer",
            step="venv",
            status="success",
            message="venv already present",
            details={"venv_dir": str(venv_dir)},
        )
        return py
    fdx_log.append_installer(
        phase="installer",
        step="venv",
        status="start",
        message="creating venv",
        details={"venv_dir": str(venv_dir)},
    )
    logging.info("creating venv at %s", venv_dir)
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    except subprocess.CalledProcessError as e:
        err = f"venv creation failed (exit {e.returncode})"
        fdx_log.append_installer(
            phase="installer",
            step="venv",
            status="error",
            message=err,
            error=err,
            details={"venv_dir": str(venv_dir)},
        )
        raise
    fdx_log.append_installer(
        phase="installer",
        step="venv",
        status="success",
        message="venv created",
        details={"venv_dir": str(venv_dir), "python": str(py)},
    )
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
    fdx_log.append_installer(
        phase="installer",
        step="pip_install",
        status="start",
        message="pip install -e (toolchain + package)",
        details={"spec": spec, "pip": str(pip_exe)},
    )
    logging.info("pip install -e %s", spec)
    try:
        subprocess.run(
            [str(pip_exe), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        err = f"pip toolchain upgrade failed (exit {e.returncode})"
        fdx_log.append_installer(
            phase="installer",
            step="pip_toolchain",
            status="error",
            message=err,
            error=err,
        )
        raise
    try:
        subprocess.run([str(pip_exe), "-m", "pip", "install", "-e", spec], check=True)
    except subprocess.CalledProcessError as e:
        err = f"pip install -e failed (exit {e.returncode})"
        fdx_log.append_installer(
            phase="installer",
            step="pip_install",
            status="error",
            message=err,
            error=err,
            details={"spec": spec},
        )
        raise
    if ghost_home is not None:
        write_engine_root_marker(ghost_home, engine_root)
    fdx_log.append_installer(
        phase="installer",
        step="pip_install",
        status="success",
        message="editable install complete",
        details={"spec": spec},
    )


def run_ghost_init_db(python_exe: Path) -> None:
    root = default_engine_root()
    fdx_log.append_installer(
        phase="installer",
        step="init_db",
        status="start",
        message="ghost init-db",
        details={"cwd": str(root)},
    )
    logging.info("ghost init-db (cwd=%s)", root)
    try:
        subprocess.run(
            [str(python_exe), "-m", "ghost_cli.main", "init-db"],
            cwd=str(root),
            check=True,
        )
    except subprocess.CalledProcessError as e:
        err = f"init-db failed (exit {e.returncode})"
        fdx_log.append_installer(
            phase="installer",
            step="init_db",
            status="error",
            message=err,
            error=err,
            details={"cwd": str(root)},
        )
        raise
    fdx_log.append_installer(
        phase="installer",
        step="init_db",
        status="success",
        message="init-db complete",
        details={"cwd": str(root)},
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
