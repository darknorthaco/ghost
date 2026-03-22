"""BM25 (FTS5) + dense cosine + RRF fusion, then weighted dimension scoring."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from ghost_retrieval.embedder import (
    cosine_similarity_batch,
    load_all_chunk_embeddings,
    load_all_skill_embeddings,
)


@dataclass
class SearchResult:
    skill_id: str
    title: str = ""
    bm25_score: float = 0.0
    dense_score: float = 0.0
    rrf_score: float = 0.0
    final_score: float = 0.0
    recency_score: float = 0.0
    importance_score: float = 0.0
    relevance_score: float = 0.0


@dataclass
class HybridSearchEngine:
    conn: sqlite3.Connection
    rrf_k: int = 60
    bm25_weight: float = 0.4
    dense_weight: float = 0.6
    dimensions: int = 1024
    corpus_mode: Literal["auto", "skills", "chunks"] = "auto"
    _ids: list[str] = field(default_factory=list, init=False, repr=False)
    _embedding_matrix: np.ndarray = field(
        default_factory=lambda: np.empty(0), init=False, repr=False
    )
    _cache_loaded: bool = field(default=False, init=False, repr=False)
    _resolved_mode: str | None = field(default=None, init=False, repr=False)

    def _resolve_corpus_mode(self) -> str:
        if self.corpus_mode in ("skills", "chunks"):
            return self.corpus_mode
        ns = self.conn.execute("SELECT COUNT(*) AS c FROM skill_embeddings").fetchone()["c"]
        nc = self.conn.execute("SELECT COUNT(*) AS c FROM chunk_embeddings").fetchone()["c"]
        if nc > 0 and ns == 0:
            return "chunks"
        return "skills"

    def _ensure_cache(self) -> None:
        if self._cache_loaded:
            return
        if self._resolved_mode is None:
            self._resolved_mode = self._resolve_corpus_mode()
        mode = self._resolved_mode
        if mode == "chunks":
            self._ids, self._embedding_matrix = load_all_chunk_embeddings(
                self.conn, self.dimensions
            )
        else:
            self._ids, self._embedding_matrix = load_all_skill_embeddings(
                self.conn, self.dimensions
            )
        self._cache_loaded = True

    def invalidate_cache(self) -> None:
        self._cache_loaded = False
        self._resolved_mode = None

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str | None:
        cleaned = re.sub(r"[^\w\s]", " ", query)
        words = [f'"{w}"' for w in cleaned.split() if len(w) > 1]
        return " OR ".join(words) if words else None

    def search_bm25(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        sanitized = self._sanitize_fts5_query(query)
        if sanitized is None:
            return []
        if self._resolved_mode is None:
            self._resolved_mode = self._resolve_corpus_mode()
        mode = self._resolved_mode
        if mode == "chunks":
            rows = self.conn.execute(
                """SELECT chunk_id AS sid, rank
                   FROM chunks_fts
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (sanitized, top_k),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT skill_id AS sid, rank
                   FROM skills_fts
                   WHERE skills_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (sanitized, top_k),
            ).fetchall()
        return [(row["sid"], -row["rank"]) for row in rows]

    def search_dense(self, query_embedding: np.ndarray, top_k: int = 20) -> list[tuple[str, float]]:
        self._ensure_cache()
        if len(self._ids) == 0:
            return []
        similarities = cosine_similarity_batch(query_embedding, self._embedding_matrix)
        if len(similarities) <= top_k:
            top_indices = np.argsort(similarities)[::-1]
        else:
            top_indices = np.argpartition(similarities, -top_k)[-top_k:]
            top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        return [(self._ids[i], float(similarities[i])) for i in top_indices]

    def fuse_rrf(
        self,
        bm25_results: list[tuple[str, float]],
        dense_results: list[tuple[str, float]],
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        for rank, (skill_id, _) in enumerate(bm25_results):
            rrf = self.bm25_weight / (self.rrf_k + rank + 1)
            scores[skill_id] = scores.get(skill_id, 0.0) + rrf
        for rank, (skill_id, _) in enumerate(dense_results):
            rrf = self.dense_weight / (self.rrf_k + rank + 1)
            scores[skill_id] = scores.get(skill_id, 0.0) + rrf
        return scores

    def search(
        self,
        query: str,
        query_embedding: np.ndarray,
        top_k: int = 10,
        retrieval_weights: tuple[float, float, float] | None = None,
    ) -> list[SearchResult]:
        if self._resolved_mode is None:
            self._resolved_mode = self._resolve_corpus_mode()
        fetch_k = max(top_k * 3, 20)
        bm25_results = self.search_bm25(query, top_k=fetch_k)
        dense_results = self.search_dense(query_embedding, top_k=fetch_k)
        rrf_scores = self.fuse_rrf(bm25_results, dense_results)
        bm25_lookup = dict(bm25_results)
        dense_lookup = dict(dense_results)
        results: list[SearchResult] = []
        for skill_id, rrf_score in rrf_scores.items():
            result = SearchResult(
                skill_id=skill_id,
                bm25_score=bm25_lookup.get(skill_id, 0.0),
                dense_score=dense_lookup.get(skill_id, 0.0),
                rrf_score=rrf_score,
            )
            if self._resolved_mode is None:
                self._resolved_mode = self._resolve_corpus_mode()
            mode = self._resolved_mode
            if mode == "chunks":
                row = self.conn.execute(
                    "SELECT title FROM chunks WHERE chunk_id = ?", (skill_id,)
                ).fetchone()
            else:
                row = self.conn.execute(
                    "SELECT title FROM skills WHERE skill_id = ?", (skill_id,)
                ).fetchone()
            if row:
                result.title = row["title"]
            results.append(result)
        if retrieval_weights is not None:
            w_rec, w_imp, w_rel = retrieval_weights
            max_rrf = max((r.rrf_score for r in results), default=1.0) or 1.0
            for r in results:
                r.relevance_score = r.rrf_score / max_rrf
                if r.recency_score == 0.0 and r.importance_score == 0.0:
                    r.recency_score = 0.5
                    r.importance_score = 0.5
                r.final_score = (
                    w_rec * r.recency_score + w_imp * r.importance_score + w_rel * r.relevance_score
                )
        else:
            for r in results:
                r.final_score = r.rrf_score
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results[:top_k]
