"""Extraction pipeline (Milestone 3, docs/07-extraction-pipeline-design.md).

Stages, in order:

    rules.py / signal_types.py  -> deterministic direction/certainty/
                                    conditionality/negation/magnitude/time/
                                    signal-type cue detection
    entity_resolution.py        -> raw mentions -> resolved entities /
                                    forecast_key against a local master list
    llm_stage.py                -> local constrained-decoding semantic stage
                                    (OPEN, disabled by default -- see
                                    docs/14-open-questions.md item 1); the
                                    rules stage above IS the documented
                                    degradation path, not a placeholder
    extractor.py                -> orchestrates rules + entity resolution
                                    (+ llm_stage if enabled) into one
                                    SignalRecord, applying abstention where
                                    evidence is insufficient
    pipeline.py                 -> runs the extractor over a note corpus,
                                    validates every output against the
                                    canonical contract, and writes to the
                                    append-only local signal ledger
    ledger.py                   -> append-only local JSONL ledger writer

No component here ever guesses a value it cannot point to in the source
text -- see docs/07-extraction-pipeline-design.md "unsupported inference"
and the abstention-first design principle.
"""
