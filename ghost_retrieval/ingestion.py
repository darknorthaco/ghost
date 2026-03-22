"""Ingest files into documents/chunks, FTS, and chunk_embeddings (local embedder)."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import sqlite3

from ghost_retrieval.embedder import Embedder, store_chunk_embedding


@dataclass
class IngestResult:
    document_id: str
    chunks_written: int
    source_path: str
    content_sha256: str
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class IngestOptions:
    recursive: bool = False
    """Allowed file suffixes (lower case, with dot). Empty = use mime / sniff only."""
    extensions: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {".txt", ".md", ".rst", ".py", ".json", ".yaml", ".yml", ".toml", ".csv"}
        )
    )
    mime_prefix_allow: tuple[str, ...] = ("text/", "application/json", "application/yaml")
    chunk_size: int = 2000
    chunk_overlap: int = 200
    skip_if_content_unchanged: bool = True
    on_progress: Callable[[str], None] | None = None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if max_chars <= 0:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    step = max(1, max_chars - overlap)
    while start < n:
        end = min(start + max_chars, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start += step
    return chunks if chunks else [text]


def _mime_ok(path: Path, mime_prefix_allow: tuple[str, ...]) -> bool:
    mime, _ = mimetypes.guess_type(str(path))
    if mime is None:
        return True
    return any(mime.startswith(p) for p in mime_prefix_allow)


def _extension_ok(path: Path, extensions: frozenset[str]) -> bool:
    if not extensions:
        return True
    return path.suffix.lower() in extensions


def iter_ingest_files(root: Path, options: IngestOptions) -> Iterable[Path]:
    root = root.resolve()
    if root.is_file():
        if _extension_ok(root, options.extensions) and _mime_ok(root, options.mime_prefix_allow):
            yield root
        return
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    if options.recursive:
        for p in sorted(root.rglob("*")):
            if p.is_file() and _extension_ok(p, options.extensions) and _mime_ok(p, options.mime_prefix_allow):
                yield p
    else:
        for p in sorted(root.iterdir()):
            if p.is_file() and _extension_ok(p, options.extensions) and _mime_ok(p, options.mime_prefix_allow):
                yield p


def ingest_file(
    conn: sqlite3.Connection,
    embedder: Embedder,
    file_path: Path,
    *,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
    skip_if_content_unchanged: bool = True,
    on_progress: Callable[[str], None] | None = None,
    options: IngestOptions | None = None,
) -> IngestResult:
    """Read file bytes, hash for content-addressable document_id, chunk, embed, store."""
    opt = options or IngestOptions(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunk_size = opt.chunk_size
    chunk_overlap = opt.chunk_overlap
    skip_if_content_unchanged = opt.skip_if_content_unchanged
    on_progress = on_progress or opt.on_progress

    raw_bytes = file_path.read_bytes()
    sha = _sha256_hex(raw_bytes)
    document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ghost:doc:{sha}"))
    title = file_path.name

    if skip_if_content_unchanged:
        row = conn.execute(
            "SELECT content_sha256 FROM documents WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        if row is not None and row["content_sha256"] == sha:
            if on_progress:
                on_progress(f"skip unchanged {file_path}")
            return IngestResult(
                document_id=document_id,
                chunks_written=0,
                source_path=str(file_path.resolve()),
                content_sha256=sha,
                skipped=True,
                skip_reason="content_unchanged",
            )

    raw = raw_bytes.decode("utf-8", errors="replace")

    conn.execute(
        "DELETE FROM documents WHERE source_path = ? AND document_id != ?",
        (str(file_path.resolve()), document_id),
    )
    conn.execute(
        """INSERT OR REPLACE INTO documents (document_id, source_path, title, content_sha256)
           VALUES (?, ?, ?, ?)""",
        (document_id, str(file_path.resolve()), title, sha),
    )
    conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    pieces = _chunk_text(raw, chunk_size, chunk_overlap)
    chunk_ids: list[str] = []
    texts: list[str] = []
    for i, piece in enumerate(pieces):
        ph = _sha256_hex(piece.encode("utf-8"))
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ghost:chunk:{document_id}:{i}:{ph}"))
        conn.execute(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, document_id, chunk_index, title, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                chunk_id,
                document_id,
                i,
                f"{title} §{i}",
                piece,
                json.dumps(
                    {
                        "source_path": str(file_path),
                        "chunk_index": i,
                        "content_sha256": sha,
                    }
                ),
            ),
        )
        chunk_ids.append(chunk_id)
        texts.append(piece)
    if texts:
        matrices = embedder.embed_batch(texts)
        for i, cid in enumerate(chunk_ids):
            store_chunk_embedding(conn, cid, matrices[i], model=embedder.model_name)
    conn.commit()
    if on_progress:
        on_progress(f"ingested {file_path} -> {len(chunk_ids)} chunks")
    return IngestResult(
        document_id=document_id,
        chunks_written=len(chunk_ids),
        source_path=str(file_path.resolve()),
        content_sha256=sha,
    )


def ingest_path(
    conn: sqlite3.Connection,
    embedder: Embedder,
    path: Path,
    *,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
    options: IngestOptions | None = None,
) -> list[IngestResult]:
    """Ingest a file or walk a directory (optional recursive) with filtering."""
    if options is not None:
        opt = options
    else:
        opt = IngestOptions(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    out: list[IngestResult] = []
    for fp in iter_ingest_files(path, opt):
        out.append(
            ingest_file(
                conn,
                embedder,
                fp,
                options=opt,
            )
        )
    return out
