"""One-shot initialization from config (paths, presets, bandit arms)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ghost_core.config import project_root
from ghost_core.storage import init_bandit_arms, init_db, open_sqlite, seed_preset_from_weights


def ensure_ghost_db(sqlite_path: str | Path, config: dict[str, Any] | None = None) -> Any:
    """Create DB file, apply schema, seed presets from `config/presets/*.yaml`."""
    import sqlite3

    conn: sqlite3.Connection = open_sqlite(sqlite_path)
    init_db(conn)
    root = project_root()
    preset_dir = root / "config" / "presets"
    preset_ids: list[str] = []
    if preset_dir.is_dir():
        for p in sorted(preset_dir.glob("*.yaml")):
            with open(p, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            pid = doc.get("preset_id", p.stem)
            w = doc.get("weights", {})
            seed_preset_from_weights(
                conn,
                str(pid),
                float(w["recency"]),
                float(w["importance"]),
                float(w["relevance"]),
            )
            preset_ids.append(str(pid))
    if not preset_ids:
        seed_preset_from_weights(conn, "equal", 1 / 3, 1 / 3, 1 / 3)
        preset_ids.append("equal")
    scope = "global"
    if config:
        scope = str(config.get("optimizer", {}).get("default_scope", scope))
    init_bandit_arms(conn, scope, preset_ids)
    return conn
