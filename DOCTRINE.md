# GHOST doctrine

GHOST is built around explicit **product and governance principles**. These describe **design intent** and engineering values—they are **not** warranties of performance, fitness for a particular purpose, or guarantees of regulatory or legal compliance.

## Core principles

| Principle | Meaning |
|-----------|--------|
| **Sovereignty** | Users own their data and runtime; offline-first and local control where possible. |
| **Determinism** | Seeded, reproducible behavior where the architecture promises it; explicit randomness where not. |
| **Auditability** | Structured logs and traceable decisions for inspection and review. |
| **Human stewardship** | Policy gates and governance hooks so humans remain in the loop for consequential changes. |
| **Explicit boundaries** | No hidden global mutable state; clear contracts between components. |

## Relationship to law and risk

- **No professional advice.** Nothing in this repository (including `DOCTRINE.md`, `LICENSE`, `COMMERCIAL.md`, or documentation) is legal, regulatory, financial, or security advice. **Consult qualified counsel** for your jurisdiction and use case.
- **Your compliance is your responsibility.** You are solely responsible for how you deploy GHOST (including data protection, sector rules, export controls, sanctions, and employment or safety requirements).
- **AS IS.** Software is provided **as is** under the applicable license. See [`LICENSE`](LICENSE). The doctrine does not create an additional warranty.
- **No endorsement.** A description of use cases in documentation does not imply certification for any regulated or safety-critical use unless **explicitly** stated in a separate written agreement from Dark North Co.

## Lineage

Hybrid retrieval and bandit-style adaptation build on prior work summarized in [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md), including the retrieval-weight experiment by [Alfonso DiRocco](https://github.com/fonz-ai) ([@fonz-ai](https://github.com/fonz-ai)).

## Contributions

By contributing, you agree your contributions are under the same terms as the project license. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
