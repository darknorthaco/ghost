# ghost
GHOST is a sovereign, offline‑first adaptive knowledge engine that combines:

Phantom’s distributed orchestration patterns  
(worker registry, deterministic routing, governance hooks)

and

The retrieval‑weight experiment’s adaptive hybrid search  
(BM25 + dense embeddings + RRF + Thompson Sampling)

into a single, doctrine‑driven system designed for auditability, determinism, and continuous learning.

GHOST ingests documents, chunks them, embeds them, and stores them in a local SQLite corpus.
Retrieval uses a hybrid ranking pipeline with explainable scoring.
Feedback updates a Thompson Sampling bandit that adapts retrieval weights over time.
All decisions—retrieval, routing, optimization, governance—are logged as structured JSONL traces.

GHOST is built as a living system with clear boundaries, explicit contracts, and human‑in‑the‑loop governance.
It is not Phantom, and not the retrieval‑weight experiment—it is a new system that integrates their strengths under a unified architecture.

**Acknowledgments:** Retrieval lineage from the **retrieval-weight experiment** ([kusp-dev/retrieval-weight-experiment](https://github.com/kusp-dev/retrieval-weight-experiment)) — **[Alfonso DiRocco](https://github.com/fonz-ai)** ([@fonz-ai](https://github.com/fonz-ai)). See [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md).

## Licensing

GHOST uses **dual licensing**:

- **Noncommercial use** — free under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) (see [`LICENSE`](LICENSE)). Suitable for personal, hobby, research, and other permitted noncommercial use.
- **Commercial / industrial use** — requires a **commercial license** from Dark North Co. See [`COMMERCIAL.md`](COMMERCIAL.md).

**Doctrine** (product principles, disclaimers): [`DOCTRINE.md`](DOCTRINE.md) · **Contributing**: [`CONTRIBUTING.md`](CONTRIBUTING.md) · **Acknowledgments**: [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md)

### Deployment observability (FDX)

Structured deploy/discovery/installer traces are written as **append-only JSONL** under **`%USERPROFILE%\.ghost\logs\`** (Windows) or **`~/.ghost/logs/`** (POSIX): `deploy_fdx.jsonl`, `discovery_fdx.jsonl`, `installer_fdx.jsonl`. See **[`docs/FDX_OBSERVABILITY.md`](docs/FDX_OBSERVABILITY.md)** for the pipeline map, path matrix, failure-mode notes, and how to report issues.

Core Features
Offline‑first, sovereign design

Hybrid BM25 + dense + RRF retrieval

Adaptive weight optimization (Thompson Sampling)

Deterministic worker routing

Content‑addressable ingestion with deduplication

Full corpus lifecycle management

Governance tokens + policy‑gated admin actions

Structured JSONL audit logs

Replayable optimizer traces

Metrics for retrieval, latency, and reward loops

FastAPI + CLI interface

Use Cases
Local knowledge engines

On‑prem enterprise search

Adaptive retrieval research

Sovereign AI assistants

Distributed worker orchestration

For GHOST's identity, architecture, and governance, see GHOST_MANIFEST.md.
