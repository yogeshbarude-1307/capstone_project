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


def normalize_cutoff_column(signal_features: pd.DataFrame) -> pd.DataFrame:
    """Normalize ``forecast_cutoff`` to a tz-naive midnight ``pd.Timestamp``.

    ``forecast_cutoff`` arrives as an ISO-8601 string from
    ``ForecastFeatureRecord.model_dump(mode="json")``; D0's ``period_start``
    is a plain ``datetime.date``. Both must go through this normalization
    (or the equivalent for D0, ``pd.to_datetime(...).dt.normalize()``)
    before being compared — see ``run_arm``.
    """
    if signal_features is None or signal_features.empty:
        return signal_features
    out = signal_features.copy()
    out["forecast_cutoff"] = (
        pd.to_datetime(out["forecast_cutoff"], utc=True).dt.tz_localize(None).dt.normalize()
    )
    return out


def _ridge_fit(
    X: np.ndarray, y: np.ndarray, alpha: float
) -> tuple[np.ndarray, float]:
    """Pure-numpy Ridge regression (closed-form), no sklearn dependency.

    Centers X and y, solves (X'X + alpha*I)^-1 X'y, returns (coefs, intercept).
    """
    X_mean = X.mean(axis=0)
    y_mean = y.mean()
    scale = X.std(axis=0)
    scale[scale == 0] = 1.0
    Xc = (X - X_mean) / scale
    yc = y - y_mean
    n_features = X.shape[1]
    A = Xc.T @ Xc + alpha * np.eye(n_features)
    coefs = np.linalg.solve(A, Xc.T @ yc) / scale
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "lag_weeks", tuple(self.lag_weeks))
        if not self.lag_weeks:
            raise ValueError("lag_weeks must not be empty")
        if any(l <= 0 for l in self.lag_weeks):
            raise ValueError(f"lag_weeks must all be positive; got {self.lag_weeks}")
        if list(self.lag_weeks) != sorted(self.lag_weeks):
            raise ValueError(
                f"lag_weeks must be sorted ascending; got {self.lag_weeks}"
            )
        if self.horizon_weeks <= 0:
            raise ValueError(f"horizon_weeks must be positive; got {self.horizon_weeks}")
        if self.train_weeks <= 0:
            raise ValueError(f"train_weeks must be positive; got {self.train_weeks}")
        if not np.isfinite(self.ridge_alpha) or self.ridge_alpha <= 0:
            raise ValueError("ridge_alpha must be finite and positive")


