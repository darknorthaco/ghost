#!/usr/bin/env python3
"""
GHOST Installation Wizard
Windows XP/95-style Tkinter wizard — installation-phase GUI only.

This module provides:
    GHOSTWizard   – main Tk window; owns navigation and layout.
    WizardState     – mutable state accumulated across screens.
    main()          – entry point.

Constitutional pipeline code is NEVER touched here.
"""
from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Type

# Ensure installer root is on sys.path so sibling packages are importable.
_installer_dir = Path(__file__).parent.parent
if str(_installer_dir) not in sys.path:
    sys.path.insert(0, str(_installer_dir))


# ---------------------------------------------------------------------------
# Retro Windows XP / 95 colour theme
# ---------------------------------------------------------------------------

class WinXPTheme:
    """GHOST spectral palette — same wizard layout, Phantom blue replaced."""

    BG = "#0F0F0F"          # Pale black
    SIDEBAR_BG = "#1A1A1A"  # Charcoal
    SIDEBAR_FG = "#E6E6E6"  # Ghost grey
    TITLE_BG = "#1A1A1A"
    TITLE_FG = "#FFFFFF"
    HEADING_FG = "#E6E6E6"
    SEPARATOR = "#2E2E2E"
    BUTTON_BG = "#1A1A1A"
    BUTTON_ACTIVE = "#E6E6E6"
    TEXT_FG = "#E6E6E6"
    ENTRY_BG = "#1A1A1A"
    CHECK_BG = "#0F0F0F"
    ROW_ALT = "#141414"
    SUCCESS = "#006600"
    WARNING = "#996600"
    FAIL = "#CC0000"

    FONT = ("Tahoma", 9)
    FONT_BOLD = ("Tahoma", 9, "bold")
    FONT_HEADING = ("Tahoma", 12, "bold")
    FONT_SIDEBAR = ("Tahoma", 10, "bold")
    FONT_MONO = ("Courier New", 8)


# ---------------------------------------------------------------------------
# Wizard state — accumulated across screens
# ---------------------------------------------------------------------------

@dataclass
class WizardState:
    """Mutable state shared between all wizard screens."""

    # Welcome
    show_detailed_logs: bool = False

    # Installation directory
    install_dir: Path = field(default_factory=lambda: Path.home() / "ghost")

    # Worker discovery
    discovery_mode: str = "comprehensive"
    discovered_workers: List[Dict] = field(default_factory=list)
    selected_workers: List[Dict] = field(default_factory=list)
    task_master: Optional[Dict] = None

    # Model
    selected_model: Optional[Dict] = None
    model_path: Optional[Path] = None

    # Dependency fetch
    dependencies_staged: bool = False
    staging_dir: Optional[Path] = None

    # Reboot / resume
    reboot_required: bool = False
    resume_after_reboot: bool = False

    # Completion
    launch_ghost: bool = True


# ---------------------------------------------------------------------------
# Main wizard window
# ---------------------------------------------------------------------------

