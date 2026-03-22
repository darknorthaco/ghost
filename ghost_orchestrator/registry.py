"""In-memory worker registry implementing `WorkerRegistryPort` (snapshot for routing)."""

from __future__ import annotations

import threading
import time
from typing import Any, Mapping

from ghost_core.contracts import WorkerRegistryPort
from ghost_orchestrator.models import WorkerRecord, WorkerStatus


class InMemoryWorkerRegistry(WorkerRegistryPort):
    """Thread-safe CRUD + heartbeat; `snapshot()` returns a deterministic sortable structure."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerRecord] = {}
        self._lock = threading.Lock()
        self._heartbeats: dict[str, float] = {}

    def upsert(self, record: WorkerRecord) -> None:
        with self._lock:
            self._workers[record.worker_id] = record
            self._heartbeats[record.worker_id] = time.time()

    def remove(self, worker_id: str) -> None:
        with self._lock:
            self._workers.pop(worker_id, None)
            self._heartbeats.pop(worker_id, None)

    def heartbeat(self, worker_id: str, payload: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            if worker_id not in self._workers:
                return
            self._heartbeats[worker_id] = time.time()
            if payload:
                w = self._workers[worker_id]
                self._workers[worker_id] = WorkerRecord(
                    worker_id=w.worker_id,
                    host=str(payload.get("host", w.host)),
                    port=int(payload.get("port", w.port)),
                    status=WorkerStatus(str(payload.get("status", w.status.value))),
                    capabilities=frozenset(payload.get("capabilities", w.capabilities)),
                    max_concurrent_tasks=int(payload.get("max_concurrent_tasks", w.max_concurrent_tasks)),
                    current_tasks=int(payload.get("current_tasks", w.current_tasks)),
                    performance_score=float(payload.get("performance_score", w.performance_score)),
                    gpu_name=str(payload.get("gpu_name", w.gpu_name)),
                    memory_free_mb=int(payload.get("memory_free_mb", w.memory_free_mb)),
                    extras=dict(w.extras),
                )

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            workers = sorted(self._workers.values(), key=lambda w: w.worker_id)
            return {
                "workers": [
                    {
                        "worker_id": w.worker_id,
                        "host": w.host,
                        "port": w.port,
                        "status": w.status.value,
                        "capabilities": sorted(w.capabilities),
                        "max_concurrent_tasks": w.max_concurrent_tasks,
                        "current_tasks": w.current_tasks,
                        "performance_score": w.performance_score,
                        "gpu_name": w.gpu_name,
                        "memory_free_mb": w.memory_free_mb,
                    }
                    for w in workers
                ],
                "heartbeats": dict(sorted(self._heartbeats.items())),
            }
