"""SQLite bootstrap."""

import tempfile
from pathlib import Path

from ghost_core.storage import init_db, open_sqlite


def test_init_db_idempotent() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.db"
        conn = open_sqlite(p)
        init_db(conn)
        init_db(conn)
        n = conn.execute("SELECT COUNT(*) AS c FROM schema_version").fetchone()["c"]
        assert n >= 1
        conn.close()
