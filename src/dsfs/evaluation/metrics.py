"""Extraction metrics with explicit denominators and per-source diagnostics.

No forecast data, generator truth, or extraction rules enter this module.
Missing outputs are errors; duplicate outputs are never cherry-picked.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from dsfs.contracts import ContractValidationError, validate_record
from dsfs.evaluation.annotations import FIELDS, AnnotatedCase, asserted
from dsfs.models import Conditionality, SignalRecord, SignalType, ValidationStatus

if TYPE_CHECKING:
    from dsfs.extraction.pipeline import QuarantinedRecord

MISSING = "__MISSING__"
ERROR_TYPES = (
    "false_event", "missed_event", "wrong_type", "wrong_entity", "wrong_direction",
    "wrong_magnitude", "wrong_timing", "negation_error", "conditionality_error",
    "duplicate", "missed_supersession_stale_signal", "unsupported_inference",
)


@dataclass(frozen=True)
class MetricConfig:
    magnitude_absolute_tolerance: float = 1e-6
    magnitude_relative_tolerance: float = 0.0

    def __post_init__(self):
        for value in (self.magnitude_absolute_tolerance, self.magnitude_relative_tolerance):
            if not math.isfinite(value) or value < 0:
                raise ValueError("Magnitude tolerances must be finite and nonnegative")


def ratio(numerator: int | float, denominator: int) -> dict:
    return {"value": numerator / denominator if denominator else None,
            "numerator": numerator, "denominator": denominator}


def precision_recall(tp: int, fp: int, fn: int) -> dict:
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
            "f1": ratio(2 * tp, 2 * tp + fp + fn)}


def classification(pairs: list[tuple[str, str]], labels: list[str] | None = None) -> dict:
    labels = labels if labels is not None else sorted({v for pair in pairs for v in pair} - {MISSING})
    per_class = {}
    for label in labels:
        tp = sum(g == label and p == label for g, p in pairs)
        fp = sum(g != label and p == label for g, p in pairs)
        fn = sum(g == label and p != label for g, p in pairs)
        per_class[label] = precision_recall(tp, fp, fn)
    f1s = [m["f1"]["value"] for m in per_class.values() if m["f1"]["value"] is not None]
    return {"accuracy": ratio(sum(g == p for g, p in pairs), len(pairs)),
            "macro_f1": ratio(sum(f1s), len(f1s)), "per_class": per_class}


def decision(record: SignalRecord | None) -> str:
    if record is None:
        return MISSING
    if record.validation_status != ValidationStatus.PASS:
        return "REVIEW" if record.validation_status == ValidationStatus.REVIEW else "FAIL"
    return "NO_SIGNAL" if record.signal_type == SignalType.NO_SIGNAL else "PASS"


def matches(field: str, expected: object, actual: object, config: MetricConfig) -> bool:
    if actual == MISSING:
        return False
    if field == "magnitude_value" and expected is not None and actual is not None:
        return math.isclose(expected, actual, abs_tol=config.magnitude_absolute_tolerance,
                            rel_tol=config.magnitude_relative_tolerance)
    return expected == actual


def interval_iou(case: AnnotatedCase, record: SignalRecord | None) -> float:
    g_start, g_end = case.expected.effective_start, case.expected.effective_end
    if record is None or record.effective_start is None or record.effective_end is None:
        return 0.0
    p_start, p_end = record.effective_start, record.effective_end
    intersection = max(0.0, (min(g_end, p_end) - max(g_start, p_start)).total_seconds())
    union = max((max(g_end, p_end) - min(g_start, p_start)).total_seconds(), 0.0)
    return intersection / union if union else 0.0


def evaluate(
    cases: list[AnnotatedCase],
    predictions: list[SignalRecord],
    quarantined: list[QuarantinedRecord] | None = None,
    config: MetricConfig | None = None,
    source_by_signal_id: dict[str, str] | None = None,
) -> dict:
    """Score one split/sample cohort. Provisional/human cohorts are separated by the runner."""
    config = config or MetricConfig()
    quarantined = quarantined or []
    sources = {c.evidence.source_id: c for c in cases}
    if len(sources) != len(cases):
        raise ValueError("Duplicate annotation source IDs")
    run_ids = {p.extraction_run_id for p in predictions} | {q.extraction_run_id for q in quarantined}
    if len(run_ids) > 1:
        raise ValueError("Evaluate one extraction run at a time")
    by_source = defaultdict(list)
    failures = Counter(q.stage for q in quarantined)
    cross_field_failures = 0
    schema_valid = 0
    for q in quarantined:
        if q.source_id not in sources:
            raise ValueError("Quarantine source has no D2 annotation")
    for prediction in predictions:
        if prediction.source_id not in sources:
            raise ValueError("Prediction source has no D2 annotation")
        by_source[prediction.source_id].append(prediction)
        try:
            dumped = prediction.model_dump(mode="json")
            validate_record("signal_record", dumped)
            schema_valid += 1
            validated = SignalRecord.model_validate(dumped)
        except ContractValidationError:
            failures["contract"] += 1
        except ValidationError:
            failures["construct"] += 1
            cross_field_failures += 1
        else:
            if validated.source_revision != sources[validated.source_id].evidence.source_revision:
                failures["lineage"] += 1
            else:
                by_source[prediction.source_id][-1] = validated
                continue
        # Preserve output count, but never score malformed rows as successful interpretations.
        by_source[prediction.source_id][-1] = None

    signal_sources = source_by_signal_id or {p.signal_id: p.source_id for p in predictions}
    fields = {name: Counter() for name in FIELDS}
    taxonomy = Counter({name: 0 for name in ERROR_TYPES})
    diagnostics, type_pairs, direction_pairs, decision_pairs, event_pairs = [], [], [], [], []
    negation_pairs, conditional_pairs = [], []
    grounding_count = unsupported_count = span_count = covered_count = 0
    interval_scores = []
    interval_exact = []
    entity_resolvable, entity_unresolved = [], []
    by_reason = defaultdict(list)
    missing_count = duplicate_count = 0

    for case in cases:
        source_id = case.evidence.source_id
        outputs = by_source[source_id]
        prediction = outputs[0] if len(outputs) == 1 else None
        if not outputs:
            missing_count += 1
        duplicate_count += max(0, len(outputs) - 1)
        predicted_decision = decision(prediction)
        decision_pairs.append((case.expected.decision, predicted_decision))
        if case.expected.abstention_reason:
            by_reason[case.expected.abstention_reason].append(predicted_decision == case.expected.decision)
        gold_event = case.expected.signal_type.value if case.expected.decision == "PASS" else MISSING
        pred_event = prediction.signal_type.value if predicted_decision == "PASS" else MISSING
        if "signal_type" in case.scored_fields:
            event_pairs.append((gold_event, pred_event))
        # Every duplicate actionable output is an extra false positive, while the
        # original annotated event above remains a miss (no arbitrary best match).
        if len(outputs) > 1 and "signal_type" in case.scored_fields:
            event_pairs.extend((MISSING, p.signal_type.value) for p in outputs if decision(p) == "PASS")
        if "signal_type" in case.scored_fields:
            type_pairs.append((case.expected.signal_type.value, prediction.signal_type.value if prediction else MISSING))
        if "direction" in case.scored_fields:
            direction_pairs.append((case.expected.direction.value, prediction.direction.value if prediction else MISSING))
        if "negation" in case.tags and "negated" in case.scored_fields:
            negation_pairs.append((str(case.expected.negated), str(prediction.negated) if prediction else MISSING))
        if "conditional" in case.tags and "conditionality" in case.scored_fields:
            conditional_pairs.append((case.expected.conditionality.value,
                                      prediction.conditionality.value if prediction else MISSING))

        wrong_fields, unsupported_fields = [], []
        ref = prediction.evidence_ref if prediction else None
        valid_span = bool(ref and ref.source_id == source_id and prediction.source_revision == case.evidence.source_revision
                          and 0 <= ref.char_start < ref.char_end <= len(case.evidence.raw_text))
        for name in case.scored_fields:
            expected = getattr(case.expected, name)
            if prediction is None:
                actual = MISSING
            elif name == "supersedes_source_id":
                actual = signal_sources.get(prediction.supersedes_signal_id, MISSING) if prediction.supersedes_signal_id else None
            else:
                actual = getattr(prediction, name)
            correct = matches(name, expected, actual, config)
            counts = fields[name]
            counts["n"] += 1
            counts["correct"] += correct
            gold_positive = asserted(expected)
            pred_positive = actual != MISSING and asserted(actual)
            counts["tp"] += gold_positive and pred_positive and correct
            counts["fp"] += pred_positive and not (gold_positive and correct)
            counts["fn"] += gold_positive and not (pred_positive and correct)
            if not correct:
                wrong_fields.append(name)
            if name == "supersedes_source_id":
                continue
            spans = case.field_evidence.get(name, [])
            covered = bool(valid_span and spans and all(
                ref.char_start <= span.char_start and ref.char_end >= span.char_end for span in spans
            ))
            if spans:
                span_count += 1
                covered_count += covered
            if pred_positive:
                grounding_count += 1
                # Operational annotation-relative definition: matching asserted value
                # AND a citation covering its annotated support. Broad spans alone
                # cannot make a wrong value "grounded".
                if not (correct and covered):
                    unsupported_count += 1
                    unsupported_fields.append(name)

        if {"effective_start", "effective_end"}.issubset(case.scored_fields):
            if case.expected.effective_start and case.expected.effective_end:
                interval_scores.append(interval_iou(case, prediction))
                interval_exact.append(not ({"effective_start", "effective_end"} & set(wrong_fields)))
        if "forecast_key" in case.scored_fields:
            result = "forecast_key" not in wrong_fields
            (entity_resolvable if case.expected.forecast_key else entity_unresolved).append(result)

        errors = set()
        if "signal_type" in case.scored_fields and gold_event == MISSING and pred_event != MISSING:
            errors.add("false_event")
        if "signal_type" in case.scored_fields and gold_event != MISSING and pred_event == MISSING:
            errors.add("missed_event")
        mapping = {
            "signal_type": "wrong_type", "forecast_key": "wrong_entity",
            "direction": "wrong_direction", "magnitude_value": "wrong_magnitude",
            "magnitude_unit": "wrong_magnitude", "effective_start": "wrong_timing",
            "effective_end": "wrong_timing", "negated": "negation_error",
            "conditionality": "conditionality_error", "condition_text": "conditionality_error",
            "supersedes_source_id": "missed_supersession_stale_signal",
        }
        errors.update(mapping[f] for f in wrong_fields if f in mapping)
        if len(outputs) > 1:
            errors.add("duplicate")
        if unsupported_fields:
            errors.add("unsupported_inference")
        taxonomy.update(errors)
        if errors or predicted_decision != case.expected.decision or wrong_fields:
            diagnostics.append({"source_id": source_id, "expected_decision": case.expected.decision,
                                "predicted_decision": predicted_decision, "field_errors": wrong_fields,
                                "unsupported_fields": unsupported_fields, "error_types": sorted(errors)})

    abstention_pairs = [("ABSTAIN" if g != "PASS" else "PASS",
                         "ABSTAIN" if p in ("NO_SIGNAL", "REVIEW") else p) for g, p in decision_pairs]
    # A missing/failed prediction is not credited as a deliberate abstention.
    attempts = len(predictions) + len(quarantined)
    event_labels = [t.value for t in SignalType if t != SignalType.NO_SIGNAL]
    return {
        "n_notes": len(cases), "n_output_attempts": attempts,
        "missing_output_count": missing_count, "duplicate_output_count": duplicate_count,
        "schema_valid_record_rate": ratio(schema_valid, attempts),
        "model_validation_failure_rate": ratio(failures["construct"], attempts),
        "semantic_cross_field_failure_rate": ratio(cross_field_failures, schema_valid),
        "unclassified_construction_failure_count": sum(q.stage == "construct" for q in quarantined),
        "schema_failure_rate": ratio(failures["contract"], attempts),
        "lineage_failure_rate": ratio(failures["lineage"], attempts),
        "actionable_event_detection": classification(event_pairs, event_labels),
        "signal_type": classification(type_pairs), "direction": classification(direction_pairs),
        "fields": {name: {"accuracy": ratio(c["correct"], c["n"]), **precision_recall(c["tp"], c["fp"], c["fn"])}
                   for name, c in fields.items()},
        "negation_subset": classification(negation_pairs, ["True", "False"]),
        "conditional_subset": classification(conditional_pairs, [v.value for v in Conditionality]),
        "temporal": {"exact_match": ratio(sum(interval_exact), len(interval_exact)),
                     "mean_interval_iou": ratio(sum(interval_scores), len(interval_scores))},
        "entity": {"resolvable_accuracy": ratio(sum(entity_resolvable), len(entity_resolvable)),
                   "correct_unresolved_rate": ratio(sum(entity_unresolved), len(entity_unresolved))},
        "abstention": classification(abstention_pairs, ["ABSTAIN"])["per_class"]["ABSTAIN"],
        "abstention_decision": classification(decision_pairs, ["PASS", "NO_SIGNAL", "REVIEW"]),
        "abstention_reason_breakdown": {reason: ratio(sum(values), len(values)) for reason, values in sorted(by_reason.items())},
        "grounding": {"evidence_span_coverage": ratio(covered_count, span_count),
                      "unsupported_inference_rate": ratio(unsupported_count, grounding_count)},
        "error_taxonomy": dict(taxonomy), "errors": diagnostics,
    }
