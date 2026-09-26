# Demand Signal Feature Service — POC

An offline, local-only proof of concept testing whether qualitative business
notes can be turned into point-in-time-correct demand-signal features that
measurably improve a forecast versus a tabular-only baseline. See
`docs/00-development-requirements-spec.md` for the full requirements
reconciliation, and `docs/12-implementation-milestones.md` for the build
sequence.

**Everything in this repo runs locally, offline. No hosted LLM APIs, no
cloud storage, no external services.**

## Status

- **Milestone 0** (documentation package) — complete. See `docs/`.
- **Milestone 1** (POC foundation) — complete. Repo skeleton, config module,
  and the three canonical JSON Schema contracts wired into validated Pydantic
  models, with a green test suite.
- **Milestone 2** (synthetic dataset) — complete. Causally-ordered generator
  (`src/dsfs/synth/`) producing D0 (tabular demand history) and D1 (notes +
  generator-internal ground truth), with 25 tests covering leakage
  prevention, demand-distribution sanity, note-generation quality, and
  end-to-end reproducibility. Run `python -m dsfs.synth.generator` to
  (re)generate `data/raw/*`.
- **Milestone 3** (extraction pipeline) — complete. Hybrid rules + NER
  extractor (`src/dsfs/extraction/`): deterministic direction/certainty/
  conditionality/negation/magnitude/time-window/signal-type detection,
  entity resolution against a local master-entity set, and a deterministic
  validator with abstention as a first-class outcome. The local
  constrained-decoding LLM stage (`llm_stage.py`) is a real, swappable
  interface that currently raises rather than silently no-opping — it's
  disabled by default per `docs/14-open-questions.md` item 1, so
  **rules+NER is the actual, documented degradation-path extractor right
  now, not a placeholder for it**. 31 new tests, all passing (103 total),
  covering all five mandated hard cases (negation, conditional,
  future-dated, reversal, hedged uncertainty), append-only ledger
  semantics, and 100% schema conformance on the full 675-note Milestone 2
  corpus (run `python -m dsfs.extraction.pipeline`). 72 tests passing overall.

  **Caveat:** 100% schema conformance and zero REVIEW-status abstentions on
  the Milestone 2 corpus reflects a rules stage read directly off that
  corpus's own template vocabulary — it demonstrates the pipeline mechanics
  work end to end, not real extraction accuracy on held-out or paraphrased
  language. The five hard-case tests use independently-written sentences
  (not the generator's exact templates) precisely to guard against this,
  and one of them (`EV-4`, reversal) does correctly abstain into `REVIEW`.
  A genuine accuracy measurement requires the held-out D2 gold/challenge
  set from Milestone 4, kept deliberately separate per `docs/09-evaluation-
  plan.md`.
- **Milestones 4–12** — not started. See `docs/12-implementation-milestones.md`
  and `docs/14-open-questions.md`.

## Layout

```
docs/                    Pre-development spec, design docs, JSON Schema contracts
src/dsfs/                Package: config, contracts loader, Pydantic models
  models/                SourceEvidence, SignalRecord, ForecastFeatureRecord
tests/                   pytest suite (contract round-trip, business rules, config)
data/{raw,interim,processed}/   Local-only data artifacts (gitignored contents)
reports/                 Generated evaluation/drift reports (gitignored contents)
```

## Setup

```bash
pip install -r requirements.txt
pytest -q
```

`spaCy`, `transformers`/`sentence-transformers`, and forecasting libraries in
`requirements.txt` are used starting at Milestone 2+; only `pydantic`,
`pydantic-settings`, and `jsonschema` are required for the current (Milestone
1) test suite.

## Key documents to read first

1. `docs/00-development-requirements-spec.md` — what/why, reconciled from five prior research passes.
2. `docs/03-data-model.md` — the three-layer data model and the point-in-time eligibility rule (the single most important correctness constraint in the project).
3. `docs/08-forecasting-experiment-design.md` — the 4-arm experiment that answers the actual business hypothesis.
4. `docs/14-open-questions.md` — what's still unresolved and who resolves it.
