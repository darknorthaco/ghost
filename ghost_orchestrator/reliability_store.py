"""Local worker reliability signals for retrieval-style routing (DKA Phase 3).

Sovereign: JSONL under ``~/.ghost/retrieval/`` (or ``GHOST_HOME``). No network.
Deterministic: same store contents → same Laplace-smoothed weights.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _ghost_home() -> Path:
    env = os.environ.get("GHOST_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".ghost"


def _retrieval_dir() -> Path:
    d = _ghost_home() / "retrieval"
    d.mkdir(parents=True, exist_ok=True)
    return d


def worker_signals_path() -> Path:
    return _retrieval_dir() / "worker_signals.jsonl"


def worker_routing_fdx_path() -> Path:
    return _retrieval_dir() / "worker_routing_fdx.jsonl"


@dataclass(frozen=True)
class WorkerSignal:
    """One observation of worker behavior (task outcome or health)."""

    worker_id: str
    ok: bool
    latency_ms: int | None = None
    source: str = "orchestrator"


def record_worker_signal(sig: WorkerSignal) -> None:
    """Append a signal line for later Laplace estimates."""
    path = worker_signals_path()
    line = json.dumps(
        {
            "worker_id": sig.worker_id,
            "ok": sig.ok,
            "latency_ms": sig.latency_ms,
            "source": sig.source,
        },
        ensure_ascii=False,
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return out


def laplace_reliability_weights() -> dict[str, float]:
    """Per-worker multiplicative factor in (0,1]; higher = more historically successful."""
    rows = _read_jsonl(worker_signals_path())
    ok: dict[str, int] = {}
    bad: dict[str, int] = {}
    for r in rows:
        wid = str(r.get("worker_id", ""))
        if not wid:
            continue
        if r.get("ok") is True:
            ok[wid] = ok.get(wid, 0) + 1
        elif r.get("ok") is False:
            bad[wid] = bad.get(wid, 0) + 1
    keys = set(ok) | set(bad)
    weights: dict[str, float] = {}
    for wid in keys:
        o = ok.get(wid, 0)
        b = bad.get(wid, 0)
        # Laplace smoothing; neutral 0.5 when no data
        weights[wid] = (o + 1.0) / (o + b + 2.0)
    return weights


def mean_latency_ms(worker_id: str) -> float | None:
    rows = _read_jsonl(worker_signals_path())
    lat: list[int] = []
    for r in rows:
        if str(r.get("worker_id", "")) != worker_id:
            continue
        v = r.get("latency_ms")
        if isinstance(v, (int, float)) and v >= 0:
            lat.append(int(v))
    if not lat:
        return None
    return sum(lat) / len(lat)


def append_routing_decision(entry: Mapping[str, Any]) -> None:
    """Audit trail for Taskmaster-style routing (why this worker)."""
    path = worker_routing_fdx_path()
    line = json.dumps(dict(entry), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
