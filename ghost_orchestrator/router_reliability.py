"""Deterministic routing with local reliability retrieval + JSONL audit (DKA Phase 3)."""

from __future__ import annotations

from typing import Any, Mapping

from ghost_orchestrator.models import TaskSpec
from ghost_orchestrator.reliability_store import (
    append_routing_decision,
    laplace_reliability_weights,
)
from ghost_orchestrator.router import deterministic_route


def deterministic_route_with_retrieval_audit(
    task: TaskSpec,
    registry_snapshot: Mapping[str, Any],
    gpu_profiles: Mapping[str, Mapping[str, float]] | None = None,
    *,
    log_routing: bool = True,
) -> tuple[str | None, dict[str, Any]]:
    """Same contract as ``deterministic_route``, but weights workers by ``worker_signals.jsonl``.

    Appends one JSON line to ``~/.ghost/retrieval/worker_routing_fdx.jsonl`` when ``log_routing``.
    """
    weights = laplace_reliability_weights()
    chosen = deterministic_route(
        task,
        registry_snapshot,
        gpu_profiles,
        reliability_weights=weights,
    )
    rationale = (
        f"deterministic_route with Laplace reliability weights "
        f"({len(weights)} worker(s) in store)"
    )
    detail: dict[str, Any] = {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "chosen_worker_id": chosen,
        "rationale": rationale,
        "reliability_weights": weights,
    }
    if log_routing:
        append_routing_decision(detail)
    return chosen, detail
