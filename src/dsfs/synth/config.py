"""Generator configuration — engineering defaults (PROPOSED), documented here
rather than assumed silently. See docs/14-open-questions.md items 3-4 and 9:
no real forecast grain/horizon/cadence exists to draw from, so this config
defines and documents its own POC-only defaults."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class GeneratorConfig(BaseModel):
    model_config = {"frozen": True}

    seed: int = 42

    # --- Entities / horizon (PROPOSED POC defaults; real grain is OPEN) ---
    n_entities: int = 40
    start_date: date = date(2023, 1, 2)  # a Monday
    n_weeks: int = 104

    # --- Baseline demand shape ---
    weekly_baseline_level_range: tuple[float, float] = (80.0, 300.0)
    weekly_trend_frac_range: tuple[float, float] = (-0.0015, 0.0025)  # per-week drift as frac of level
    seasonal_amplitude_frac: float = 0.15
    seasonal_period_weeks: int = 52
    demand_noise_frac: float = 0.08  # multiplicative noise std, as fraction of level

    # --- Latent event generation ---
    events_per_entity_per_year: float = 3.0
    knowable_lead_days_range: tuple[int, int] = (7, 90)  # how far before effective_start a note *can* appear
    effective_duration_weeks_range: tuple[int, int] = (2, 8)
    true_demand_delta_frac_range: tuple[float, float] = (0.05, 0.45)  # magnitude of hidden true impact

    # --- Note rendering ---
    notes_per_event_range: tuple[int, int] = (1, 3)
    irrelevant_note_rate: float = 0.25  # extra no-signal notes, as a fraction of event-driven note count
    reversal_probability: float = 0.2  # chance a given event later gets an explicit cancellation note
    stated_magnitude_reveal_prob: dict[str, float] = Field(
        default_factory=lambda: {
            "ASSERTED": 0.9,
            "EXPECTED": 0.7,
            "LIKELY": 0.55,
            "POSSIBLE": 0.3,
            "UNKNOWN": 0.15,
        }
    )
    ingestion_delay_minutes_range: tuple[int, int] = (5, 240)

    # --- Materialization (used only inside demand.py, never notes.py) ---
    materialization_prob_by_certainty: dict[str, float] = Field(
        default_factory=lambda: {
            "ASSERTED": 0.95,
            "EXPECTED": 0.75,
            "LIKELY": 0.55,
            "POSSIBLE": 0.30,
            "UNKNOWN": 0.50,
        }
    )
    realized_magnitude_noise_frac: float = 0.2  # noise on the true delta when an event does materialize
