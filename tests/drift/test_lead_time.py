"""End-to-end scenario evaluation (docs/10): detection + latency + calibrated
false-alert rate, always reported together, against a real generated corpus
with a known injection week."""

from __future__ import annotations

import random

from dsfs.drift.monitors import monitor_note_length, monitor_source_type_mix
from dsfs.drift.report import evaluate_scenario, render_report
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events
from dsfs.synth.notes import generate_notes


def _generate(scenario: str, inject_at_week: int, seed: int = 12):
    config = GeneratorConfig(
        seed=seed, n_entities=20, n_weeks=60,
        drift_scenario=scenario, drift_inject_at_week=inject_at_week,
    )
    rng_latent = random.Random(config.seed)
    entities = generate_entities(config)
    knowables, _ = generate_latent_events(entities, config, rng_latent)
    notes, _ = generate_notes(knowables, config, random.Random(config.seed + 1))
    return config, notes


def test_note_length_shift_is_detected_with_positive_latency():
    config, notes = _generate("note_length_shift", inject_at_week=24)
    result = evaluate_scenario(notes, config, monitor_note_length, window_weeks=4)
    assert result.detected is True
    assert result.detection_latency_weeks is not None
    assert result.detection_latency_weeks >= 0
    assert result.calibrated_false_alert_rate == result.calibrated_false_alert_rate  # not NaN


def test_no_scenario_usually_not_detected_or_reports_its_false_alert_rate():
    config, notes = _generate("none", inject_at_week=24)
    result = evaluate_scenario(notes, config, monitor_note_length, window_weeks=4)
    # Whatever the outcome, false-alert rate must always be present alongside it.
    assert result.calibrated_false_alert_rate == result.calibrated_false_alert_rate


def test_source_type_mix_shift_detected_by_its_own_monitor():
    config, notes = _generate("source_type_mix_shift", inject_at_week=20)
    result = evaluate_scenario(notes, config, monitor_source_type_mix, window_weeks=4)
    assert result.detected is True
    assert result.detection_latency_weeks is not None


def test_render_report_includes_latency_and_false_alert_rate_together():
    config, notes = _generate("note_length_shift", inject_at_week=24)
    result = evaluate_scenario(notes, config, monitor_note_length, window_weeks=4)
    report = render_report([result])
    assert "Latency" in report
    assert "false-alert rate" in report.lower()
    assert result.scenario in report
