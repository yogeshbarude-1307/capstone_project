> Historical design/evidence: the [realignment acceptance contract](20-realignment-acceptance.md) supersedes conflicting scope and semantics below. The current target is weekly customer demand, Monday UTC cutoffs, four separate weekly horizons, PASS-only published signals, required HTTP consumption, a one-hour simulated freshness target, and matched forecast-degradation lead time. Earlier test counts and results require revalidation.

# 01 — POC Scope and Non-Goals

## Confirmed POC scope

The POC is a **local, offline, batch-first pipeline** that demonstrates, on synthetic data only:

1. A causally-ordered synthetic-note generator producing notes with known, hidden ground truth.
2. A hybrid (rules + NER + local constrained-decoding LLM) extraction pipeline that turns notes into structured, versioned demand-signal events, with mandatory abstention on insufficient evidence.
3. Deterministic schema and business-rule validation of every extracted event.
4. An append-only signal ledger preserving source evidence, extraction provenance, and revision history.
5. A point-in-time-correct transformation of signals into forecast-ready features, keyed by entity and forecast cutoff.
6. A local, callable feature-access layer (optionally wrapped in a localhost-only HTTP interface).
7. A controlled 4-arm forecasting experiment (tabular baseline / oracle-signal / extracted-signal / shuffled-signal control) evaluated with rolling-origin time-series cross-validation.
8. Extraction-quality evaluation kept fully independent from forecast-quality evaluation.
9. A layered drift/monitoring demonstration using deliberately seeded synthetic scenarios.
10. End-to-end lineage from a served feature back to its originating note.
11. A documented gap analysis of what would have to change for production and for real data.

## Explicit non-goals (do not build these in the POC)

| Excluded | Why |
|---|---|
| Kubernetes / container orchestration | Single local process/repo is sufficient to test the hypothesis; no scaling requirement exists yet. |
| Message bus / event streaming (Kafka, etc.) | Batch/offline processing is sufficient; no real-time source feed exists. |
| Online/low-latency feature store | No confirmed synchronous forecast consumer exists; batch retrieval meets the stated need. |
| Automatic model/extractor retraining | Introduces risk (silent quality regression) with no corresponding POC requirement. |
| Multi-region / high-availability infrastructure | Irrelevant to a single-machine, offline POC. |
| Real company notes of any kind | Not available; and even if available, would require a security/PII review that is out of scope (offline constraint). |
| Hosted/API LLMs (Claude, OpenAI, etc.) | Violates the confirmed offline/local-only constraint. |
| Cloud storage, cloud model registries, SaaS observability/lineage | Violates the confirmed offline/local-only constraint. |
| Enterprise feature store product (Feast, Databricks Feature Store, etc.) | Its *point-in-time-join pattern* is reused directly in local SQL; the product itself adds operational weight the POC doesn't need. |
| Formal security/IAM/authN-authZ implementation | No network-facing service and no real/sensitive data exist in this POC; documented as a production requirement only. |
| Human-review workflow tooling (queues, reviewer UI) | Simulated via a small local script only if needed for D2 gold-set adjudication; not a product feature. |
| Production-grade cost/capacity modeling with real vendor pricing | Meaningless without hosted-API usage; a local compute/runtime-cost note is included instead. |

## Boundary rule

Any component listed above may be *documented* as a production consideration (see `13-risks-and-dependencies.md`), but none of them are implemented, stubbed as if real, or silently assumed present. Where the source research assumed a hosted LLM (several documents did), that assumption is explicitly overridden by the offline constraint — see `00-development-requirements-spec.md` header and `05-technology-decision-matrix.md`.