@dataclass
class OriginResult:
    """Result for one (entity, origin) forecast."""
    entity_key: str
    origin_week_index: int
    horizon_week_index: int
    actual: float
    predicted: float
    arm: ArmLabel
    origin_cutoff: object = None  # the forecast_cutoff used to key signal_features (docs/16 M9 segments)
    horizon_step: int = 1
    mase_scale: float | None = None


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

    ``forecast_cutoff`` arrives as an ISO-8601 string (produced by
    ``ForecastFeatureRecord.model_dump(mode="json")`` in both the feature
    store and the oracle builder), while D0's ``period_start`` is a plain
    ``datetime.date``. Both are normalized to tz-naive midnight
    ``pd.Timestamp`` once here so the per-origin merge keys actually match —
    without this, arms B/C/D silently receive zero merged signal rows and
    become numerically identical to arm A.
    """
    result = ArmResult(arm=arm, config=config)
    entities = sorted(d0["entity_key"].unique())

    signal_features = normalize_cutoff_column(signal_features)
    signal_index = {}
    if signal_features is not None and not signal_features.empty:
        for row in signal_features.to_dict("records"):
            key = (row["entity_key"], pd.Timestamp(row["forecast_cutoff"]), int(row.get("horizon_step", 0)))
            if key in signal_index:
                raise ValueError(f"Duplicate signal feature key: {key}")
            signal_index[key] = row

    for entity_key in entities:
        entity_data = d0[d0["entity_key"] == entity_key].sort_values("week_index")
        demand = entity_data["demand"].values
        week_indices = entity_data["week_index"].values
        dates = pd.to_datetime(entity_data["period_start"]).dt.normalize().values
        n = len(demand)

        demand_series = pd.Series(demand)

        first_origin = max(config.train_weeks, config.lag_weeks[-1] + 4 + 10 + config.horizon_weeks - 1)
        last_origin = n - config.horizon_weeks

        if last_origin - first_origin + 1 < config.min_origins:
            continue

        # Compute feature vectors once per account/time/horizon, not per fit.
        cache = {}
        for t in range(n):
            base = _build_tabular_features(demand_series, t, config)
            if base is None:
                continue
            for h in range(1, config.horizon_weeks + 1):
                feats = dict(base)
                row = signal_index.get((entity_key, pd.Timestamp(dates[t]), h),
                                       signal_index.get((entity_key, pd.Timestamp(dates[t]), 0)))
                if signal_features is not None:
                    if row and isinstance(row.get("tabular_features"), dict):
                        feats = dict(row["tabular_features"])
                    empty = {c: None for c in signal_features.columns if c in SIGNAL_NUMERIC_COLUMNS
                             or c in ("net_demand_direction_30d", "target_demand_direction")}
                    feats.update(numeric_signal_features(row or empty))
                cache[t, h] = feats
        for origin_idx in range(first_origin, last_origin + 1):

            # Direct multi-horizon: one ridge head per h, trained on (features_at_t,
            # demand[t+h]) pairs where both t and t+h are strictly before origin_idx —
            # never a single one-step model reused across every horizon.
            for h in range(1, config.horizon_weeks + 1):
                target_idx = origin_idx + h - 1
                if target_idx >= n:
                    break

                train_features = []
                train_targets = []

                for target_t in range(max(0, origin_idx - config.train_weeks), origin_idx):
                    t = target_t - h + 1
                    feats = cache.get((t, h))
                    if feats is None:
                        continue
                    train_features.append(feats)
                    train_targets.append(demand[target_t])

                if len(train_features) < 10:
                    continue

                if (origin_idx, h) not in cache:
                    continue
                pred_feats_base = cache[origin_idx, h]
                feature_names = sorted(train_features[0].keys())
                X_train = np.array([[f.get(k, 0.0) for k in feature_names] for f in train_features])
                y_train = np.array(train_targets)

                coefs, intercept = _ridge_fit(X_train, y_train, config.ridge_alpha)

                X_pred = np.array([pred_feats_base.get(k, 0.0) for k in feature_names])
                predicted = float(X_pred @ coefs + intercept)
                predicted = max(0.0, predicted)

                result.origins.append(OriginResult(
                    entity_key=entity_key,
                    origin_week_index=int(week_indices[origin_idx]),
                    horizon_week_index=int(week_indices[target_idx]),
                    actual=float(demand[target_idx]),
                    predicted=predicted,
                    arm=arm,
                    origin_cutoff=pd.Timestamp(dates[origin_idx]),
                    horizon_step=h,
                    mase_scale=float(np.abs(np.diff(demand[max(0, origin_idx-config.train_weeks):origin_idx])).mean()),
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
    mase_unavailable_count: int = 0


def evaluate_arm(arm_result: ArmResult, baseline_mae: float | None = None) -> ExperimentMetrics:
    if len(arm_result.origins) == 0:
        raise ValueError(
            f"Arm {arm_result.arm!r} produced zero origins — nothing to evaluate. "
            f"train_weeks/lag_weeks are likely too large relative to the dataset's "
            f"n_weeks (got train_weeks={arm_result.config.train_weeks}, "
            f"lag_weeks={arm_result.config.lag_weeks}). Silently returning NaN "
            f"metrics here would hide a config/data-size mismatch."
        )
    actuals = arm_result.actuals
    preds = arm_result.predictions
    mae = compute_mae(actuals, preds)
    return ExperimentMetrics(
        arm=arm_result.arm,
        mase=float(np.mean([abs(o.actual-o.predicted)/o.mase_scale for o in arm_result.origins
                            if o.mase_scale is not None and o.mase_scale > 0]))
             if any(o.mase_scale is not None and o.mase_scale > 0 for o in arm_result.origins) else float("nan"),
        mae=mae,
        bias=compute_bias(actuals, preds),
        n_origins=len(arm_result.origins),
        incremental_lift_vs_a=compute_incremental_lift(baseline_mae, mae) if baseline_mae else None,
        mase_unavailable_count=sum(o.mase_scale is None or o.mase_scale <= 0 for o in arm_result.origins),
    )


SIGNAL_NUMERIC_COLUMNS = (
    "has_active_signal_30d", "signal_count_30d", "expected_qty_delta_next_horizon",
    "committed_qty", "cancelled_qty_30d", "delay_count_90d", "nearest_effective_start_days",
    "days_since_latest_signal", "independent_source_count_30d", "active_conflict_count",
    "signed_pct_change", "active_demand_signal_count", "supply_signal_count", "conditional_signal_count",
    "asserted_signal_count", "expected_signal_count", "likely_signal_count", "possible_signal_count",
)


def numeric_signal_features(row: dict) -> dict[str, float]:
    out = {}
    # An absent column is intentionally absent (ablation); a null value is missing.
    for name in SIGNAL_NUMERIC_COLUMNS:
        if name not in row:
            continue
        value = row[name]
        missing = value is None or bool(pd.isna(value))
        out[name] = 0.0 if missing else float(value)
        out[name + "_missing"] = float(missing)
    for column,prefix in (("net_demand_direction_30d","dir_"),("target_demand_direction","target_dir_")):
        if column in row:
            for direction in ("INCREASE", "DECREASE", "MIXED"):
                out[prefix + direction.lower()] = float(row[column] == direction)
    return out


def paired_origins(a: ArmResult, b: ArmResult) -> tuple[list[OriginResult], list[OriginResult]]:
    def index(result):
        keys = {(o.entity_key, o.origin_week_index, o.horizon_step): o for o in result.origins}
        if len(keys) != len(result.origins):
            raise ValueError("Duplicate forecast evaluation keys")
        return keys
    left, right = index(a), index(b)
    if left.keys() != right.keys():
        raise ValueError("Forecast arms have different account/cutoff/horizon keys")
    keys = sorted(left)
    if any(left[k].actual != right[k].actual for k in keys):
        raise ValueError("Paired arms have different actual outcomes")
    return [left[k] for k in keys], [right[k] for k in keys]
