"""SQLite schema bootstrap for GHOST (corpus + optimizer state)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Corpus + hybrid retrieval (from retrieval-weight experiment, trimmed to GHOST needs)
CORPUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    skill_id    TEXT PRIMARY KEY,
    domain      TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
    skill_id UNINDEXED,
    title,
    content,
    content='skills',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
    INSERT INTO skills_fts(rowid, skill_id, title, content)
    VALUES (new.rowid, new.skill_id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
    INSERT INTO skills_fts(skills_fts, rowid, skill_id, title, content)
    VALUES ('delete', old.rowid, old.skill_id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills BEGIN
    INSERT INTO skills_fts(skills_fts, rowid, skill_id, title, content)
    VALUES ('delete', old.rowid, old.skill_id, old.title, old.content);
    INSERT INTO skills_fts(rowid, skill_id, title, content)
    VALUES (new.rowid, new.skill_id, new.title, new.content);
END;

CREATE TABLE IF NOT EXISTS skill_embeddings (
    skill_id    TEXT PRIMARY KEY REFERENCES skills(skill_id),
    embedding   BLOB NOT NULL,
    model       TEXT NOT NULL DEFAULT 'local',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weight_presets (
    preset_id   TEXT PRIMARY KEY,
    w_recency   REAL NOT NULL,
    w_importance REAL NOT NULL,
    w_relevance REAL NOT NULL,
    CHECK (abs(w_recency + w_importance + w_relevance - 1.0) < 0.02)
);

-- Thompson Sampling posteriors: scope replaces experiment condition_id
CREATE TABLE IF NOT EXISTS bandit_state (
    scope       TEXT NOT NULL,
    preset_id   TEXT NOT NULL REFERENCES weight_presets(preset_id),
    alpha       REAL NOT NULL DEFAULT 1.0,
    beta        REAL NOT NULL DEFAULT 1.0,
    pulls       INTEGER NOT NULL DEFAULT 0,
    total_reward REAL NOT NULL DEFAULT 0.0,
    last_updated TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (scope, preset_id)
);

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Document corpus (chunk IDs; FTS5 external content pattern from retrieval-weight experiment)
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    content_sha256 TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    title,
    content,
    content='chunks',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, chunk_id, title, content)
    VALUES (new.rowid, new.chunk_id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, title, content)
    VALUES ('delete', old.rowid, old.chunk_id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, title, content)
    VALUES ('delete', old.rowid, old.chunk_id, old.title, old.content);
    INSERT INTO chunks_fts(rowid, chunk_id, title, content)
    VALUES (new.rowid, new.chunk_id, new.title, new.content);
END;

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id    TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding   BLOB NOT NULL,
    model       TEXT NOT NULL DEFAULT 'local',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS governance_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS governance_tokens (
    token_hash TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA_VERSION = 3

# Idempotent DDL for DBs created before v2 (schema_version row = 1 only).
MIGRATION_V1_TO_V2 = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,
    title,
    content,
    content='chunks',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, chunk_id, title, content)
    VALUES (new.rowid, new.chunk_id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, title, content)
    VALUES ('delete', old.rowid, old.chunk_id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, title, content)
    VALUES ('delete', old.rowid, old.chunk_id, old.title, old.content);
    INSERT INTO chunks_fts(rowid, chunk_id, title, content)
    VALUES (new.rowid, new.chunk_id, new.title, new.content);
END;

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id    TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding   BLOB NOT NULL,
    model       TEXT NOT NULL DEFAULT 'local',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def open_sqlite(path: str | Path) -> sqlite3.Connection:
    """Open SQLite with WAL, foreign keys, and Row factory."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Bandit reward worker runs on a background thread; all access is serialized via locks.
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


GOVERNANCE_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS governance_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS governance_tokens (
    token_hash TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply additive migrations; safe to call on every open."""
    v_row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version").fetchone()
    current = int(v_row["v"])
    if current >= SCHEMA_VERSION:
        return
    if current < 2:
        conn.executescript(MIGRATION_V1_TO_V2)
    if current < 3:
        conn.executescript(GOVERNANCE_SCHEMA_DDL)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()]
        if cols and "content_sha256" not in cols:
            conn.execute("ALTER TABLE documents ADD COLUMN content_sha256 TEXT")
    if not conn.execute(
        "SELECT 1 FROM schema_version WHERE version = ?", (SCHEMA_VERSION,)
    ).fetchone():
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(CORPUS_SCHEMA)
    n = conn.execute("SELECT COUNT(*) AS c FROM schema_version").fetchone()["c"]
    if n == 0:
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    conn.commit()
    migrate_schema(conn)


def seed_preset_from_weights(
    conn: sqlite3.Connection,
    preset_id: str,
    w_recency: float,
    w_importance: float,
    w_relevance: float,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO weight_presets
           (preset_id, w_recency, w_importance, w_relevance)
           VALUES (?, ?, ?, ?)""",
        (preset_id, w_recency, w_importance, w_relevance),
    )
    conn.commit()


def init_bandit_arms(conn: sqlite3.Connection, scope: str, preset_ids: list[str]) -> None:
    for pid in preset_ids:
        conn.execute(
            """INSERT OR IGNORE INTO bandit_state (scope, preset_id, alpha, beta)
               VALUES (?, ?, 1.0, 1.0)""",
            (scope, pid),
        )
    conn.commit()
