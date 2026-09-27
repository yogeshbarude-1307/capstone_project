"""Generator configuration — engineering defaults (PROPOSED), documented here
rather than assumed silently. See docs/14-open-questions.md items 3-4 and 9:
no real forecast grain/horizon/cadence exists to draw from, so this config
defines and documents its own POC-only defaults."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class GeneratorConfig(BaseModel):
    model_config = {"frozen": True}

    seed: int = 42

    # --- Entity mention realism (docs/16 Layer 2b) ---
    # "none" renders the canonical entity_key directly as the mention (current
    # POC default; trivially exact-match resolvable). "mild" renders a fixed
    # nickname per entity. "aggressive" additionally mixes in pronouns and
    # hierarchy references, so entity_resolution's exact-string matcher is
    # expected to abstain on most notes — this is the intended stress test,
    # not a bug to fix here.
    entity_paraphrase_mode: Literal["none", "mild", "aggressive"] = "none"

    # --- Seeded drift scenarios (docs/10, Milestone 10 D4) ---
    # Only text/metadata-level scenarios are implemented (confined to
    # notes.py); direction_class_shift and concept_drift would require
    # changing latent.py/demand.py, which are the most safety-critical,
    # leakage-tested modules in the generator, and are deliberately left
    # unimplemented rather than risking that invariant. See
    # docs/16-revised-execution-plan.md.
    drift_scenario: Literal[
        "none", "vocabulary_shift", "new_abbreviations", "source_type_mix_shift",
        "note_length_shift", "contradiction_rate_increase",
    ] = "none"
    drift_inject_at_week: int = 0

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
