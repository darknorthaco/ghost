"""Shared value types for GHOST subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RetrievalWeights:
    """Non-negative weights that sum to 1.0 over retrieval dimensions."""

    recency: float
    importance: float
    relevance: float

    def __post_init__(self) -> None:
        s = self.recency + self.importance + self.relevance
        if abs(s - 1.0) > 0.02:
            raise ValueError(f"weights must sum to ~1.0, got {s}")


@dataclass(frozen=True, slots=True)
class WorkerContext:
    """Opaque worker-side context propagated for routing and audit (no globals)."""

    worker_id: str | None = None
    capabilities: frozenset[str] = frozenset()
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Per-chunk explainable scores (all stages visible to audit)."""

    chunk_id: str
    bm25_score: float = 0.0
    dense_score: float = 0.0
    rrf_score: float = 0.0
    recency_score: float = 0.0
    importance_score: float = 0.0
    relevance_score: float = 0.0
    final_score: float = 0.0
    title: str = ""


@dataclass(frozen=True, slots=True)
class RetrieveRequest:
    query: str
    limit: int
    weights: RetrievalWeights | None = None
    preset_id: str | None = None
    worker_context: WorkerContext = field(default_factory=WorkerContext)


@dataclass(frozen=True, slots=True)
class RetrieveResponse:
    decision_id: str
    chunks: tuple[ScoreBreakdown, ...]
    preset_id: str | None
    weights_used: RetrievalWeights | None
    explain: Mapping[str, Any]
