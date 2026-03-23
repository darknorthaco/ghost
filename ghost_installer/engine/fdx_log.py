"""FDX — append-only JSONL installer observability under ~/.ghost/logs/."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _ghost_logs_dir() -> Path:
    base = Path.home() / ".ghost" / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def append_installer(
    *,
    phase: str,
    step: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
    error: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "phase": phase,
        "step": step,
        "status": status,
        "message": message,
    }
    if details is not None:
        entry["details"] = details
    if error is not None:
        entry["error"] = error
    if context is not None:
        entry["context"] = context
    path = _ghost_logs_dir() / "installer_fdx.jsonl"
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[fdx_log] failed to write {path}: {e}", file=sys.stderr)
