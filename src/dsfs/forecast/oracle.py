"""Arm B oracle features: built from generator ground truth (docs/08).

These features represent the upper bound — "is there even a signal worth
extracting?" They use the generator's internal knowable state, not rendered
note text or extracted signals. PIT rules still apply: a ground-truth event
is only visible if its knowable_from <= cutoff.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dsfs.features.direction import direction_vote as _direction_from_gt
from dsfs.features.transformer import DEFAULT_STALENESS_THRESHOLD_DAYS
from dsfs.models.forecast_feature import NetDemandDirection, StalenessStatus


def build_oracle_features(
    ground_truth_path: Path,
    notes_path: Path,
    cutoffs: list[datetime],
    entities: list[str],
    *,
    horizon_days: int = 28,
    lookback_days: int = 30,
) -> pd.DataFrame:
    """Build D3-shaped oracle features from generator ground truth.

    Each ground-truth record is linked to a source_id in the notes corpus.
    PIT eligibility uses the note's available_at, not the ground truth's
    effective_start — the note is what makes the information available.
    """
    with ground_truth_path.open(encoding="utf-8") as f:
        gt_records = [json.loads(line) for line in f if line.strip()]

    with notes_path.open(encoding="utf-8") as f:
        notes_raw = [json.loads(line) for line in f if line.strip()]
    note_available_at = {}
    for note in notes_raw:
        sid = note["source_id"]
        avail = note.get("available_at")
        if avail:
            if isinstance(avail, str):
                dt = datetime.fromisoformat(avail)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                note_available_at[sid] = dt
            else:
                note_available_at[sid] = avail

    rows = []
    for cutoff in cutoffs:
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        horizon_end = cutoff + timedelta(days=horizon_days)
        lookback_start = cutoff - timedelta(days=lookback_days)

        for entity_key in entities:
            eligible = []
            for gt in gt_records:
                sid = gt["source_id"]
                avail = note_available_at.get(sid)
                if avail is None or avail > cutoff:
                    continue

                # Entity linkage must come from the generator's own ground truth,
                # never the rendered mention text (docs/08) — this is what keeps
                # the oracle arm valid even when notes use paraphrased entity
                # references (docs/16 Layer 2b).
                if gt.get("entity_key") != entity_key:
                    continue

                if gt.get("is_irrelevant", False):
                    continue

                eff_start = gt.get("effective_start")
                eff_end = gt.get("effective_end")
                if eff_start and eff_end:
                    es = datetime.fromisoformat(eff_start)
                    ee = datetime.fromisoformat(eff_end)
                    if es.tzinfo is None:
                        es = es.replace(tzinfo=timezone.utc)
                    if ee.tzinfo is None:
                        ee = ee.replace(tzinfo=timezone.utc)
                    if not (es < horizon_end and ee > cutoff):
                        continue

                eligible.append((gt, avail))

            recent = [
                (gt, avail) for gt, avail in eligible
                if avail > lookback_start
            ]

            direction_votes = [
                _direction_from_gt(gt["direction"], gt.get("negated", False))
                for gt, _ in recent
            ]
            has_up = any(v > 0 for v in direction_votes)
            has_down = any(v < 0 for v in direction_votes)
            if has_up and has_down:
                net_dir = "MIXED"
            elif sum(direction_votes) > 0:
                net_dir = "INCREASE"
            elif sum(direction_votes) < 0:
                net_dir = "DECREASE"
            elif direction_votes:
                net_dir = "STABLE"
            else:
                net_dir = "UNKNOWN"

            qty_delta = 0.0
            has_qty = False
            for gt, _ in recent:
                mag = gt.get("stated_magnitude_value")
                unit = gt.get("stated_magnitude_unit")
                if mag is not None and unit != "%":
                    vote = _direction_from_gt(gt["direction"], gt.get("negated", False))
                    qty_delta += mag * vote if vote != 0 else 0
                    has_qty = True

            latest_avail = max((a for _, a in eligible), default=None)
            days_since = None
            if latest_avail:
                days_since = max(0, int((cutoff - latest_avail).total_seconds() / 86400))

            contributing_ids = [gt["source_id"] for gt, _ in eligible]

            rows.append({
                "entity_key": entity_key,
                "forecast_cutoff": cutoff.isoformat(),
                "feature_definition_version": "oracle-v0.1.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "contributing_signal_ids": contributing_ids,
                "schema_version": "0.1.0",
                "has_active_signal_30d": len(recent) > 0,
                "signal_count_30d": len(recent),
                "net_demand_direction_30d": net_dir,
                "expected_qty_delta_next_horizon": qty_delta if has_qty else None,
                "committed_qty": None,
                "cancelled_qty_30d": None,
                "delay_count_90d": 0,
                "nearest_effective_start_days": None,
                "days_since_latest_signal": days_since,
                "independent_source_count_30d": len({gt["source_id"] for gt, _ in recent}),
                "active_conflict_count": 1 if (has_up and has_down) else 0,
                "feature_available_at": datetime.now(timezone.utc).isoformat(),
                "staleness_status": (
                    "FRESH" if days_since is not None and days_since <= DEFAULT_STALENESS_THRESHOLD_DAYS
                    else "STALE" if days_since is not None
                    else "UNKNOWN"
                ),
            })

    return pd.DataFrame(rows)
