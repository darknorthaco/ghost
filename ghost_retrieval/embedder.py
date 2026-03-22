"""Dense embeddings — optional sentence-transformers (offline-capable)."""

import sqlite3
from typing import Any, Optional

import numpy as np


class Embedder:
    """Lazy-loads a local embedding model; no network calls after install."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-Embedding-0.6B",
        dimensions: int = 1024,
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.dimensions = dimensions
        self.device = device
        self._model: Any = None

    def _load_model(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self.model_name,
            device=self.device,
            truncate_dim=self.dimensions,
        )

    def embed(self, text: str) -> np.ndarray:
        self._load_model()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.astype(np.float32)

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Local batch embedding for ingestion jobs."""
        self._load_model()
        vecs = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 32,
        )
        return vecs.astype(np.float32)


def vector_to_blob(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def blob_to_vector(blob: bytes, dimensions: int = 1024) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32).copy()


def cosine_similarity_batch(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return matrix @ query


def load_all_skill_embeddings(
    conn: sqlite3.Connection,
    dimensions: int = 1024,
) -> tuple[list[str], np.ndarray]:
    rows = conn.execute(
        "SELECT skill_id, embedding FROM skill_embeddings ORDER BY skill_id"
    ).fetchall()
    if not rows:
        return [], np.empty((0, dimensions), dtype=np.float32)
    skill_ids = [row["skill_id"] for row in rows]
    vectors = np.array(
        [blob_to_vector(row["embedding"], dimensions) for row in rows],
        dtype=np.float32,
    )
    return skill_ids, vectors


def load_all_chunk_embeddings(
    conn: sqlite3.Connection,
    dimensions: int = 1024,
) -> tuple[list[str], np.ndarray]:
    rows = conn.execute(
        "SELECT chunk_id, embedding FROM chunk_embeddings ORDER BY chunk_id"
    ).fetchall()
    if not rows:
        return [], np.empty((0, dimensions), dtype=np.float32)
    chunk_ids = [row["chunk_id"] for row in rows]
    vectors = np.array(
        [blob_to_vector(row["embedding"], dimensions) for row in rows],
        dtype=np.float32,
    )
    return chunk_ids, vectors


def store_skill_embedding(
    conn: sqlite3.Connection,
    skill_id: str,
    embedding: np.ndarray,
    model: str = "local",
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO skill_embeddings (skill_id, embedding, model)
           VALUES (?, ?, ?)""",
        (skill_id, vector_to_blob(embedding), model),
    )
    conn.commit()


def store_chunk_embedding(
    conn: sqlite3.Connection,
    chunk_id: str,
    embedding: np.ndarray,
    model: str = "local",
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO chunk_embeddings (chunk_id, embedding, model)
           VALUES (?, ?, ?)""",
        (chunk_id, vector_to_blob(embedding), model),
    )
    conn.commit()
