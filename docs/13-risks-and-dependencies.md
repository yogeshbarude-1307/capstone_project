# 13 — Risks and Dependencies

Consolidated and deduplicated from all five source research documents, filtered to what's actually relevant to an offline/synthetic-only POC (production-only risks are marked as such and deferred rather than mitigated now).

## POC-relevant risks

| Risk | Consequence | Mitigation |
|---|---|---|
| Synthetic notes are unrealistically easy or the generator accidentally leaks future truth into past-dated notes | Inflated, meaningless extraction/forecast results | Enforced causal generation order (`06-synthetic-data-design.md`); explicit code-level assertion that the demand-realization step never reads note text/signals |
| Point-in-time leakage through timestamp handling | False forecast lift, invalid experiment | Explicit eligibility rule (`03-data-model.md`); dedicated adversarial leakage tests (`11-testing-strategy.md`); arm D negative control |
| Local LLM stage infeasible on available hardware | Extraction pipeline degrades or stalls | Documented degradation path to rules+NER only (`07-extraction-pipeline-design.md`); technology matrix names this OPEN and testable early (Milestone 3) |
| Extraction invents unsupported values (magnitude, entity, time) | Bad, fabricated forecast features | Evidence-span requirement on every populated field; unsupported-inference rate tracked as a first-class metric |
| Negation/conditionality mishandled | Sign-flipped or overconfident signals | Dedicated hard-case unit tests + oversampled D2/D5 cases |
| Duplicate or contradicting notes double-count or hide reversal | Artificially amplified or stale signal | `related_signal_ids`/`supersedes_signal_id` + explicit reconciliation logic |
| Forecast model can't exploit even a well-extracted signal (arm B ≈ A) | Business hypothesis fails regardless of NLP quality | 4-arm design isolates this specifically so it's discovered early and cheaply (Milestone 8–9), not after a large extraction investment |
| Synthetic-only results get reported/interpreted as real-world business value | False confidence, wasted follow-on investment | Mandatory verbatim caveat in every evaluation report (`09-evaluation-plan.md`); explicit non-goal in `01-poc-scope-and-non-goals.md` |
| D2 gold-set annotation effort underestimated | Extraction evaluation delayed or under-powered | Sizing flagged as PROPOSED/adjustable in `06-synthetic-data-design.md`; can be scaled down for a capstone timeline if needed |
| Drift monitors too noisy (constant false alerts) or too slow (miss seeded shifts) | Monitoring demonstration unconvincing | Calibration-on-no-drift-window requirement + persistence-based alerting (`10-drift-monitoring-plan.md`) |
| Local compute/runtime limits (no GPU, limited RAM) | Slower iteration, may force the degraded extraction path | Named explicitly as OPEN; architecture is designed to tolerate the degraded path without invalidating the rest of the experiment |

## Deferred (production-only) risks — documented, not mitigated in this POC

Real-note confidentiality/PII exposure; extractor-version rollback and reprocessing at scale; production SLA/freshness guarantees against a real forecast cadence; human-review workflow at volume; authentication/authorization for a real network-facing service; cost/capacity planning against real vendor pricing (moot while offline); supply-chain review of any locally-hosted model weights before production use; governance/retention policy for real business notes.

## Dependencies

- Milestone 3 (extraction) depends on the local LLM/runtime feasibility check (`05-technology-decision-matrix.md`, OPEN).
- Milestone 4 (extraction evaluation) depends on D2 annotation being completed to a usable size.
- Milestone 9 (evaluation/ablations) depends on a business-approved minimum forecast-lift threshold to make a clean go/iterate/stop call — currently OPEN (`14-open-questions.md`); in its absence, results will be reported with the statistical evidence and left as an explicit recommendation rather than an automatic pass/fail.
