"""Deterministic routing: same inputs → same worker."""

from ghost_orchestrator.models import TaskSpec, WorkerRecord, WorkerStatus
from ghost_orchestrator.registry import InMemoryWorkerRegistry
from ghost_orchestrator.router import deterministic_route


def test_deterministic_route_tie_break() -> None:
    reg = InMemoryWorkerRegistry()
    reg.upsert(
        WorkerRecord(
            worker_id="b",
            host="127.0.0.1",
            port=1,
            status=WorkerStatus.ACTIVE,
            capabilities=frozenset(),
            performance_score=1.0,
            gpu_name="GTX 1080",
            memory_free_mb=16000,
        )
    )
    reg.upsert(
        WorkerRecord(
            worker_id="a",
            host="127.0.0.1",
            port=2,
            status=WorkerStatus.ACTIVE,
            capabilities=frozenset(),
            performance_score=1.0,
            gpu_name="GTX 1080",
            memory_free_mb=16000,
        )
    )
    snap = reg.snapshot()
    task = TaskSpec(task_id="t1", task_type="ml_inference")
    w1 = deterministic_route(task, snap)
    w2 = deterministic_route(task, snap)
    assert w1 == w2 == "a"