class GHOSTWizard(tk.Tk):
    """Main installer wizard window.

    Layout
    ------
    +---sidebar (180px)---+-------content area-----------+
    |                     |  title bar (60px)            |
    |   product logo /    +------------------------------+
    |   step list         |  active screen frame         |
    |                     +------------------------------+
    |                     |  button bar (50px)           |
    +---------------------+------------------------------+
    """

    WINDOW_WIDTH = 720
    WINDOW_HEIGHT = 500

    def __init__(self, resume_idx: int | None = None):
        super().__init__()

        self.theme = WinXPTheme()
        self.state = WizardState()

        # GHOSTInstallerAPI is created lazily once install_dir is known.
        self._api = None

        self.title("GHOST Distributed Compute Fabric — Setup")
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.resizable(False, False)
        self.configure(bg=self.theme.BG)
        try:
            icon_path = _installer_dir / "assets" / "ghost.ico"
            if icon_path.exists():
                self.iconbitmap(default=str(icon_path))
        except Exception:
            pass

        self._build_layout()

        # Import screens lazily to avoid circular imports at module level.
        from gui.screens import (
            WelcomeScreen,
            SystemScanScreen,
            DependencyFetchScreen,
            RebootPromptScreen,
            ResumeScreen,
            WorkerDiscoveryScreen,
            WorkerSelectionScreen,
            ModelSelectionScreen,
            ModelDownloadScreen,
            InstallationScreen,
            CompletionScreen,
        )

        self._screen_classes: List[Type] = [
            WelcomeScreen,        # 0
            SystemScanScreen,     # 1
            DependencyFetchScreen,# 2  — NEW
            RebootPromptScreen,   # 3  — NEW (conditional)
            ResumeScreen,         # 4  — NEW (post-reboot)
            WorkerDiscoveryScreen,# 5
            WorkerSelectionScreen,# 6
            ModelSelectionScreen, # 7
            ModelDownloadScreen,  # 8
            InstallationScreen,   # 9
            CompletionScreen,     # 10
        ]
        self._current_screen = None
        self._idx = 0

        start_idx = resume_idx if resume_idx is not None else 0
        self._show_screen(start_idx)

    # ------------------------------------------------------------------ #
    # Layout construction
    # ------------------------------------------------------------------ #

    def _build_layout(self) -> None:
        t = self.theme

        # --- Sidebar ---
        self.sidebar = tk.Frame(
            self, width=180, bg=t.SIDEBAR_BG
        )
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        tk.Label(
            self.sidebar,
            text="GHOST\nSetup",
            bg=t.SIDEBAR_BG,
            fg=t.SIDEBAR_FG,
            font=("Tahoma", 18, "bold"),
            justify=tk.CENTER,
        ).pack(pady=(30, 10))

        tk.Frame(self.sidebar, bg="#4070C0", height=2).pack(
            fill=tk.X, padx=10, pady=4
        )

        self._sidebar_steps_frame = tk.Frame(self.sidebar, bg=t.SIDEBAR_BG)
        self._sidebar_steps_frame.pack(fill=tk.X, padx=12, pady=6)

        self._sidebar_step_labels: List[tk.Label] = []
        step_names = [
            "Welcome",
            "System Check",
            "Dependencies",
            "Reboot Check",
            "Resume",
            "Discover Workers",
            "Select Workers",
            "Select Model",
            "Download Model",
            "Install",
            "Finish",
        ]
        for name in step_names:
            lbl = tk.Label(
                self._sidebar_steps_frame,
                text=f"  {name}",
                bg=t.SIDEBAR_BG,
                fg=t.SIDEBAR_FG,
                font=t.FONT,
                anchor="w",
            )
            lbl.pack(fill=tk.X, pady=1)
            self._sidebar_step_labels.append(lbl)

        # --- Right content area ---
        self.content_area = tk.Frame(self, bg=t.BG)
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Title bar
        self.title_bar = tk.Frame(
            self.content_area, bg=t.TITLE_BG, height=60
        )
        self.title_bar.pack(fill=tk.X)
        self.title_bar.pack_propagate(False)

        self._title_lbl = tk.Label(
            self.title_bar,
            text="",
            bg=t.TITLE_BG,
            fg=t.TITLE_FG,
            font=t.FONT_HEADING,
            anchor="w",
            padx=16,
        )
        self._title_lbl.pack(side=tk.LEFT, pady=8)

        self._subtitle_lbl = tk.Label(
            self.title_bar,
            text="",
            bg=t.TITLE_BG,
            fg="#C8D8F8",
            font=t.FONT,
            anchor="w",
            padx=16,
        )
        # subtitle sits below title — use a column layout
        self._title_lbl.pack_forget()
        inner = tk.Frame(self.title_bar, bg=t.TITLE_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=14)
        self._title_lbl = tk.Label(
            inner, text="", bg=t.TITLE_BG, fg=t.TITLE_FG,
            font=t.FONT_HEADING, anchor="w"
        )
        self._title_lbl.pack(anchor="w", pady=(8, 0))
        self._subtitle_lbl = tk.Label(
            inner, text="", bg=t.TITLE_BG, fg="#C8D8F8",
            font=t.FONT, anchor="w"
        )
        self._subtitle_lbl.pack(anchor="w")

        # Separator below title
        tk.Frame(self.content_area, bg=t.SEPARATOR, height=1).pack(fill=tk.X)

        # Screen container
        self.screen_container = tk.Frame(self.content_area, bg=t.BG)
        self.screen_container.pack(fill=tk.BOTH, expand=True, padx=18, pady=10)

        # Separator above buttons
        tk.Frame(self.content_area, bg=t.SEPARATOR, height=1).pack(fill=tk.X)

        # Button bar
        btn_bar = tk.Frame(self.content_area, bg=t.BG, height=48)
        btn_bar.pack(fill=tk.X, padx=10)
        btn_bar.pack_propagate(False)

        self._btn_cancel = self._make_button(btn_bar, "Cancel", self._on_cancel)
        self._btn_cancel.pack(side=tk.LEFT, padx=(0, 6), pady=8)

        self._btn_next = self._make_button(btn_bar, "Next  >", self._on_next)
        self._btn_next.pack(side=tk.RIGHT, padx=(6, 0), pady=8)

        self._btn_back = self._make_button(btn_bar, "<  Back", self._on_back)
        self._btn_back.pack(side=tk.RIGHT, padx=2, pady=8)

    def _make_button(self, parent, text: str, cmd) -> tk.Button:
        t = self.theme
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=t.BUTTON_BG,
            fg=t.TEXT_FG,
            font=t.FONT,
            relief=tk.RAISED,
            bd=2,
            width=10,
            cursor="hand2",
            activebackground=t.BUTTON_ACTIVE,
            activeforeground="#FFFFFF",
        )

    # ------------------------------------------------------------------ #
    # Screen navigation
    # ------------------------------------------------------------------ #

    def _show_screen(self, idx: int) -> None:
        if self._current_screen is not None:
            self._current_screen.on_leave()

        # Clear container
        for w in self.screen_container.winfo_children():
            w.destroy()

        self._idx = idx
        cls = self._screen_classes[idx]
        screen = cls(self.screen_container, wizard=self)
        screen.pack(fill=tk.BOTH, expand=True)
        self._current_screen = screen

        # Update title bar
        self._title_lbl.config(text=cls.TITLE)
        self._subtitle_lbl.config(text=cls.SUBTITLE)

        # Update sidebar highlight
        for i, lbl in enumerate(self._sidebar_step_labels):
            if i == idx:
                lbl.config(
                    fg="#FFFF88",
                    font=self.theme.FONT_BOLD,
                )
            elif i < idx:
                lbl.config(fg="#A0C8A0", font=self.theme.FONT)
            else:
                lbl.config(fg=self.theme.SIDEBAR_FG, font=self.theme.FONT)

        screen.on_enter()
        self.refresh_buttons()

    def _on_next(self) -> None:
        if self._idx < len(self._screen_classes) - 1:
            next_idx = self._idx + 1
            # Skip Reboot Prompt (3) if no reboot required
            if next_idx == 3 and not self.state.reboot_required:
                next_idx = 4
            # Skip Resume (4) when moving forward in a non-resume session
            if next_idx == 4 and not self.state.resume_after_reboot:
                next_idx = 5
            self._show_screen(min(next_idx, len(self._screen_classes) - 1))
        else:
            # Last screen — queue headless native install + optional launch
            self._start_post_install()
            self.destroy()

    def _on_back(self) -> None:
        if self._idx > 0:
            self._show_screen(self._idx - 1)

    def _on_cancel(self) -> None:
        if messagebox.askyesno(
            "Cancel Setup",
            "Are you sure you want to cancel the GHOST installation?\n"
            "Setup has not been completed.",
            icon=messagebox.WARNING,
        ):
            self.destroy()

    # ------------------------------------------------------------------ #
    # Button state management
    # ------------------------------------------------------------------ #

    def refresh_buttons(self) -> None:
        """Re-evaluate enabled state for Back / Next based on current screen."""
        is_last = self._idx == len(self._screen_classes) - 1

        # Back
        back_ok = (
            self._idx > 0
            and self._current_screen is not None
            and self._current_screen.can_go_back()
        )
        self._btn_back.config(state=tk.NORMAL if back_ok else tk.DISABLED)

        # Next / Finish
        next_ok = (
            self._current_screen is None
            or self._current_screen.can_go_next()
        )
        self._btn_next.config(
            text="Finish" if is_last else "Next  >",
            state=tk.NORMAL if next_ok else tk.DISABLED,
        )

    def set_next_enabled(self, enabled: bool) -> None:
        self._btn_next.config(state=tk.NORMAL if enabled else tk.DISABLED)

    def set_back_enabled(self, enabled: bool) -> None:
        self._btn_back.config(state=tk.NORMAL if enabled else tk.DISABLED)

    # ------------------------------------------------------------------ #
    # API accessor
    # ------------------------------------------------------------------ #

    @property
    def api(self):
        """Return the GHOSTInstallerAPI, creating it if necessary."""
        if self._api is None:
            from integration.ghost_installer_api import GHOSTInstallerAPI
            self._api = GHOSTInstallerAPI(self.state.install_dir)
        return self._api

    def reset_api(self) -> None:
        """Re-create the API (e.g. after install_dir changes)."""
        self._api = None

    # ------------------------------------------------------------------ #
    # Post-installation (GHOST native: venv, pip -e, API 8765, desktop)
    # ------------------------------------------------------------------ #

    def _start_post_install(self) -> None:
        import os
        import subprocess
        import sys

        env = os.environ.copy()
        env["GHOST_LAUNCH"] = "1" if getattr(self.state, "launch_ghost", True) else "0"
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200
            )
        try:
            subprocess.Popen(
                [sys.executable, "--post-install"],
                env=env,
                close_fds=True,
                creationflags=flags,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(resume_idx: int | None = None) -> None:
    """Launch the GHOST GUI installer wizard.

    Args:
        resume_idx: If set, jump directly to this screen index (post-reboot).
    """
    try:
        app = GHOSTWizard(resume_idx=resume_idx)
        if resume_idx is not None:
            app.state.resume_after_reboot = True
        app.mainloop()
    except tk.TclError as exc:
        print(f"Cannot start GUI: {exc}", file=sys.stderr)
        print(
            "Ensure a display is available or run the CLI installer instead:\n"
            "  python ghost_installer.py",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
