"""Persisted governance: hashed approval tokens and policy audit trail."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Mapping


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_approval_token(conn: sqlite3.Connection, token: str, label: str = "") -> None:
    conn.execute(
        """INSERT OR REPLACE INTO governance_tokens (token_hash, label, created_at)
           VALUES (?, ?, datetime('now'))""",
        (hash_token(token), label),
    )
    conn.commit()


def token_exists(conn: sqlite3.Connection, token: str) -> bool:
    h = hash_token(token)
    row = conn.execute("SELECT 1 FROM governance_tokens WHERE token_hash = ?", (h,)).fetchone()
    return row is not None


def append_policy_audit(
    conn: sqlite3.Connection,
    action: str,
    actor: str = "",
    detail: Mapping[str, Any] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO governance_audit (action, actor, detail_json) VALUES (?, ?, ?)",
        (action, actor, json.dumps(dict(detail or {}), default=str)),
    )
    conn.commit()


def list_approval_token_hashes(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT token_hash FROM governance_tokens").fetchall()
    return [r["token_hash"] for r in rows]
