"""Corpus lifecycle: delete documents, rebuild FTS indexes."""

from __future__ import annotations

import sqlite3


def delete_document(conn: sqlite3.Connection, document_id: str) -> int:
    """Remove a document and dependent chunks, embeddings, and FTS rows (CASCADE)."""
    cur = conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
    n = cur.rowcount or 0
    conn.commit()
    return int(n)


def rebuild_chunks_fts(conn: sqlite3.Connection) -> None:
    """Rebuild the chunks FTS index (maintenance / recovery)."""
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
    conn.commit()
