"""Load merged YAML configuration (defaults + optional overrides)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def load_ghost_config(
    path: str | Path | None = None,
    extra_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Load config/default.yaml and merge optional additional YAML files in order."""
    root = Path(__file__).resolve().parents[1]
    default = root / "config" / "default.yaml"
    config_path = Path(path) if path else default
    if not config_path.exists():
        raise FileNotFoundError(f"GHOST config not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f) or {}
    for p in extra_paths or []:
        pp = Path(p)
        if not pp.exists():
            continue
        with open(pp, encoding="utf-8") as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})
    return cfg


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]
