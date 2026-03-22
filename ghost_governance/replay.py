"""Replay structured audit JSONL for tests and offline analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ghost_optimizer.optimizer import GhostOptimizer


def load_optimizer_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load records from a JSONL file (one JSON object per line)."""
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def replay_optimizer_rewards(
    optimizer: GhostOptimizer,
    records: list[dict[str, Any]],
    *,
    event_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> int:
    """Re-apply `schedule_reward` calls from recorded optimizer traces."""
    n = 0
    for rec in records:
        if event_filter and not event_filter(rec):
            continue
        if rec.get("event") == "reward_applied":
            did = rec.get("decision_id")
            reward = rec.get("reward")
            if did is None or reward is None:
                continue
            optimizer.register_decision(
                str(did),
                {"scope": rec.get("scope", "global"), "preset_id": rec.get("preset_id", "equal")},
            )
            optimizer.schedule_reward(str(did), float(reward))
            n += 1
    return n


def replay_optimizer_rewards_from_file(optimizer: GhostOptimizer, path: str | Path) -> int:
    """Load JSONL from disk and replay reward events."""
    records = load_optimizer_jsonl(path)
    return replay_optimizer_rewards(optimizer, records)
