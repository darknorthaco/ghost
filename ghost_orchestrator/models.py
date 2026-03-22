"""Orchestration value types — explicit, JSON-serializable."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class WorkerStatus(str, Enum):
    ACTIVE = "active"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class WorkerRecord:
    worker_id: str
    host: str
    port: int
    status: WorkerStatus
    capabilities: frozenset[str]
    max_concurrent_tasks: int = 1
    current_tasks: int = 0
    performance_score: float = 1.0
    gpu_name: str = ""
    memory_free_mb: int = 0
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    task_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 0
    memory_required_mb: int | None = None
