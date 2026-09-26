"""Synthetic entity generation.

Forecast grain is OPEN (docs/14-open-questions.md item 3) — no real business
grain is available. This POC defines its own engineering-default grain: one
entity_key per synthetic account, documented explicitly as a stand-in rather
than assumed to represent any real company's hierarchy.
"""

from __future__ import annotations

from dsfs.synth.config import GeneratorConfig


def generate_entities(config: GeneratorConfig) -> list[str]:
    return [f"CUST-{i:04d}" for i in range(1, config.n_entities + 1)]
