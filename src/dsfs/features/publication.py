"""Deterministic simulation clocks; never substitute today's wall clock."""
from datetime import datetime, timedelta
from dsfs.models.common import as_utc

FRESHNESS_TARGET_MINUTES = 60

def published_at(available_at: datetime, delay_minutes: int = 0) -> datetime:
    if delay_minutes < 0:
        raise ValueError("Publication delay cannot be negative")
    dt = as_utc(available_at)
    boundary = dt.replace(minute=0, second=0, microsecond=0)
    if boundary < dt:
        boundary += timedelta(hours=1)
    return boundary + timedelta(minutes=delay_minutes)

def publication_summary(sources, delays=None):
    import numpy as np
    delays = delays or {}
    minutes = [(published_at(s.available_at, delays.get(s.source_id, 0))-s.available_at).total_seconds()/60
               for s in sources.values()]
    return {"clock": "simulated hourly publication", "target_minutes": FRESHNESS_TARGET_MINUTES,
            "n_sources": len(minutes), "breach_count": sum(v > FRESHNESS_TARGET_MINUTES for v in minutes),
            "p50_minutes": float(np.percentile(minutes, 50)) if minutes else None,
            "p95_minutes": float(np.percentile(minutes, 95)) if minutes else None,
            "max_minutes": max(minutes, default=None)}
