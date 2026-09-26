"""Rolling-origin forecast experiment harness (docs/08).

Four arms, everything identical except the qualitative-signal feature input:
  A — tabular history only (baseline)
  B — oracle features from generator ground truth
  C — extracted-signal features from the extraction pipeline
  D — shuffled control (extracted signals reassigned to wrong entity/time)

Same forecast dates, same training window, same model, same hyperparameters.
Rolling-origin CV only — never a random train/test split.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

ArmLabel = Literal["A", "B", "C", "D"]


def _ridge_fit(
    X: np.ndarray, y: np.ndarray, alpha: float
) -> tuple[np.ndarray, float]:
    """Pure-numpy Ridge regression (closed-form), no sklearn dependency.

    Centers X and y, solves (X'X + alpha*I)^-1 X'y, returns (coefs, intercept).
    """
    X_mean = X.mean(axis=0)
    y_mean = y.mean()
    Xc = X - X_mean
    yc = y - y_mean
    n_features = X.shape[1]
    A = Xc.T @ Xc + alpha * np.eye(n_features)
    coefs = np.linalg.solve(A, Xc.T @ yc)
    intercept = y_mean - X_mean @ coefs
    return coefs, intercept

DEFAULT_TRAIN_WEEKS = 52
DEFAULT_HORIZON_WEEKS = 4
DEFAULT_MIN_ORIGINS = 10


@dataclass(frozen=True)
class ForecastConfig:
    """Frozen model config — identical across all arms (docs/08)."""
    train_weeks: int = DEFAULT_TRAIN_WEEKS
    horizon_weeks: int = DEFAULT_HORIZON_WEEKS
    min_origins: int = DEFAULT_MIN_ORIGINS
    ridge_alpha: float = 1.0
    lag_weeks: list[int] = field(default_factory=lambda: [1, 2, 4, 8, 13, 26])
    seasonal_period: int = 52
    random_state: int = 42


@dataclass
class OriginResult:
    """Result for one (entity, origin) forecast."""
    entity_key: str
    origin_week_index: int
    horizon_week_index: int
    actual: float
    predicted: float
    arm: ArmLabel


@dataclass
class ArmResult:
    """Aggregated results for one experiment arm."""
    arm: ArmLabel
    config: ForecastConfig
    origins: list[OriginResult] = field(default_factory=list)

    @property
    def actuals(self) -> np.ndarray:
        return np.array([o.actual for o in self.origins])

    @property
    def predictions(self) -> np.ndarray:
        return np.array([o.predicted for o in self.origins])


def _build_tabular_features(
    series: pd.Series,
    index: int,
    config: ForecastConfig,
) -> dict[str, float] | None:
    """Build lag and seasonal features from demand history up to `index` (exclusive)."""
    features = {}
    for lag in config.lag_weeks:
        pos = index - lag
        if pos < 0:
            return None
        features[f"lag_{lag}"] = float(series.iloc[pos])

    seasonal_pos = index - config.seasonal_period
    if seasonal_pos >= 0:
        features["seasonal_lag"] = float(series.iloc[seasonal_pos])
    else:
        features["seasonal_lag"] = float(series.iloc[:index].mean()) if index > 0 else 0.0

    if index >= 4:
        features["rolling_mean_4"] = float(series.iloc[index - 4:index].mean())
        features["rolling_std_4"] = float(series.iloc[index - 4:index].std(ddof=0))
    else:
        return None

    return features


def _merge_signal_features(
    tabular: dict[str, float],
    signal_features: pd.DataFrame | None,
    entity_key: str,
    cutoff_date: object,
) -> dict[str, float]:
    """Merge signal-derived features into tabular features."""
    if signal_features is None or signal_features.empty:
        return tabular

    match = signal_features[
        (signal_features["entity_key"] == entity_key)
        & (signal_features["forecast_cutoff"] == cutoff_date)
    ]
    if match.empty:
        return tabular

    row = match.iloc[0]
    signal_cols = [
        "has_active_signal_30d", "signal_count_30d",
        "expected_qty_delta_next_horizon", "committed_qty",
        "cancelled_qty_30d", "delay_count_90d",
        "nearest_effective_start_days", "days_since_latest_signal",
        "independent_source_count_30d", "active_conflict_count",
    ]
    for col in signal_cols:
        if col in row.index:
            val = row[col]
            if pd.isna(val):
                tabular[col] = 0.0
            elif isinstance(val, bool):
                tabular[col] = 1.0 if val else 0.0
            else:
                tabular[col] = float(val)

    if "net_demand_direction_30d" in row.index:
        direction = row["net_demand_direction_30d"]
        tabular["dir_increase"] = 1.0 if direction == "INCREASE" else 0.0
        tabular["dir_decrease"] = 1.0 if direction == "DECREASE" else 0.0
        tabular["dir_mixed"] = 1.0 if direction == "MIXED" else 0.0

    return tabular


def run_arm(
    d0: pd.DataFrame,
    config: ForecastConfig,
    arm: ArmLabel,
    signal_features: pd.DataFrame | None = None,
) -> ArmResult:
    """Run rolling-origin forecast for one arm.

    ``signal_features`` is a DataFrame with columns matching
    ForecastFeatureRecord fields, keyed by (entity_key, forecast_cutoff).
    Pass None for arm A (tabular-only).
    """
    result = ArmResult(arm=arm, config=config)
    entities = sorted(d0["entity_key"].unique())

    for entity_key in entities:
        entity_data = d0[d0["entity_key"] == entity_key].sort_values("week_index")
        demand = entity_data["demand"].values
        week_indices = entity_data["week_index"].values
        dates = entity_data["period_start"].values
        n = len(demand)

        demand_series = pd.Series(demand)

        first_origin = config.train_weeks
        last_origin = n - config.horizon_weeks

        if last_origin - first_origin < config.min_origins:
            continue

        for origin_idx in range(first_origin, last_origin + 1):
            train_features = []
            train_targets = []

            for t in range(config.lag_weeks[-1] + 4, origin_idx):
                feats = _build_tabular_features(demand_series, t, config)
                if feats is None:
                    continue

                if signal_features is not None and t < len(dates):
                    cutoff_date = dates[t]
                    feats = _merge_signal_features(feats, signal_features, entity_key, cutoff_date)

                train_features.append(feats)
                train_targets.append(demand[t])

            if len(train_features) < 10:
                continue

            feature_names = sorted(train_features[0].keys())
            X_train = np.array([[f.get(k, 0.0) for k in feature_names] for f in train_features])
            y_train = np.array(train_targets)

            coefs, intercept = _ridge_fit(X_train, y_train, config.ridge_alpha)

            for h in range(1, config.horizon_weeks + 1):
                target_idx = origin_idx + h
                if target_idx >= n:
                    break

                pred_feats = _build_tabular_features(demand_series, origin_idx, config)
                if pred_feats is None:
                    continue

                if signal_features is not None:
                    cutoff_date = dates[origin_idx]
                    pred_feats = _merge_signal_features(
                        pred_feats, signal_features, entity_key, cutoff_date,
                    )

                X_pred = np.array([pred_feats.get(k, 0.0) for k in feature_names])
                predicted = float(X_pred @ coefs + intercept)
                predicted = max(0.0, predicted)

                result.origins.append(OriginResult(
                    entity_key=entity_key,
                    origin_week_index=int(week_indices[origin_idx]),
                    horizon_week_index=int(week_indices[target_idx]),
                    actual=float(demand[target_idx]),
                    predicted=predicted,
                    arm=arm,
                ))

    return result


def compute_mase(actuals: np.ndarray, predictions: np.ndarray, seasonal_period: int = 1) -> float:
    """MASE: Mean Absolute Scaled Error."""
    if len(actuals) < seasonal_period + 1:
        return float("nan")
    errors = np.abs(actuals - predictions)
    naive_errors = np.abs(actuals[seasonal_period:] - actuals[:-seasonal_period])
    scale = naive_errors.mean()
    if scale == 0:
        return float("nan")
    return float(errors.mean() / scale)


def compute_mae(actuals: np.ndarray, predictions: np.ndarray) -> float:
    return float(np.abs(actuals - predictions).mean())


def compute_bias(actuals: np.ndarray, predictions: np.ndarray) -> float:
    """Signed bias: positive means over-forecasting."""
    return float((predictions - actuals).mean())


def compute_incremental_lift(baseline_error: float, enhanced_error: float) -> float:
    """Incremental error reduction as a fraction of baseline error."""
    if baseline_error == 0:
        return 0.0
    return (baseline_error - enhanced_error) / baseline_error


@dataclass
class ExperimentMetrics:
    arm: ArmLabel
    mase: float
    mae: float
    bias: float
    n_origins: int
    incremental_lift_vs_a: float | None = None


def evaluate_arm(arm_result: ArmResult, baseline_mae: float | None = None) -> ExperimentMetrics:
    actuals = arm_result.actuals
    preds = arm_result.predictions
    mae = compute_mae(actuals, preds)
    return ExperimentMetrics(
        arm=arm_result.arm,
        mase=compute_mase(actuals, preds),
        mae=mae,
        bias=compute_bias(actuals, preds),
        n_origins=len(arm_result.origins),
        incremental_lift_vs_a=compute_incremental_lift(baseline_mae, mae) if baseline_mae else None,
    )
