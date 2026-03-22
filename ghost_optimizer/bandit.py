"""Thompson Sampling over discrete weight presets (Beta posteriors per scope)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np


@dataclass
class BanditArm:
    preset_id: str
    alpha: float
    beta: float
    pulls: int
    total_reward: float

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)


class ThompsonSamplingBandit:
    """Scope-keyed bandit; same schema as GHOST `bandit_state` table."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        scope: str,
        rng: np.random.Generator | None = None,
        discount: float | None = None,
    ):
        if discount is not None and not (0.0 < discount < 1.0):
            raise ValueError(f"Discount must be in (0, 1), got {discount}")
        self.conn = conn
        self.scope = scope
        self.rng = rng or np.random.default_rng()
        self.discount = discount

    def get_arms(self) -> list[BanditArm]:
        rows = self.conn.execute(
            """SELECT preset_id, alpha, beta, pulls, total_reward
               FROM bandit_state
               WHERE scope = ?
               ORDER BY preset_id""",
            (self.scope,),
        ).fetchall()
        return [
            BanditArm(
                preset_id=row["preset_id"],
                alpha=row["alpha"],
                beta=row["beta"],
                pulls=row["pulls"],
                total_reward=row["total_reward"],
            )
            for row in rows
        ]

    def select_arm(self) -> str:
        arms = self.get_arms()
        if not arms:
            raise ValueError(
                f"No bandit arms for scope {self.scope!r}; seed presets and init_bandit_arms()."
            )
        samples = [(arm.preset_id, self.rng.beta(arm.alpha, arm.beta)) for arm in arms]
        return max(samples, key=lambda x: x[1])[0]

    def update(self, preset_id: str, reward: float) -> None:
        if not 0.0 <= reward <= 1.0:
            raise ValueError(f"Reward must be in [0, 1], got {reward}")
        if self.discount is not None:
            self.conn.execute(
                """UPDATE bandit_state
                   SET alpha = alpha * ?, beta = beta * ?
                   WHERE scope = ? AND preset_id = ?""",
                (self.discount, self.discount, self.scope, preset_id),
            )
        self.conn.execute(
            """UPDATE bandit_state
               SET alpha = alpha + ?,
                   beta = beta + ?,
                   pulls = pulls + 1,
                   total_reward = total_reward + ?,
                   last_updated = datetime('now')
               WHERE scope = ? AND preset_id = ?""",
            (reward, 1.0 - reward, reward, self.scope, preset_id),
        )
        self.conn.commit()
