"""Append-only JSONL audit logs (local, inspectable)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping


class JsonlAuditSink:
    """Implements `AuditSink` with one file per trace kind."""

    def __init__(self, log_dir: str | Path):
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _append(self, filename: str, record: Mapping[str, Any]) -> None:
        path = self._dir / filename
        line = {
            "ts": time.time(),
            **dict(record),
        }
        payload = json.dumps(line, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(payload)

    def append_retrieval_trace(self, record: Mapping[str, Any]) -> None:
        self._append("retrieval.jsonl", record)

    def append_optimizer_trace(self, record: Mapping[str, Any]) -> None:
        self._append("optimizer.jsonl", record)

    def append_routing_trace(self, record: Mapping[str, Any]) -> None:
        self._append("routing.jsonl", record)
