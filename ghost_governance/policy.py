"""Human stewardship gates for policy mutations (presets, bandit resets)."""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Mapping


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return str(v)
    return None


def policy_change_approved(
    headers: Mapping[str, str],
    config: dict[str, Any],
    conn: sqlite3.Connection | None = None,
) -> bool:
    """When `governance.require_human_approval_for_policy_change` is true, require approval."""
    gov = config.get("governance", {})
    if not gov.get("require_human_approval_for_policy_change"):
        return True
    header_val = _header(headers, "X-Ghost-Policy-Approve")
    if conn is not None and header_val:
        from ghost_governance.store import hash_token

        h = hash_token(header_val)
        row = conn.execute(
            "SELECT 1 FROM governance_tokens WHERE token_hash = ?",
            (h,),
        ).fetchone()
        if row is not None:
            return True
    token = os.environ.get("GHOST_POLICY_TOKEN") or gov.get("policy_approval_token")
    if not token or not header_val:
        return False
    return header_val == str(token)
