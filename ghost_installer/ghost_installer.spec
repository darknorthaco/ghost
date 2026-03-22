# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — GHOST Setup Wizard (one-file). Bundles engine source + desktop ghost_app.exe.
# Run from repo:  cd ghost_installer && pyinstaller ghost_installer.spec
# Requires: Tauri release build at ../ghost_app/src-tauri/target/release/ghost_app.exe

import os

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis

block_cipher = None

ROOT = os.path.dirname(os.path.abspath(SPEC))
REPO = os.path.normpath(os.path.join(ROOT, ".."))
DESKTOP = os.path.join(REPO, "ghost_app", "src-tauri", "target", "release", "ghost_app.exe")

datas = [
    (os.path.join(ROOT, "gui"), "gui"),
    (os.path.join(ROOT, "engine"), "engine"),
    (os.path.join(ROOT, "modules"), "modules"),
    (os.path.join(ROOT, "backend_interface"), "backend_interface"),
    (os.path.join(ROOT, "integration"), "integration"),
    (os.path.join(ROOT, "ui"), "ui"),
]

_pkgs = [
    "ghost_core",
    "ghost_api",
    "ghost_cli",
    "ghost_retrieval",
    "ghost_optimizer",
    "ghost_governance",
    "ghost_orchestrator",
    "config",
]
for name in _pkgs:
    src = os.path.join(REPO, name)
    if os.path.isdir(src):
        datas.append((src, os.path.join("engine_repo", name)))

_py = os.path.join(REPO, "pyproject.toml")
if os.path.isfile(_py):
    datas.append((_py, os.path.join("engine_repo", "pyproject.toml")))

binaries = []
if os.path.isfile(DESKTOP):
    binaries.append((DESKTOP, "bundled"))
else:
    print("WARNING: ghost_app.exe not found — build Tauri first:", DESKTOP)

a = Analysis(
    [os.path.join(ROOT, "ghost_wizard.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.font",
        "engine.native_install",
        "engine.ghost_setup",
        "integration.ghost_installer_api",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ghost",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
