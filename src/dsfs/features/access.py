"""Feature access layer: get_features / get_historical_features.

Implements the callable Python interface from docs/04-api-data-contracts.md.
No network service — a stable, typed, versioned Python function that any
local process (notebook, script, test, forecast harness) can call.

Raw note text is never returned (docs/03, docs/04).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dsfs.contracts import validate_record
from dsfs.models.common import as_utc
from dsfs.models.forecast_feature import ForecastFeatureRecord
from dsfs.models.signal_record import SignalRecord
from dsfs.models.source_evidence import SourceEvidence
from dsfs.extraction.ledger import read_ledger, ledger_as_of
from dsfs.features.transformer import (
    DEFAULT_FEATURE_DEFINITION_VERSION,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_STALENESS_THRESHOLD_DAYS,
    CutoffSpec,
    build_feature_row,
    select_eligible_signals,
)


@dataclass
class FeatureBatchResponse:
    """Batch feature retrieval result with lineage metadata."""
    features: list[ForecastFeatureRecord] = field(default_factory=list)
    feature_definition_version: str = DEFAULT_FEATURE_DEFINITION_VERSION
    errors: list[str] = field(default_factory=list)


class FeatureStore:
    """In-memory feature store backed by signal ledger + source evidence.

    Holds the pre-loaded signals and sources for a single extraction run,
    providing get_features / get_historical_features against that snapshot.
    """

    def __init__(
        self,
        signals: list[SignalRecord],
        sources: dict[str, SourceEvidence],
        *,
        feature_definition_version: str = DEFAULT_FEATURE_DEFINITION_VERSION,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        staleness_threshold_days: int = DEFAULT_STALENESS_THRESHOLD_DAYS,
    ):
        self._signals = signals
        self._sources = sources
        self._source_available_at = {
            sid: src.available_at for sid, src in sources.items()
        }
        self._fdv = feature_definition_version
        self._horizon_days = horizon_days
        self._lookback_days = lookback_days
        self._staleness_threshold_days = staleness_threshold_days

    def _as_of(self, cutoff):
        runs = {s.extraction_run_id for s in self._signals}
        if len(runs) > 1:
            raise ValueError("Feature store must select one extraction run")
        if not runs:
            return []
        return ledger_as_of(self._signals, self._sources, cutoff, extraction_run_id=next(iter(runs)))

    def get_features(
        self,
        entity_keys: list[str],
        forecast_cutoff: datetime,
        feature_set_version: str | None = None,
    ) -> FeatureBatchResponse:
        """Batch point-in-time feature retrieval.

        Returns feature values plus lineage metadata. Never returns raw text.
        """
        cutoff = as_utc(forecast_cutoff)
        fdv = feature_set_version or self._fdv
        now = datetime.now(timezone.utc)
        response = FeatureBatchResponse(feature_definition_version=fdv)

        for entity_key in entity_keys:
            eligible = select_eligible_signals(
                self._as_of(cutoff),
                entity_key,
                cutoff,
                self._source_available_at,
                horizon_days=self._horizon_days,
            )
            row = build_feature_row(
                entity_key,
                cutoff,
                eligible,
                self._source_available_at,
                generated_at=now,
                feature_definition_version=fdv,
                lookback_days=self._lookback_days,
                horizon_days=self._horizon_days,
                staleness_threshold_days=self._staleness_threshold_days,
            )
            response.features.append(row)

        return response

    def get_historical_features(
        self,
        entity_cutoff_pairs: list[tuple[str, datetime]],
        feature_set_version: str | None = None,
    ) -> pd.DataFrame:
        """Reconstruct the feature table as it would have existed at each
        (entity, cutoff) pair, applying the PIT eligibility rule.

        This is the function the forecasting experiment harness calls to build
        arms B/C/D training data — it must never return a row whose
        contributing signal has available_at > cutoff.
        """
        fdv = feature_set_version or self._fdv
        now = datetime.now(timezone.utc)
        rows = []
        for entity_key, cutoff in entity_cutoff_pairs:
            cutoff = as_utc(cutoff)
            eligible = select_eligible_signals(
                self._as_of(cutoff),
                entity_key,
                cutoff,
                self._source_available_at,
                horizon_days=self._horizon_days,
            )
            row = build_feature_row(
                entity_key,
                cutoff,
                eligible,
                self._source_available_at,
                generated_at=now,
                feature_definition_version=fdv,
                lookback_days=self._lookback_days,
                horizon_days=self._horizon_days,
                staleness_threshold_days=self._staleness_threshold_days,
            )
            rows.append(row.model_dump(mode="json"))

        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)


def load_feature_store(
    ledger_path: Path,
    notes_path: Path,
    *,
    extraction_run_id: str,
    feature_definition_version: str = DEFAULT_FEATURE_DEFINITION_VERSION,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    staleness_threshold_days: int = DEFAULT_STALENESS_THRESHOLD_DAYS,
) -> FeatureStore:
    """Load a FeatureStore from persisted ledger and note corpus.

    Requires an explicit extraction_run_id so the caller selects which
    extraction snapshot to build features from (docs/07 versioning discipline).
    """
    raw_records = read_ledger(ledger_path)
    all_signals = [SignalRecord.model_validate(r) for r in raw_records]

    with notes_path.open(encoding="utf-8") as f:
        all_sources_list = [
            SourceEvidence.model_validate_json(line) for line in f if line.strip()
        ]
    sources = {s.source_id: s for s in all_sources_list}

    run_signals = [s for s in all_signals if s.extraction_run_id == extraction_run_id]

    return FeatureStore(
        run_signals,
        sources,
        feature_definition_version=feature_definition_version,
        horizon_days=horizon_days,
        lookback_days=lookback_days,
        staleness_threshold_days=staleness_threshold_days,
    )
