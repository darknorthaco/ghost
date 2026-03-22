"""CLI: init DB, run API, placeholder retrieve."""

from __future__ import annotations

from pathlib import Path

import typer
import uvicorn

from ghost_core.bootstrap import ensure_ghost_db
from ghost_core.config import load_ghost_config, project_root
from ghost_governance.store import append_policy_audit, register_approval_token
from ghost_retrieval.embedder import Embedder
from ghost_retrieval.hybrid import HybridSearchEngine
from ghost_retrieval.ingestion import IngestOptions, ingest_path
from ghost_retrieval.lifecycle import delete_document, rebuild_chunks_fts

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("init-db")
def init_db_cmd(
    config: Path | None = typer.Option(None, "--config", "-c", help="YAML config path"),
) -> None:
    """Create SQLite schema and seed presets from config/presets."""
    cfg = load_ghost_config(config) if config else load_ghost_config()
    sqlite_path = cfg.get("ghost", {}).get("sqlite_path", "data/ghost.db")
    ensure_ghost_db(sqlite_path, cfg)
    typer.echo(f"Initialized database at {sqlite_path}")


@app.command("ingest")
def ingest_cmd(
    path: Path = typer.Argument(..., help="File or directory to ingest"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    chunk_size: int = typer.Option(2000, "--chunk-size"),
    chunk_overlap: int = typer.Option(200, "--chunk-overlap"),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
) -> None:
    """Chunk files, embed locally, and write chunks + vectors to SQLite."""
    cfg = load_ghost_config(config) if config else load_ghost_config()
    sqlite_path = cfg.get("ghost", {}).get("sqlite_path", "data/ghost.db")
    conn = ensure_ghost_db(sqlite_path, cfg)
    r = cfg.get("retrieval", {})
    embedder = Embedder(dimensions=int(r.get("dimensions", 1024)))
    opt = IngestOptions(
        recursive=recursive,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        on_progress=lambda m: typer.echo(m),
    )
    results = ingest_path(conn, embedder, path, options=opt)
    hybrid = HybridSearchEngine(conn, dimensions=int(r.get("dimensions", 1024)))
    hybrid.invalidate_cache()
    for res in results:
        if res.skipped:
            typer.echo(f"Skipped ({res.skip_reason}): {res.source_path}")
        else:
            typer.echo(f"Ingested {res.chunks_written} chunks from {res.source_path}")


@app.command("corpus-delete")
def corpus_delete(
    document_id: str = typer.Argument(..., help="document_id to remove"),
    config: Path | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Delete a document and dependent chunks/embeddings."""
    cfg = load_ghost_config(config) if config else load_ghost_config()
    sqlite_path = cfg.get("ghost", {}).get("sqlite_path", "data/ghost.db")
    conn = ensure_ghost_db(sqlite_path, cfg)
    n = delete_document(conn, document_id)
    r = cfg.get("retrieval", {})
    HybridSearchEngine(conn, dimensions=int(r.get("dimensions", 1024))).invalidate_cache()
    append_policy_audit(conn, "corpus_delete_document", actor="cli", detail={"document_id": document_id})
    typer.echo(f"Deleted rows: {n}")


@app.command("fts-rebuild")
def fts_rebuild_cmd(
    config: Path | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Rebuild chunks FTS index."""
    cfg = load_ghost_config(config) if config else load_ghost_config()
    sqlite_path = cfg.get("ghost", {}).get("sqlite_path", "data/ghost.db")
    conn = ensure_ghost_db(sqlite_path, cfg)
    rebuild_chunks_fts(conn)
    append_policy_audit(conn, "fts_rebuild_chunks", actor="cli", detail={})
    typer.echo("chunks_fts rebuild complete")


@app.command("token-register")
def token_register(
    token: str = typer.Argument(..., help="Approval token to store (hashed)"),
    label: str = typer.Option("cli", "--label"),
    config: Path | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Register a hashed governance token in SQLite for policy gates."""
    cfg = load_ghost_config(config) if config else load_ghost_config()
    sqlite_path = cfg.get("ghost", {}).get("sqlite_path", "data/ghost.db")
    conn = ensure_ghost_db(sqlite_path, cfg)
    register_approval_token(conn, token, label=label)
    typer.echo("Token registered (sha256 stored)")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Run the local FastAPI server."""
    root = project_root()
    uvicorn.run(
        "ghost_api.app:app",
        host=host,
        port=port,
        factory=False,
        app_dir=str(root),
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
