"""retrieve → decision_id → schedule_reward → bandit posterior update."""

import tempfile
import time
from pathlib import Path

import numpy as np

from ghost_core.bootstrap import ensure_ghost_db
from ghost_optimizer.optimizer import GhostOptimizer
from ghost_retrieval.hybrid import HybridSearchEngine
from ghost_retrieval.pipeline import DefaultRetrievePipeline
from ghost_core.types import RetrieveRequest, RetrievalWeights, WorkerContext


class FakeEmbedder:
    dimensions = 1024

    def embed(self, text: str) -> np.ndarray:
        return np.ones(self.dimensions, dtype=np.float32) * 0.1


def test_reward_updates_posterior() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        hybrid = HybridSearchEngine(conn, dimensions=1024, corpus_mode="skills")
        pipe = DefaultRetrievePipeline(conn, FakeEmbedder(), hybrid)
        rng = np.random.default_rng(0)
        opt = GhostOptimizer(conn, "global", rng, audit=None, max_queue=100)
        resp = pipe.retrieve(
            RetrieveRequest(
                query="q",
                limit=5,
                weights=RetrievalWeights(1 / 3, 1 / 3, 1 / 3),
                preset_id="equal",
                worker_context=WorkerContext(),
            )
        )
        opt.register_decision(resp.decision_id, {"scope": "global", "preset_id": "equal"})
        before = conn.execute(
            "SELECT alpha FROM bandit_state WHERE scope = ? AND preset_id = ?",
            ("global", "equal"),
        ).fetchone()["alpha"]
        opt.schedule_reward(resp.decision_id, 0.9)
        time.sleep(0.25)
        after = conn.execute(
            "SELECT alpha FROM bandit_state WHERE scope = ? AND preset_id = ?",
            ("global", "equal"),
        ).fetchone()["alpha"]
        assert after > before
        opt.close()
        conn.close()
