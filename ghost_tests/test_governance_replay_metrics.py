"""Governance store, replay from file, metrics, lifecycle."""

import tempfile
import time
from pathlib import Path

import numpy as np

from ghost_core.bootstrap import ensure_ghost_db
from ghost_core.metrics import GhostMetrics
from ghost_governance.policy import policy_change_approved
from ghost_governance.replay import replay_optimizer_rewards_from_file
from ghost_governance.store import register_approval_token
from ghost_optimizer.optimizer import GhostOptimizer
from ghost_retrieval.ingestion import ingest_file
from ghost_retrieval.lifecycle import delete_document


class FakeEmbedder:
    dimensions = 8
    model_name = "fake"

    def embed(self, text: str) -> np.ndarray:
        return np.ones(self.dimensions, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), self.dimensions), dtype=np.float32)


def test_policy_allows_persisted_token() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        register_approval_token(conn, "my-secret", label="test")
        cfg = {"governance": {"require_human_approval_for_policy_change": True}}
        assert policy_change_approved({}, cfg, conn=conn) is False
        assert (
            policy_change_approved({"X-Ghost-Policy-Approve": "my-secret"}, cfg, conn=conn)
            is True
        )
        conn.close()


def test_replay_optimizer_from_jsonl_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        db = td_path / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        rng = np.random.default_rng(2)
        opt = GhostOptimizer(conn, "global", rng, audit=None, max_queue=50)
        p = td_path / "r.jsonl"
        p.write_text(
            '{"event":"reward_applied","decision_id":"x1","reward":0.6,"scope":"global","preset_id":"equal"}\n',
            encoding="utf-8",
        )
        before = conn.execute(
            "SELECT alpha FROM bandit_state WHERE scope = ? AND preset_id = ?",
            ("global", "equal"),
        ).fetchone()["alpha"]
        replay_optimizer_rewards_from_file(opt, p)
        time.sleep(0.2)
        after = conn.execute(
            "SELECT alpha FROM bandit_state WHERE scope = ? AND preset_id = ?",
            ("global", "equal"),
        ).fetchone()["alpha"]
        assert after > before
        opt.close()
        conn.close()


def test_metrics_snapshot() -> None:
    m = GhostMetrics()
    m.record_retrieve(0.01, error=False)
    m.record_retrieve(0.02, error=False)
    s = m.snapshot()
    assert s["retrieve_total"] == 2


def test_delete_document_removes_chunks() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        db = td_path / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        f = td_path / "a.txt"
        f.write_text("hello", encoding="utf-8")
        res = ingest_file(conn, FakeEmbedder(), f, chunk_size=100, chunk_overlap=10)
        n0 = conn.execute("SELECT COUNT(*) AS c FROM chunk_embeddings").fetchone()["c"]
        assert n0 >= 1
        delete_document(conn, res.document_id)
        n1 = conn.execute("SELECT COUNT(*) AS c FROM chunk_embeddings").fetchone()["c"]
        assert n1 == 0
        conn.close()


def test_schema_version_at_least_3() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "g.db"
        conn = ensure_ghost_db(db, {})
        v = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"]
        assert int(v) >= 3
        conn.close()
