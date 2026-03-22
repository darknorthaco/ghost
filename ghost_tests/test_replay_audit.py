"""Replay optimizer JSONL records."""

import tempfile
import time
from pathlib import Path

import numpy as np

from ghost_core.bootstrap import ensure_ghost_db
from ghost_governance.replay import replay_optimizer_rewards
from ghost_optimizer.optimizer import GhostOptimizer


def test_replay_reward_from_records() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        rng = np.random.default_rng(1)
        opt = GhostOptimizer(conn, "global", rng, audit=None, max_queue=50)
        records = [
            {
                "event": "reward_applied",
                "decision_id": "dec-replay-1",
                "reward": 0.75,
                "scope": "global",
                "preset_id": "equal",
            }
        ]
        before = conn.execute(
            "SELECT alpha FROM bandit_state WHERE scope = ? AND preset_id = ?",
            ("global", "equal"),
        ).fetchone()["alpha"]
        replay_optimizer_rewards(opt, records)
        time.sleep(0.2)
        after = conn.execute(
            "SELECT alpha FROM bandit_state WHERE scope = ? AND preset_id = ?",
            ("global", "equal"),
        ).fetchone()["alpha"]
        assert after > before
        opt.close()
        conn.close()

