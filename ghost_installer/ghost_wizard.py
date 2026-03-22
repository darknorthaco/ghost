#!/usr/bin/env python3
"""
GHOST GUI Installation Wizard — entry point (spectral Tk shell).

Run:
    python ghost_wizard.py

Requires Tkinter. Full engine install (venv, pip, init-db) is orchestrated
via `engine/ghost_setup.py` for scripted/automated flows; the Tk wizard
remains the interactive UI shell preserved from the upstream lineage.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

# Default engine root = repo root (parent of ghost_installer/)
if not os.environ.get("GHOST_ENGINE_ROOT"):
    os.environ["GHOST_ENGINE_ROOT"] = str(_here.parent)

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GHOST — Setup Wizard")
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume after reboot (if supported by wizard state).",
    )
    p.add_argument(
        "--post-install",
        action="store_true",
        help="Headless: materialize engine, venv, pip install, init-db, token, launch (internal).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.post_install:
        from engine.native_install import main as native_main

        native_main()
        sys.exit(0)

    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError:
        print(
            "ERROR: Tkinter is not available.\n"
            "  On Windows/macOS Python includes Tkinter.\n"
            "  On Debian/Ubuntu: sudo apt-get install python3-tk\n",
            file=sys.stderr,
        )
        sys.exit(1)

    from gui.wizard import main as wizard_main

    wizard_main(resume_idx=None)
