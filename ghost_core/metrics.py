"""Lightweight in-process metrics (no network; optional export via /metrics later)."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class GhostMetrics:
    """Thread-safe counters and latency samples for observability."""

    def __init__(self, latency_window: int = 256) -> None:
        self._lock = threading.Lock()
        self.retrieve_total = 0
        self.retrieve_errors = 0
        self.feedback_total = 0
        self.ingest_files_total = 0
        self._retrieve_latencies_ms: deque[float] = deque(maxlen=latency_window)

    def record_retrieve(self, duration_sec: float, error: bool = False) -> None:
        with self._lock:
            self.retrieve_total += 1
            if error:
                self.retrieve_errors += 1
            self._retrieve_latencies_ms.append(duration_sec * 1000.0)

    def record_feedback(self) -> None:
        with self._lock:
            self.feedback_total += 1

    def record_ingest_file(self) -> None:
        with self._lock:
            self.ingest_files_total += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            lat = list(self._retrieve_latencies_ms)
            p95 = _percentile(lat, 95) if lat else 0.0
            return {
                "retrieve_total": self.retrieve_total,
                "retrieve_errors": self.retrieve_errors,
                "feedback_total": self.feedback_total,
                "ingest_files_total": self.ingest_files_total,
                "retrieve_latency_ms_p95": round(p95, 3),
                "retrieve_latency_ms_last": round(lat[-1], 3) if lat else 0.0,
                "ts": time.time(),
            }


def _percentile(sorted_or_values: list[float], pct: float) -> float:
    if not sorted_or_values:
        return 0.0
    xs = sorted(sorted_or_values)
    k = (len(xs) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c] - xs[f]) * (k - f)
