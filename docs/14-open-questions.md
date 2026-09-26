# 14 — Open Questions / Development Blockers

Per the handoff's stop-condition rule: none of these are guessed. Each is tagged with who can resolve it and what it affects if left unresolved.

| # | Open question | Affects | Who resolves it | If unresolved |
|---|---|---|---|---|
| 1 | Exact local LLM/runtime to use for the semantic-extraction stage (which small open-weight model, which local serving runtime) | Extraction pipeline (Milestone 3), technology matrix | Project owner / a quick local feasibility check | Pipeline uses the documented degradation path (rules+NER only) |
| 2 | GPU availability on the target machine | Same as above (affects how large a local model is practical) | Project owner | Assume CPU-only; smaller model candidates only |
| 3 | Forecast grain (e.g. customer-SKU, region-product, other) | Data model entity keys, feature aggregation | Forecasting team / not available in this capstone context | Synthetic generator will define its own grain explicitly and document it as an engineering default, not a real business grain |
| 4 | Forecast horizon(s) and cadence | Temporal windows, evaluation design | Forecasting team | Synthetic generator/experiment will pick and document reasonable defaults (e.g. weekly cadence, 4–12 week horizon) as PROPOSED, clearly labeled as not sourced from a real forecasting process |
| 5 | Business-approved minimum meaningful forecast lift | Milestone 9 go/iterate/stop decision | Business/product owner | Results reported with full statistical detail; recommendation given without a hard pass/fail threshold |
| 6 | Whether a localhost HTTP wrapper is worth building vs. a callable Python API only | Milestone 6 scope | Project owner (e.g. capstone grading requirements) | Default to callable Python API only |
| 7 | Real note volume, language(s), typical length | Not applicable to this synthetic-only POC; relevant only if the project later pursues real-data validation | Business/domain SME | Deferred entirely — out of scope while offline/synthetic |
| 8 | Security/PII classification of real notes | Not applicable while offline/synthetic; required before any real-data phase | Security/governance team | Deferred entirely — out of scope while offline/synthetic |
| 9 | D2 gold-set target size (given actual annotation time available) | Milestone 4 statistical power | Project owner (time budget for a capstone) | Use the smaller end of the PROPOSED range (≈800 notes) and note the resulting confidence-interval width in reports |
| 10 | Whether any existing tabular forecasting code/baseline exists to reuse, or D0/arm-A must be built from scratch | Milestone 7 effort | Project owner | Assume built from scratch as part of the synthetic generator; documented as a POC-only baseline, not a real company baseline |

**Implementation update (2026-09-26):** Milestones 1–2 and the narrower
Milestone 3 rules baseline are verified (see `12-implementation-milestones.md`).
Items 1–2 remain open; the current path is regex plus supplied-mention matching,
without statistical NER or LLM. Item 3 uses a synthetic account grain; item 4
has weekly D0 observations, but forecast horizons/cutoff semantics still need
explicit experiment defaults before Milestone 5. Item 9 is the next practical
dependency: D2's 40-note provisional starter and evaluation tooling are now
implemented, but independent annotation/adjudication, a held-out set, and the
final target size still need review (docs/15). Generator truth is not gold.
Item 5 does not block running experiments; it limits the
eventual go/iterate/stop framing.
