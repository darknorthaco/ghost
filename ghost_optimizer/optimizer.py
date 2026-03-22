"""Optimizer service: preset selection + async reward queue with a single-writer DB lock."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections import deque
from typing import Any, Mapping

import numpy as np

from ghost_core.contracts import AuditSink
from ghost_optimizer.bandit import ThompsonSamplingBandit

logger = logging.getLogger(__name__)


class GhostOptimizer:
    """Implements OptimizerPort; `schedule_reward` is non-blocking up to max_queue."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        default_scope: str,
        rng: np.random.Generator,
        audit: AuditSink | None = None,
        discount: float | None = None,
        max_queue: int = 10_000,
    ):
        self._conn = conn
        self._default_scope = default_scope
        self._rng = rng
        self._audit = audit
        self._discount = discount
        self._max_queue = max_queue
        self._lock = threading.Lock()
        self._queue: deque[dict[str, Any]] = deque()
        self._pending_decisions: dict[str, dict[str, Any]] = {}
        self._worker = threading.Thread(target=self._drain_loop, daemon=True)
        self._stop = threading.Event()
        self._worker.start()

    def register_decision(self, decision_id: str, meta: Mapping[str, Any]) -> None:
        """Link retrieval decision_id to scope and preset for reward attribution."""
        with self._lock:
            self._pending_decisions[decision_id] = dict(meta)

    def reset_bandit_scope(self, scope: str) -> None:
        """Reinitialize Beta priors for every preset in `weight_presets` (governance-gated at API)."""
        rows = self._conn.execute("SELECT preset_id FROM weight_presets").fetchall()
        preset_ids = [r["preset_id"] for r in rows]
        with self._lock:
            self._conn.execute("DELETE FROM bandit_state WHERE scope = ?", (scope,))
            for pid in preset_ids:
                self._conn.execute(
                    """INSERT OR IGNORE INTO bandit_state (scope, preset_id, alpha, beta)
                       VALUES (?, ?, 1.0, 1.0)""",
                    (scope, pid),
                )
            self._conn.commit()

    def close(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._worker.join(timeout=timeout)

    def _bandit(self, scope: str) -> ThompsonSamplingBandit:
        return ThompsonSamplingBandit(
            self._conn,
            scope,
            rng=self._rng,
            discount=self._discount,
        )

    def select_preset(self, scope: str) -> str:
        with self._lock:
            b = self._bandit(scope)
            preset_id = b.select_arm()
            arm_ids = [a.preset_id for a in b.get_arms()]
        if self._audit:
            self._audit.append_optimizer_trace(
                {
                    "event": "select_preset",
                    "scope": scope,
                    "preset_id": preset_id,
                    "arms": arm_ids,
                }
            )
        return preset_id

    @property
    def reward_queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    def bandit_snapshot(self, scope: str) -> dict[str, Any]:
        """Inspectable posteriors for a scope (audit-friendly)."""
        with self._lock:
            b = self._bandit(scope)
            arms = b.get_arms()
        return {
            "scope": scope,
            "arms": [
                {
                    "preset_id": a.preset_id,
                    "alpha": a.alpha,
                    "beta": a.beta,
                    "mean": a.mean,
                    "pulls": a.pulls,
                    "total_reward": a.total_reward,
                }
                for a in arms
            ],
        }

    def schedule_reward(
        self,
        decision_id: str,
        reward: float,
        meta_override: Mapping[str, Any] | None = None,
    ) -> None:
        if not 0.0 <= reward <= 1.0:
            raise ValueError("reward must be in [0, 1]")
        with self._lock:
            if len(self._queue) >= self._max_queue:
                raise RuntimeError("reward queue full")
            self._queue.append(
                {
                    "decision_id": decision_id,
                    "reward": reward,
                    "ts": time.time(),
                    "meta_override": dict(meta_override) if meta_override else None,
                }
            )

    def _drain_loop(self) -> None:
        while not self._stop.is_set():
            item: dict[str, Any] | None = None
            with self._lock:
                if self._queue:
                    item = self._queue.popleft()
            if item is None:
                time.sleep(0.05)
                continue
            self._apply_reward(item)

    def _apply_reward(self, item: dict[str, Any]) -> None:
        decision_id = item["decision_id"]
        reward = float(item["reward"])
        override = item.get("meta_override")
        with self._lock:
            meta = self._pending_decisions.pop(decision_id, None)
        scope = self._default_scope
        preset_id = "equal"
        if meta:
            scope = str(meta.get("scope", scope))
            preset_id = str(meta.get("preset_id", preset_id))
        if override:
            scope = str(override.get("scope", scope))
            preset_id = str(override.get("preset_id", preset_id))
        try:
            with self._lock:
                self._bandit(scope).update(preset_id, reward)
        except Exception:
            logger.exception("bandit update failed for decision_id=%s", decision_id)
            return
        if self._audit:
            self._audit.append_optimizer_trace(
                {
                    "event": "reward_applied",
                    "decision_id": decision_id,
                    "scope": scope,
                    "preset_id": preset_id,
                    "reward": reward,
                    "meta_override": override,
                }
            )
