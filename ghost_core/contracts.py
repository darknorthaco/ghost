"""Minimal composable interfaces (Protocols) — no hidden coupling."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from ghost_core.types import RetrieveRequest, RetrieveResponse


@runtime_checkable
class RetrievePipeline(Protocol):
    """Deterministic ranking given fixed DB snapshot, weights, and embedder inputs."""

    def retrieve(self, req: RetrieveRequest) -> RetrieveResponse:
        ...


@runtime_checkable
class OptimizerPort(Protocol):
    """Bandit + governance hooks; randomness is injected and logged by implementation."""

    def select_preset(self, scope: str) -> str:
        """Return a weight preset id for the given scope (e.g. tenant, corpus)."""
        ...

    def schedule_reward(self, decision_id: str, reward: float) -> None:
        """Enqueue a bounded reward in [0, 1] tied to a retrieval decision."""
        ...


@runtime_checkable
class WorkerRegistryPort(Protocol):
    """CRUD + heartbeat; routing uses an explicit snapshot for determinism."""

    def heartbeat(self, worker_id: str, payload: Mapping[str, Any] | None = None) -> None: ...

    def snapshot(self) -> Mapping[str, Any]:
        """Immutable serializable view for deterministic routing."""
        ...


@runtime_checkable
class AuditSink(Protocol):
    """Structured append-only traces (local files or DB), queryable downstream."""

    def append_retrieval_trace(self, record: Mapping[str, Any]) -> None: ...

    def append_optimizer_trace(self, record: Mapping[str, Any]) -> None: ...

    def append_routing_trace(self, record: Mapping[str, Any]) -> None: ...
