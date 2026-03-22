"""Deterministic worker selection — same snapshot + task → same worker_id."""

from __future__ import annotations

from typing import Any, Mapping

from ghost_orchestrator.models import TaskSpec, WorkerStatus


def _score_worker(task: TaskSpec, w: Mapping[str, Any], gpu_profiles: Mapping[str, Mapping[str, float]]) -> float:
    """Replica of Phantom-style scoring, purely functional for testing and audit."""
    if w.get("status") != WorkerStatus.ACTIVE.value:
        return -1.0
    cur = int(w.get("current_tasks", 0))
    cap = max(int(w.get("max_concurrent_tasks", 1)), 1)
    if cur >= cap:
        return -1.0
    gpu_name = str(w.get("gpu_name", ""))
    base = 1.0
    for profile_name, profile in gpu_profiles.items():
        if profile_name in gpu_name:
            base = float(profile.get(task.task_type, profile.get("ml_inference", 1.0)))
            break
    load_factor = 1.0 - (cur / cap)
    perf = float(w.get("performance_score", 1.0))
    mem_free = int(w.get("memory_free_mb", 0))
    mem_factor = 1.0
    req = task.memory_required_mb
    if req is not None and req > 0:
        mem_factor = 0.1 if mem_free < req else min(1.0, mem_free / req)
    return base * load_factor * perf * mem_factor


def deterministic_route(
    task: TaskSpec,
    registry_snapshot: Mapping[str, Any],
    gpu_profiles: Mapping[str, Mapping[str, float]] | None = None,
) -> str | None:
    """Pick highest score; ties broken by lexicographic `worker_id`."""
    profiles: Mapping[str, Mapping[str, float]] = gpu_profiles or {
        "RTX 5080": {"ml_inference": 10.0, "training": 9.5, "default": 8.0},
        "GTX 1080": {"ml_inference": 5.0, "training": 4.5, "default": 5.0},
    }
    workers: list[Mapping[str, Any]] = list(registry_snapshot.get("workers", []))
    scored: list[tuple[str, float]] = []
    for w in workers:
        wid = str(w["worker_id"])
        s = _score_worker(task, w, profiles)
        scored.append((wid, s))
    scored.sort(key=lambda x: (-x[1], x[0]))
    for wid, s in scored:
        if s >= 0:
            return wid
    return None
