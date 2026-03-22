"""Default retrieval pipeline implementing `ghost_core.contracts.RetrievePipeline`."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Callable, Mapping

import numpy as np

from ghost_core.contracts import AuditSink
from ghost_core.types import (
    RetrievalWeights,
    RetrieveRequest,
    RetrieveResponse,
    ScoreBreakdown,
)
from ghost_retrieval.embedder import Embedder
from ghost_retrieval.hybrid import HybridSearchEngine


PresetResolver = Callable[[str], RetrievalWeights]


class DefaultRetrievePipeline:
    """Hybrid BM25+dense retrieval with structured explanations and audit records."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        embedder: Embedder,
        hybrid: HybridSearchEngine,
        audit: AuditSink | None = None,
        preset_resolver: PresetResolver | None = None,
    ):
        self._conn = conn
        self._embedder = embedder
        self._hybrid = hybrid
        self._audit = audit
        self._preset_resolver = preset_resolver

    @property
    def audit(self) -> AuditSink | None:
        return self._audit

    def _weights_for_request(self, req: RetrieveRequest) -> tuple[RetrievalWeights | None, str | None]:
        if req.weights is not None:
            return req.weights, req.preset_id
        if req.preset_id:
            if self._preset_resolver:
                return self._preset_resolver(req.preset_id), req.preset_id
            row = self._conn.execute(
                "SELECT w_recency, w_importance, w_relevance FROM weight_presets WHERE preset_id = ?",
                (req.preset_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown preset_id: {req.preset_id}")
            w = RetrievalWeights(
                recency=float(row["w_recency"]),
                importance=float(row["w_importance"]),
                relevance=float(row["w_relevance"]),
            )
            return w, req.preset_id
        return None, None

    def retrieve(self, req: RetrieveRequest) -> RetrieveResponse:
        decision_id = str(uuid.uuid4())
        qvec = self._embedder.embed(req.query)
        weights, preset_id = self._weights_for_request(req)
        rw: tuple[float, float, float] | None = None
        if weights is not None:
            rw = (weights.recency, weights.importance, weights.relevance)
        raw = self._hybrid.search(
            req.query,
            qvec,
            top_k=req.limit,
            retrieval_weights=rw,
        )
        chunks = tuple(
            ScoreBreakdown(
                chunk_id=r.skill_id,
                title=r.title,
                bm25_score=r.bm25_score,
                dense_score=r.dense_score,
                rrf_score=r.rrf_score,
                recency_score=r.recency_score,
                importance_score=r.importance_score,
                relevance_score=r.relevance_score,
                final_score=r.final_score,
            )
            for r in raw
        )
        explain: dict[str, Any] = {
            "rrf_k": self._hybrid.rrf_k,
            "bm25_weight": self._hybrid.bm25_weight,
            "dense_weight": self._hybrid.dense_weight,
            "query_embedding_norm": float(np.linalg.norm(qvec)),
        }
        resp = RetrieveResponse(
            decision_id=decision_id,
            chunks=chunks,
            preset_id=preset_id,
            weights_used=weights,
            explain=explain,
        )
        if self._audit is not None:
            self._audit.append_retrieval_trace(
                {
                    "decision_id": decision_id,
                    "query": req.query,
                    "limit": req.limit,
                    "preset_id": preset_id,
                    "weights": (
                        {
                            "recency": weights.recency,
                            "importance": weights.importance,
                            "relevance": weights.relevance,
                        }
                        if weights
                        else None
                    ),
                    "chunks": [c.__dict__ for c in chunks],
                    "explain": explain,
                    "worker_context": {
                        "worker_id": req.worker_context.worker_id,
                        "capabilities": sorted(req.worker_context.capabilities),
                    },
                }
            )
        return resp


def load_preset_yaml_weights(path: str) -> RetrievalWeights:
    import yaml
    from pathlib import Path

    with open(Path(path), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    w = data["weights"]
    return RetrievalWeights(
        recency=float(w["recency"]),
        importance=float(w["importance"]),
        relevance=float(w["relevance"]),
    )
