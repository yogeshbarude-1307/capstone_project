"""Step 1-2 of the causal generation order (docs/06-synthetic-data-design.md):
generate a latent business state per entity, then split it into exactly the
two pieces the rest of the pipeline is allowed to see:

    Knowable    -> the only thing notes.py may ever read (what a plausible
                   human author could know/write about at note time).
    HiddenState -> the only thing demand.py may ever read (the true,
                   possibly-never-materializing business reality).

These are deliberately DIFFERENT TYPES, not two views of one object, so that
a function which only type-hints one of them structurally cannot accept the
other. generate_notes() and realize_demand() enforce this with an isinstance
guard at their entry point in addition to the type hints (see notes.py /
demand.py and tests/synth/test_leakage.py).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from dsfs.models.signal_record import (
    BusinessCertainty,
    Conditionality,
    Direction,
    ImpactChannel,
    SignalType,
)
from dsfs.synth.config import GeneratorConfig

_DEMAND_SIGNAL_TYPES = [
    SignalType.DEMAND_EXPECTATION,
    SignalType.PURCHASE_INTENT,
    SignalType.ORDER_LIFECYCLE,
    SignalType.QUANTITY_REVISION,
    SignalType.TIMING_REVISION,
    SignalType.INVENTORY_POSITION,
    SignalType.COMMERCIAL_EVENT,
]
_SUPPLY_SIGNAL_TYPES = [SignalType.SUPPLY_FULFILLMENT, SignalType.MARKET_CONTEXT]

_CERTAINTY_CHOICES = list(BusinessCertainty)
_DIRECTION_CHOICES = [Direction.INCREASE, Direction.DECREASE, Direction.STABLE]

_MAGNITUDE_UNITS = ["units", "%", "cases"]


@dataclass(frozen=True)
class Knowable:
    """What a plausible human author could write about at note time.

    generate_notes() reads ONLY this type. It has no field describing
    whether the event will actually materialize or what its true magnitude
    turns out to be — that lives exclusively in HiddenState.
    """

    event_id: str
    entity_key: str
    signal_type: SignalType
    direction: Direction
    business_certainty: BusinessCertainty
    conditionality: Conditionality
    condition_text: str | None
    stated_magnitude_value: float | None
    stated_magnitude_unit: str | None
    impact_channel: ImpactChannel
    knowable_from: datetime
    effective_start: datetime
    effective_end: datetime
    cancellation_at: datetime | None = None


@dataclass(frozen=True)
class HiddenState:
    """The true, hidden business reality behind a Knowable.

    realize_demand() reads ONLY this type. It has no field containing note
    text, extracted signals, or anything notes.py produced.
    """

    event_id: str
    entity_key: str
    business_certainty: BusinessCertainty  # drives materialization probability
    true_demand_delta_frac: float  # signed: positive=more demand, negative=less
    effective_start: datetime
    effective_end: datetime
    cancellation_at: datetime | None = None


def _pick_time_expression_window(
    config: GeneratorConfig, period_start: datetime, rng: random.Random
) -> tuple[datetime, datetime, datetime]:
    lead_days = rng.randint(*config.knowable_lead_days_range)
    duration_weeks = rng.randint(*config.effective_duration_weeks_range)
    effective_start = period_start + timedelta(days=lead_days)
    effective_end = effective_start + timedelta(weeks=duration_weeks)
    knowable_from = period_start
    return knowable_from, effective_start, effective_end


def generate_latent_events(
    entities: list[str], config: GeneratorConfig, rng: random.Random
) -> tuple[list[Knowable], list[HiddenState]]:
    """Generate the paired (Knowable, HiddenState) latent event set.

    Returns two lists, index-aligned by event_id, but callers downstream
    only ever receive one list or the other — see notes.py / demand.py.
    """
    knowables: list[Knowable] = []
    hidden_states: list[HiddenState] = []

    n_periods = config.n_weeks
    horizon_days = n_periods * 7
    expected_events_total = config.events_per_entity_per_year * (horizon_days / 365.0)

    event_counter = 0
    for entity_key in entities:
        n_events = max(0, round(rng.gauss(expected_events_total, max(expected_events_total * 0.3, 0.5))))
        for _ in range(n_events):
            event_counter += 1
            event_id = f"EVT-{event_counter:06d}"

            day_offset = rng.randint(0, max(horizon_days - 1, 0))
            period_start = datetime.combine(config.start_date, datetime.min.time()) + timedelta(days=day_offset)

            is_supply = rng.random() < 0.15
            signal_type = rng.choice(_SUPPLY_SIGNAL_TYPES if is_supply else _DEMAND_SIGNAL_TYPES)
            impact_channel = (
                ImpactChannel.FULFILLMENT if is_supply else ImpactChannel.DEMAND
            )

            direction = rng.choice(_DIRECTION_CHOICES)
            business_certainty = rng.choice(_CERTAINTY_CHOICES)

            conditional = rng.random() < 0.25
            conditionality = Conditionality.CONDITIONAL if conditional else Conditionality.NONE
            condition_text = (
                rng.choice(
                    [
                        "if the promotion is approved",
                        "if the new contract is signed",
                        "if inventory levels normalize",
                        "pending final budget approval",
                    ]
                )
                if conditional
                else None
            )

            true_delta = rng.uniform(*config.true_demand_delta_frac_range)
            if direction == Direction.DECREASE:
                true_delta = -true_delta
            elif direction == Direction.STABLE:
                true_delta = 0.0

            reveal_prob = config.stated_magnitude_reveal_prob.get(business_certainty.value, 0.3)
            reveal_magnitude = rng.random() < reveal_prob and direction != Direction.STABLE
            stated_magnitude_value = None
            stated_magnitude_unit = None
            if reveal_magnitude:
                # The stated magnitude is a rounded/coarser version of the
                # true hidden delta, not identical to it — real authors
                # rarely quote exact internal figures.
                stated_pct = round(abs(true_delta) * 100 / 5) * 5  # round to nearest 5%
                stated_magnitude_value = float(stated_pct)
                stated_magnitude_unit = "%"

            knowable_from, effective_start, effective_end = _pick_time_expression_window(
                config, period_start, rng
            )
            # Independent lifecycle stream: text mutations never change outcomes.
            lifecycle_rng = random.Random(f"{config.seed}:{event_id}:lifecycle")
            reversal_probability = config.reversal_probability
            if config.drift_scenario == "contradiction_rate_increase" and (
                (effective_start.date()-config.start_date).days // 7 >= config.drift_inject_at_week
            ):
                reversal_probability = min(1.0, reversal_probability * 3)
            last_cancel_day = min(21, max(1, (effective_end-effective_start).days-1))
            cancellation_at = (effective_start + timedelta(days=lifecycle_rng.randint(1, last_cancel_day))
                               if lifecycle_rng.random() < reversal_probability else None)

            knowables.append(
                Knowable(
                    event_id=event_id,
                    entity_key=entity_key,
                    signal_type=signal_type,
                    direction=direction,
                    business_certainty=business_certainty,
                    conditionality=conditionality,
                    condition_text=condition_text,
                    stated_magnitude_value=stated_magnitude_value,
                    stated_magnitude_unit=stated_magnitude_unit,
                    impact_channel=impact_channel,
                    knowable_from=knowable_from,
                    effective_start=effective_start,
                    effective_end=effective_end,
                    cancellation_at=cancellation_at,
                )
            )
            hidden_states.append(
                HiddenState(
                    event_id=event_id,
                    entity_key=entity_key,
                    business_certainty=business_certainty,
                    true_demand_delta_frac=true_delta if impact_channel == ImpactChannel.DEMAND else 0.0,
                    effective_start=effective_start,
                    effective_end=effective_end,
                    cancellation_at=cancellation_at,
                )
            )

    return knowables, hidden_states
