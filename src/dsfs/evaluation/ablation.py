"""M9 ablation matrix (docs/08): which representation of the qualitative
signal actually carries the forecast lift.

Only ablations mechanically constructible from the existing D3/oracle feature
schema are implemented. Ablations requiring feature engineering this POC
never built (business_certainty/conditionality features, aggregate-only
cross-entity features, decayed/windowed weighting, rules-vs-NER-vs-LLM
representation) are listed in NOT_IMPLEMENTED with a one-line reason each —
never fabricated. See docs/16-revised-execution-plan.md.
"""

from __future__ import annotations

import pandas as pd

from dsfs.forecast.harness import ArmResult, ForecastConfig, evaluate_arm, run_arm

# Column groups, additive: each ablation keeps its own group plus every group
# before it in the matrix (docs/08 "Signal presence only" -> "+ effective time").
_PRESENCE_COLS = ["has_active_signal_30d", "signal_count_30d"]
_DIRECTION_COLS = ["net_demand_direction_30d"]
_MAGNITUDE_COLS = ["expected_qty_delta_next_horizon", "committed_qty", "cancelled_qty_30d"]
_TIME_COLS = ["nearest_effective_start_days", "delay_count_90d", "days_since_latest_signal", "active_conflict_count"]

ABLATIONS: dict[str, list[str]] = {
    "note_count_only": ["signal_count_30d"],
    "presence_only": _PRESENCE_COLS,
    "direction": _PRESENCE_COLS + _DIRECTION_COLS,
    "magnitude": _PRESENCE_COLS + _DIRECTION_COLS + _MAGNITUDE_COLS,
    "effective_time": _PRESENCE_COLS + _DIRECTION_COLS + _MAGNITUDE_COLS + _TIME_COLS,
    "full": None,  # no masking — every column the feature store produces
}

NOT_IMPLEMENTED: dict[str, str] = {
    "business_certainty_conditionality": (
        "ForecastFeatureRecord carries no business_certainty/conditionality field; "
        "would require new feature engineering, not present in this POC's D3 schema."
    ),
    "aggregate_only_no_entity_resolution": (
        "Requires a distinct cross-entity aggregate feature set; not built in this POC."
    ),
    "rules_vs_hybrid_vs_llm": (
        "Only rules-based extraction is implemented (M3 status); NER/local-LLM stages "
        "are stubbed (extraction/llm_stage.py), so this ablation has one arm, not three."
    ),
    "decay_vs_windowed": (
        "Current features use fixed 30/90-day lookback windows, no decay weighting; "
        "a decayed variant would require changing features/transformer.py, not attempted here."
    ),
}

_ALL_MASKABLE_COLS = _PRESENCE_COLS + _DIRECTION_COLS + _MAGNITUDE_COLS + _TIME_COLS


def apply_ablation(signal_features: pd.DataFrame | None, ablation: str) -> pd.DataFrame | None:
    """Return a copy of ``signal_features`` with only the ablation's allowed
    columns populated; every other maskable column is nulled so ``run_arm``'s
    merge treats it as absent (see ``_merge_signal_features``)."""
    if signal_features is None or signal_features.empty:
        return signal_features
    if ablation not in ABLATIONS:
        raise KeyError(f"Unknown ablation {ablation!r}. Known: {sorted(ABLATIONS)}")
    allowed = ABLATIONS[ablation]
    if allowed is None:
        return signal_features
    out = signal_features.copy()
    for col in _ALL_MASKABLE_COLS:
        if col not in allowed and col in out.columns:
            out[col] = None
    return out


def run_ablation_matrix(
    d0: pd.DataFrame,
    config: ForecastConfig,
    signal_features: pd.DataFrame | None,
    *,
    arm_label: str,
    baseline_result: ArmResult,
) -> dict[str, ArmResult]:
    """Run one arm (B or C) under every implemented ablation.

    ``baseline_result`` is arm A's ArmResult, used only to compute lift in the
    caller — this function returns raw ArmResults per ablation so callers can
    apply whatever statistics (bootstrap CI, paired tests) they need.
    """
    results: dict[str, ArmResult] = {}
    for name in ABLATIONS:
        masked = apply_ablation(signal_features, name)
        results[name] = run_arm(d0, config, arm_label, signal_features=masked)
    return results


def summarize_ablation_matrix(
    ablation_results: dict[str, ArmResult], baseline_mae: float,
) -> dict[str, dict]:
    """Evaluate each ablation's ArmResult against the shared arm-A baseline MAE."""
    return {
        name: evaluate_arm(result, baseline_mae=baseline_mae).__dict__
        for name, result in ablation_results.items()
    }
