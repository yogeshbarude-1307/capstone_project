"""Decision report must always emit B/C comparison, even when D-lift triggers a leakage warning."""

from __future__ import annotations

from dsfs.forecast.harness import ExperimentMetrics, ForecastConfig
from dsfs.forecast.pipeline import _format_report


def _m(arm: str, mae: float, lift: float | None = None) -> ExperimentMetrics:
    return ExperimentMetrics(arm=arm, mase=mae / 100, mae=mae, bias=0.0, n_origins=10,
                             incremental_lift_vs_a=lift)


def test_d_lift_warning_does_not_suppress_bc_findings():
    """When D-lift > threshold, leakage warning must appear AND B/C branch must still be evaluated."""
    results = {
        "A": _m("A", 100.0),
        "B": _m("B", 80.0, lift=0.20),   # B > A by 20%
        "C": _m("C", 85.0, lift=0.15),   # C retains most of B's lift
        "D": _m("D", 90.0, lift=0.10),   # D lift > 0.02 → leakage warning
    }
    report = _format_report(results, ForecastConfig())
    assert "LEAKAGE WARNING" in report
    assert "retains" in report or "bottleneck" in report or "no forecastable" in report


def test_b_flat_reports_no_signal_branch():
    results = {
        "A": _m("A", 100.0),
        "B": _m("B", 100.0, lift=0.0),
        "C": _m("C", 100.0, lift=0.0),
        "D": _m("D", 100.0, lift=0.0),
    }
    report = _format_report(results, ForecastConfig())
    assert "no forecastable" in report or "B ≈ A" in report


def test_c_lags_b_reports_bottleneck_branch():
    results = {
        "A": _m("A", 100.0),
        "B": _m("B", 70.0, lift=0.30),
        "C": _m("C", 99.7, lift=0.003),
        "D": _m("D", 100.0, lift=0.0),
    }
    report = _format_report(results, ForecastConfig())
    assert "bottleneck" in report or "B > A but C" in report


def test_mandatory_caveat_present_verbatim():
    results = {
        "A": _m("A", 100.0),
        "B": _m("B", 80.0, lift=0.2),
        "C": _m("C", 85.0, lift=0.15),
        "D": _m("D", 100.0, lift=0.0),
    }
    report = _format_report(results, ForecastConfig())
    assert "does **not** demonstrate that" in report
    assert "Real-data validation" in report
