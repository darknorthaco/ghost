"""Retrieval pipeline with a fake embedder (no model download)."""

import tempfile
from pathlib import Path

import numpy as np

from ghost_core.bootstrap import ensure_ghost_db
from ghost_core.types import RetrieveRequest, RetrievalWeights, WorkerContext
from ghost_retrieval.hybrid import HybridSearchEngine
from ghost_retrieval.pipeline import DefaultRetrievePipeline


class FakeEmbedder:
    dimensions = 1024

    def embed(self, text: str) -> np.ndarray:
        return np.ones(self.dimensions, dtype=np.float32) * 0.1


def test_retrieve_empty_corpus() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        hybrid = HybridSearchEngine(conn, dimensions=1024)
        pipe = DefaultRetrievePipeline(conn, FakeEmbedder(), hybrid)
        resp = pipe.retrieve(
            RetrieveRequest(
                query="hello world",
                limit=5,
                weights=RetrievalWeights(1 / 3, 1 / 3, 1 / 3),
                worker_context=WorkerContext(),
            )
        )
        assert resp.chunks == ()
        assert resp.decision_id
        conn.close()
