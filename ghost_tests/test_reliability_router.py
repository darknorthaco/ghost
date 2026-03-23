"""Routing with local reliability weights (DKA Phase 3)."""

import json
import tempfile
from pathlib import Path

from ghost_orchestrator.models import TaskSpec, WorkerRecord, WorkerStatus
from ghost_orchestrator.registry import InMemoryWorkerRegistry
from ghost_orchestrator.router import deterministic_route
from ghost_orchestrator.router_reliability import deterministic_route_with_retrieval_audit


def test_deterministic_route_unchanged_without_weights() -> None:
    reg = InMemoryWorkerRegistry()
    for wid in ("b", "a"):
        reg.upsert(
            WorkerRecord(
                worker_id=wid,
                host="127.0.0.1",
                port=1 if wid == "b" else 2,
                status=WorkerStatus.ACTIVE,
                capabilities=frozenset(),
                performance_score=1.0,
                gpu_name="GTX 1080",
                memory_free_mb=16000,
            )
        )
    snap = reg.snapshot()
    task = TaskSpec(task_id="t1", task_type="ml_inference")
    w = deterministic_route(task, snap)
    assert w == "a"


def test_reliability_weights_prefer_successful_worker(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as td:
        gh = Path(td) / ".ghost"
        (gh / "retrieval").mkdir(parents=True)
        monkeypatch.setenv("GHOST_HOME", str(gh))

        sig = gh / "retrieval" / "worker_signals.jsonl"
        lines = [json.dumps({"worker_id": "a", "ok": True})] * 4 + [
            json.dumps({"worker_id": "b", "ok": False})
        ] * 4
        sig.write_text("\n".join(lines) + "\n", encoding="utf-8")

        reg = InMemoryWorkerRegistry()
        for wid in ("a", "b"):
            reg.upsert(
                WorkerRecord(
                    worker_id=wid,
                    host="127.0.0.1",
                    port=8080 if wid == "a" else 8081,
                    status=WorkerStatus.ACTIVE,
                    capabilities=frozenset(),
                    performance_score=1.0,
                    gpu_name="GTX 1080",
                    memory_free_mb=16000,
                )
            )
        snap = reg.snapshot()
        task = TaskSpec(task_id="t2", task_type="ml_inference")
        chosen, detail = deterministic_route_with_retrieval_audit(
            task, snap, log_routing=False
        )
        assert chosen == "a"
        assert detail["chosen_worker_id"] == "a"
        wa = detail["reliability_weights"]["a"]
        wb = detail["reliability_weights"]["b"]
        assert wa > wb
