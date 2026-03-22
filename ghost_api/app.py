"""FastAPI application — local-only by default; wire dependencies explicitly."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ghost_core.bootstrap import ensure_ghost_db
from ghost_core.config import load_ghost_config
from ghost_core.metrics import GhostMetrics
from ghost_core.types import RetrieveRequest, WorkerContext
from ghost_governance.audit import JsonlAuditSink
from ghost_governance.policy import policy_change_approved
from ghost_governance.store import append_policy_audit
from ghost_optimizer.optimizer import GhostOptimizer
from ghost_retrieval.embedder import Embedder
from ghost_retrieval.hybrid import HybridSearchEngine
from ghost_retrieval.lifecycle import delete_document, rebuild_chunks_fts
from ghost_retrieval.pipeline import DefaultRetrievePipeline


class RetrieveBody(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    preset_id: str | None = None


class FeedbackBody(BaseModel):
    decision_id: str
    reward: float = Field(ge=0.0, le=1.0)
    scope: str | None = None
    preset_id: str | None = None


@dataclass
class AppState:
    pipeline: DefaultRetrievePipeline | None = None
    optimizer: GhostOptimizer | None = None
    config: dict[str, Any] = field(default_factory=dict)
    conn: Any = None
    hybrid: HybridSearchEngine | None = None
    metrics: GhostMetrics | None = None
    audit: JsonlAuditSink | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_ghost_config()
    paths = cfg.get("ghost", {})
    sqlite_path = paths.get("sqlite_path", "data/ghost.db")
    audit_dir = paths.get("audit_log_dir", "data/audit")
    seed = int(paths.get("random_seed", 42))
    conn = ensure_ghost_db(sqlite_path, cfg)
    audit = JsonlAuditSink(Path(audit_dir))
    r = cfg.get("retrieval", {})
    cm = r.get("corpus_mode", "auto")
    if cm not in ("auto", "skills", "chunks"):
        cm = "auto"
    hybrid = HybridSearchEngine(
        conn,
        rrf_k=int(r.get("rrf_k", 60)),
        bm25_weight=float(r.get("bm25_weight", 0.4)),
        dense_weight=float(r.get("dense_weight", 0.6)),
        dimensions=int(r.get("dimensions", 1024)),
        corpus_mode=cm,
    )
    embedder = Embedder(dimensions=int(r.get("dimensions", 1024)))
    pipeline = DefaultRetrievePipeline(conn, embedder, hybrid, audit=audit)
    opt_cfg = cfg.get("optimizer", {})
    rng = np.random.default_rng(seed)
    optimizer = GhostOptimizer(
        conn,
        default_scope=str(opt_cfg.get("default_scope", "global")),
        rng=rng,
        audit=audit,
        discount=opt_cfg.get("bandit_discount"),
        max_queue=int(opt_cfg.get("reward_queue_max", 10_000)),
    )
    state.pipeline = pipeline
    state.optimizer = optimizer
    state.config = cfg
    state.conn = conn
    state.hybrid = hybrid
    state.metrics = GhostMetrics()
    state.audit = audit
    yield
    optimizer.close()


def create_app() -> FastAPI:
    app = FastAPI(title="GHOST", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "system": "ghost"}

    @app.get("/v1/metrics")
    def metrics_ep() -> dict[str, Any]:
        if state.metrics is None:
            raise HTTPException(status_code=503, detail="metrics unavailable")
        snap = state.metrics.snapshot()
        if state.optimizer is not None:
            snap["reward_queue_depth"] = state.optimizer.reward_queue_depth
        return snap

    @app.post("/v1/retrieve")
    def retrieve(body: RetrieveBody) -> dict[str, Any]:
        assert state.pipeline is not None and state.metrics is not None
        t0 = time.perf_counter()
        if body.preset_id is None and state.optimizer is not None:
            scope = str(state.config.get("optimizer", {}).get("default_scope", "global"))
            preset_id = state.optimizer.select_preset(scope)
        else:
            preset_id = body.preset_id or "equal"
        req = RetrieveRequest(
            query=body.query,
            limit=body.limit,
            preset_id=preset_id,
            worker_context=WorkerContext(),
        )
        try:
            resp = state.pipeline.retrieve(req)
        except KeyError as e:
            state.metrics.record_retrieve(time.perf_counter() - t0, error=True)
            raise HTTPException(status_code=400, detail=str(e)) from e
        state.metrics.record_retrieve(time.perf_counter() - t0, error=False)
        if state.optimizer is not None:
            scope = str(state.config.get("optimizer", {}).get("default_scope", "global"))
            state.optimizer.register_decision(
                resp.decision_id,
                {"scope": scope, "preset_id": preset_id},
            )
        return {
            "decision_id": resp.decision_id,
            "preset_id": resp.preset_id,
            "chunks": [c.__dict__ for c in resp.chunks],
            "explain": dict(resp.explain),
        }

    @app.post("/v1/feedback")
    def feedback(body: FeedbackBody) -> dict[str, Any]:
        if state.optimizer is None or state.metrics is None:
            raise HTTPException(status_code=503, detail="optimizer unavailable")
        override = None
        if body.scope is not None or body.preset_id is not None:
            default_scope = str(state.config.get("optimizer", {}).get("default_scope", "global"))
            override = {
                "scope": body.scope if body.scope is not None else default_scope,
                "preset_id": body.preset_id if body.preset_id is not None else "equal",
            }
        state.optimizer.schedule_reward(body.decision_id, body.reward, meta_override=override)
        state.metrics.record_feedback()
        audit = state.pipeline.audit if state.pipeline else None
        if audit is not None:
            audit.append_optimizer_trace(
                {
                    "event": "feedback_queued",
                    "decision_id": body.decision_id,
                    "reward": body.reward,
                    "meta_override": override,
                }
            )
        return {"status": "queued"}

    @app.get("/v1/bandit/{scope}")
    def bandit_snapshot(scope: str) -> dict[str, Any]:
        if state.optimizer is None:
            raise HTTPException(status_code=503, detail="optimizer unavailable")
        return state.optimizer.bandit_snapshot(scope)

    @app.post("/v1/admin/bandit/reset")
    def bandit_reset(request: Request, scope: str = "global") -> dict[str, str]:
        if not policy_change_approved(request.headers, state.config, conn=state.conn):
            raise HTTPException(status_code=403, detail="policy approval required")
        if state.optimizer is None or state.conn is None:
            raise HTTPException(status_code=503, detail="optimizer unavailable")
        state.optimizer.reset_bandit_scope(scope)
        append_policy_audit(state.conn, "bandit_reset", actor="", detail={"scope": scope})
        return {"status": "ok", "scope": scope}

    @app.post("/v1/admin/hybrid/invalidate")
    def invalidate_hybrid(request: Request) -> dict[str, str]:
        if not policy_change_approved(request.headers, state.config, conn=state.conn):
            raise HTTPException(status_code=403, detail="policy approval required")
        if state.hybrid is None:
            raise HTTPException(status_code=503, detail="hybrid unavailable")
        state.hybrid.invalidate_cache()
        return {"status": "ok"}

    @app.delete("/v1/corpus/documents/{document_id}")
    def corpus_delete_document(request: Request, document_id: str) -> dict[str, Any]:
        if not policy_change_approved(request.headers, state.config, conn=state.conn):
            raise HTTPException(status_code=403, detail="policy approval required")
        if state.conn is None or state.hybrid is None:
            raise HTTPException(status_code=503, detail="unavailable")
        n = delete_document(state.conn, document_id)
        state.hybrid.invalidate_cache()
        append_policy_audit(state.conn, "corpus_delete_document", detail={"document_id": document_id})
        return {"deleted": n, "document_id": document_id}

    @app.post("/v1/admin/fts/rebuild")
    def fts_rebuild(request: Request) -> dict[str, str]:
        if not policy_change_approved(request.headers, state.config, conn=state.conn):
            raise HTTPException(status_code=403, detail="policy approval required")
        if state.conn is None:
            raise HTTPException(status_code=503, detail="unavailable")
        rebuild_chunks_fts(state.conn)
        append_policy_audit(state.conn, "fts_rebuild_chunks", detail={})
        return {"status": "ok"}

    return app


app = create_app()
