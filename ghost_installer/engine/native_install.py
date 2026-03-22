"""
Headless GHOST install + launch — invoked as: ghost_installer.exe --post-install

Copies bundled engine source to ~/.ghost/engine_src (frozen), creates venv,
pip install -e, init-db, governance token registration, engine_root.txt,
installs desktop EXE to ~/.ghost/bin/, optionally starts API + desktop.
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from engine.ghost_setup import (
    configure_logging,
    install_log_path,
    pip_install_ghost,
    run_ghost_init_db,
)


def _repo_root_dev() -> Path:
    return Path(__file__).resolve().parents[2]


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return _repo_root_dev()


def _engine_src_for_install(ghost_home: Path) -> Path:
    """Editable install root: materialized bundle (frozen) or repo (dev)."""
    if getattr(sys, "frozen", False):
        bundled = _bundle_root() / "engine_repo"
        if not bundled.is_dir():
            raise RuntimeError(f"Bundled engine_repo missing at {bundled}")
        dest = ghost_home / "engine_src"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(bundled, dest)
        logging.info("materialized engine to %s", dest)
        return dest
    root = Path(os.environ.get("GHOST_ENGINE_ROOT", str(_repo_root_dev()))).resolve()
    if not (root / "pyproject.toml").is_file():
        raise RuntimeError(f"GHOST_ENGINE_ROOT invalid: {root}")
    return root


def _venv_python(ghost_home: Path) -> Path:
    if sys.platform == "win32":
        return ghost_home / "venv" / "Scripts" / "python.exe"
    return ghost_home / "venv" / "bin" / "python3"


def _venv_pip(ghost_home: Path) -> Path:
    if sys.platform == "win32":
        return ghost_home / "venv" / "Scripts" / "pip.exe"
    return ghost_home / "venv" / "bin" / "pip"


def find_python() -> Path:
    candidates: list[list[str]] = [["python"], ["py", "-3.12"], ["py", "-3.11"], ["py", "-3"]]
    for cmd in candidates:
        try:
            out = subprocess.run(
                cmd + ["-c", "import sys; print(sys.executable); assert sys.version_info >= (3, 11)"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if out.returncode == 0 and out.stdout.strip():
                return Path(out.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError(
        "Python 3.11+ not found. Install from https://www.python.org/downloads/windows/ "
        "or: winget install Python.Python.3.12"
    )


def try_install_python_windows() -> bool:
    if sys.platform != "win32":
        return False
    winget = shutil.which("winget")
    if not winget:
        return False
    logging.info("Attempting winget install Python.Python.3.12 …")
    r = subprocess.run(
        [winget, "install", "Python.Python.3.12", "--silent", "--accept-package-agreements"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    logging.info("winget exit=%s out=%s err=%s", r.returncode, r.stdout[:500], r.stderr[:500])
    return r.returncode == 0


def ensure_venv(ghost_home: Path, base_python: Path) -> Path:
    """Create ~/.ghost/venv using the given interpreter."""
    vdir = ghost_home / "venv"
    py = _venv_python(ghost_home)
    if py.exists():
        logging.info("venv exists: %s", vdir)
        return py
    logging.info("creating venv with %s at %s", base_python, vdir)
    ghost_home.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(base_python), "-m", "venv", str(vdir)], check=True)
    return _venv_python(ghost_home)


def bundled_desktop_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "bundled" / "ghost_app.exe"  # noqa: SLF001
        return p if p.is_file() else None
    p = _repo_root_dev() / "ghost_app" / "src-tauri" / "target" / "release" / "ghost_app.exe"
    return p if p.is_file() else None


def install_desktop_binary(ghost_home: Path) -> Path | None:
    src = bundled_desktop_exe()
    if src is None:
        logging.warning("No bundled ghost_app.exe — skip desktop copy")
        return None
    dest_dir = ghost_home / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "GHOST.exe"
    shutil.copy2(src, dest)
    logging.info("installed desktop: %s", dest)
    return dest


def register_governance_token(python_exe: Path, engine_root: Path) -> str:
    token = secrets.token_urlsafe(24)
    subprocess.run(
        [str(python_exe), "-m", "ghost_cli.main", "token-register", token, "--label", "installer"],
        cwd=str(engine_root),
        check=True,
    )
    gh = Path.home() / ".ghost"
    gh.mkdir(parents=True, exist_ok=True)
    p = gh / "governance_token.txt"
    p.write_text(
        f"{token}\n# Use HTTP header X-Ghost-Policy-Approve: {token} for admin API calls.\n",
        encoding="utf-8",
    )
    logging.info("governance token written to %s", p)
    return token


def run_full_install(ghost_home: Path | None = None) -> Path:
    configure_logging()
    ghost_home = ghost_home or (Path.home() / ".ghost")
    ghost_home.mkdir(parents=True, exist_ok=True)

    try:
        py = find_python()
    except RuntimeError:
        if try_install_python_windows():
            py = find_python()
        else:
            raise

    engine_root = _engine_src_for_install(ghost_home)
    os.environ["GHOST_ENGINE_ROOT"] = str(engine_root)

    vpy = ensure_venv(ghost_home, py)
    pip_install_ghost(engine_root, _venv_pip(ghost_home), ghost_home=ghost_home)

    run_ghost_init_db(vpy)
    register_governance_token(vpy, engine_root)
    install_desktop_binary(ghost_home)

    logging.info("GHOST install complete — engine_root=%s", engine_root)
    return engine_root


def _win_no_window() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def launch_api(engine_root: Path, ghost_home: Path) -> None:
    vpy = _venv_python(ghost_home)
    subprocess.Popen(
        [
            str(vpy),
            "-m",
            "uvicorn",
            "ghost_api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        cwd=str(engine_root),
        env={**os.environ, "GHOST_ENGINE_ROOT": str(engine_root)},
        creationflags=_win_no_window(),
        close_fds=True,
    )
    logging.info("GHOST API launch requested on 127.0.0.1:8765")


def launch_desktop(ghost_home: Path) -> None:
    exe = ghost_home / "bin" / "GHOST.exe"
    if not exe.is_file():
        logging.warning("Desktop binary not at %s", exe)
        return
    subprocess.Popen([str(exe)], creationflags=_win_no_window(), close_fds=True)
    logging.info("GHOST desktop launch requested")


def main() -> None:
    configure_logging()
    log_path = install_log_path()
    logging.info("native_install starting — log=%s", log_path)
    try:
        gh = Path.home() / ".ghost"
        er = run_full_install(gh)
        if os.environ.get("GHOST_LAUNCH", "1") == "1":
            launch_api(er, gh)
            launch_desktop(gh)
    except Exception:
        logging.exception("native_install failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
