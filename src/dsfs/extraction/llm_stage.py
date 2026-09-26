"""Local constrained-decoding LLM stage -- OPEN, disabled by default.

docs/14-open-questions.md item 1: the exact local model/runtime is not yet
resolved. docs/07-extraction-pipeline-design.md documents the required
baseline for this situation: the regex + supplied-mention matching stages
(rules.py, signal_types.py, entity_resolution.py) run unconditionally and
ARE the current extraction pipeline; this stage exists as a clearly-labeled,
swappable extension point behind the same interface, gated off by
Settings.llm_extraction_enabled (default False, see dsfs/config.py).

When enabled, this stage would take over interpretation of sentence-level
semantics the rules stage cannot reliably resolve (see docs/07: harder
paraphrases of negation/conditionality/direction not covered by explicit
phrase matching) via a locally-hosted small instruction model with
JSON-schema-constrained decoding -- never a hosted API, per the confirmed
offline/local-only constraint.
"""

from __future__ import annotations

from dsfs.config import Settings


class LocalLLMUnavailableError(RuntimeError):
    """Raised when the local LLM extraction stage is invoked while disabled
    or while no local model/runtime has been configured."""


def is_llm_stage_available(settings: Settings) -> bool:
    return settings.llm_extraction_enabled and settings.local_llm_model_path is not None


def extract_with_local_llm(text: str, settings: Settings) -> dict:
    """Placeholder for the local constrained-decoding semantic stage.

    Deliberately raises rather than silently returning a guess or falling
    back without saying so -- see docs/01-poc-scope-and-non-goals.md and
    docs/07's degradation-path requirement: a disabled/unavailable stage
    must be visible, not silently absorbed.
    """
    if not is_llm_stage_available(settings):
        raise LocalLLMUnavailableError(
            "The local LLM extraction stage is disabled or unconfigured "
            "(Settings.llm_extraction_enabled=False or local_llm_model_path is unset). "
            "This is the documented Milestone 3 state: the rules baseline "
            "(dsfs.extraction.rules / dsfs.extraction.signal_types) is the actual "
            "extractor for this POC. See docs/14-open-questions.md item 1 and "
            "docs/07-extraction-pipeline-design.md 'Degradation path'."
        )
    # Not implemented: no local model/runtime has been selected yet.
    raise NotImplementedError(
        "Local constrained-decoding LLM extraction is not yet implemented. "
        "Resolve docs/14-open-questions.md item 1 first, then implement this "
        "function against the chosen local runtime (e.g. llama.cpp/ollama/"
        "transformers with JSON-schema-constrained decoding), never a hosted API."
    )
