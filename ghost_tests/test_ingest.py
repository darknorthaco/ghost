"""Ingestion writes chunks and embeddings (fake embedder)."""

import tempfile
from pathlib import Path

import numpy as np

from ghost_core.bootstrap import ensure_ghost_db
from ghost_retrieval.ingestion import ingest_file


class FakeEmbedder:
    dimensions = 8
    model_name = "fake"

    def embed(self, text: str) -> np.ndarray:
        return np.ones(self.dimensions, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), self.dimensions), dtype=np.float32)


def test_ingest_file_creates_chunks() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        db = td_path / "g.db"
        conn = ensure_ghost_db(db, {"optimizer": {"default_scope": "global"}})
        f = td_path / "a.txt"
        f.write_text("hello world " * 50, encoding="utf-8")
        res = ingest_file(conn, FakeEmbedder(), f, chunk_size=100, chunk_overlap=10)
        assert res.chunks_written >= 1
        assert len(res.content_sha256) == 64
        n = conn.execute("SELECT COUNT(*) AS c FROM chunk_embeddings").fetchone()["c"]
        assert n == res.chunks_written
        conn.close()
