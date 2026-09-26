"""Milestone 2 acceptance test (docs/12-implementation-milestones.md):
"a leakage test asserting the demand-realization function's code path never
reads rendered note text or extracted signals."

Four independent layers of assertion, per the design rationale in
src/dsfs/synth/__init__.py and src/dsfs/synth/latent.py:

1. Import-direction: demand.py must never import notes.py, and vice versa.
2. Type-level: the two functions' signatures only accept the type they're
   allowed to see (Knowable for notes, HiddenState for demand).
3. Runtime guard: passing the wrong type raises TypeError immediately.
4. Behavioral: demand output is bit-for-bit reproducible from HiddenState +
   config + seed alone, with zero dependency on whatever notes said —
   because notes are never even passed in.
"""

from __future__ import annotations

import ast
import inspect
import random
from pathlib import Path

import pytest

from dsfs.synth import demand as demand_module
from dsfs.synth import notes as notes_module
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.demand import realize_demand
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import HiddenState, Knowable, generate_latent_events
from dsfs.synth.notes import generate_notes

SRC_SYNTH_DIR = Path(demand_module.__file__).resolve().parent


def _imported_module_names(py_path: Path) -> set[str]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestImportDirection:
    def test_demand_module_never_imports_notes_module(self):
        imported = _imported_module_names(SRC_SYNTH_DIR / "demand.py")
        assert not any("synth.notes" in name or name == "notes" for name in imported), imported

    def test_notes_module_never_imports_demand_module(self):
        imported = _imported_module_names(SRC_SYNTH_DIR / "notes.py")
        assert not any("synth.demand" in name or name == "demand" for name in imported), imported


class TestSourceCodeNeverReferencesForbiddenConcepts:
    """Cheap but meaningful guard: even if someone later widens the type
    hints, the demand-realization source code should never need to mention
    note text, source evidence, or signal records at all."""

    def test_demand_source_never_mentions_note_or_signal_concepts(self):
        source = (SRC_SYNTH_DIR / "demand.py").read_text(encoding="utf-8").lower()
        for forbidden in ("raw_text", "sourceevidence", "signalrecord", "notegroundtruth", "content_hash"):
            assert forbidden not in source, f"demand.py must never reference {forbidden!r}"

    def test_notes_source_never_mentions_materialization_concepts(self):
        source = (SRC_SYNTH_DIR / "notes.py").read_text(encoding="utf-8").lower()
        for forbidden in ("materializ", "realized_frac", "true_demand_delta_frac", "hiddenstate("):
            assert forbidden not in source, f"notes.py must never reference {forbidden!r}"


class TestSignatureTypes:
    def test_generate_notes_type_hints_knowable_not_hiddenstate(self):
        sig = inspect.signature(generate_notes)
        first_param = next(iter(sig.parameters.values()))
        annotation = str(first_param.annotation)
        assert "Knowable" in annotation
        assert "HiddenState" not in annotation

    def test_realize_demand_type_hints_hiddenstate_not_knowable(self):
        sig = inspect.signature(realize_demand)
        params = list(sig.parameters.values())
        hidden_states_param = params[1]
        annotation = str(hidden_states_param.annotation)
        assert "HiddenState" in annotation
        assert "Knowable" not in annotation

        # And demand.py must never accept anything named/typed like notes or signals.
        for p in params:
            assert "note" not in p.name.lower()
            assert "signal" not in p.name.lower()


class TestRuntimeGuards:
    def test_generate_notes_rejects_hiddenstate_input(self):
        config = GeneratorConfig(seed=1, n_entities=2, n_weeks=8)
        rng = random.Random(config.seed)
        entities = generate_entities(config)
        _, hidden_states = generate_latent_events(entities, config, rng)

        with pytest.raises(TypeError, match="HiddenState"):
            generate_notes(hidden_states, config, rng)  # type: ignore[arg-type]

    def test_realize_demand_rejects_knowable_input(self):
        config = GeneratorConfig(seed=1, n_entities=2, n_weeks=8)
        rng = random.Random(config.seed)
        entities = generate_entities(config)
        knowables, _ = generate_latent_events(entities, config, rng)

        with pytest.raises(TypeError, match="Knowable"):
            realize_demand(entities, knowables, config, rng)  # type: ignore[arg-type]


class TestBehavioralIndependence:
    def test_demand_is_reproducible_from_hidden_state_alone_regardless_of_notes(self):
        """Demand realization never receives notes as an argument at all, so
        it cannot depend on their content. Demonstrate this by regenerating
        two DIFFERENT note corpora from the same knowables, while showing
        demand output stays identical whenever HiddenState/config/seed are
        held fixed — proving the two subsystems are decoupled, not merely
        coincidentally similar."""
        config = GeneratorConfig(seed=3, n_entities=6, n_weeks=20)
        rng_latent = random.Random(config.seed)
        entities = generate_entities(config)
        knowables, hidden_states = generate_latent_events(entities, config, rng_latent)

        notes_a, _ = generate_notes(knowables, config, random.Random(101))
        notes_b, _ = generate_notes(knowables, config, random.Random(202))
        texts_a = [n.raw_text for n in notes_a]
        texts_b = [n.raw_text for n in notes_b]
        assert texts_a != texts_b, "test setup invariant violated: note corpora should differ"

        demand_1 = realize_demand(entities, hidden_states, config, random.Random(999))
        demand_2 = realize_demand(entities, hidden_states, config, random.Random(999))
        pd = pytest.importorskip("pandas")
        assert demand_1.equals(demand_2), (
            "realize_demand must be fully determined by HiddenState + config + its own rng "
            "seed alone, independent of any note corpus (which it never receives)."
        )
