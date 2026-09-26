"""docs/14-open-questions.md item 1 / docs/07 degradation path: the local
LLM stage must be visibly disabled, never silently skipped or faked."""

from __future__ import annotations

import pytest

from dsfs.config import Settings
from dsfs.extraction.llm_stage import LocalLLMUnavailableError, extract_with_local_llm, is_llm_stage_available


def test_llm_stage_disabled_by_default():
    settings = Settings()
    assert settings.llm_extraction_enabled is False
    assert is_llm_stage_available(settings) is False


def test_calling_disabled_llm_stage_raises_clearly():
    settings = Settings()
    with pytest.raises(LocalLLMUnavailableError, match="disabled or unconfigured"):
        extract_with_local_llm("some note text", settings)


def test_enabling_flag_without_model_path_still_unavailable():
    settings = Settings(llm_extraction_enabled=True, local_llm_model_path=None)
    assert is_llm_stage_available(settings) is False
    with pytest.raises(LocalLLMUnavailableError):
        extract_with_local_llm("some note text", settings)


def test_enabling_with_model_path_raises_not_implemented(tmp_path):
    fake_model_path = tmp_path / "fake-model.gguf"
    fake_model_path.write_text("not a real model")
    settings = Settings(llm_extraction_enabled=True, local_llm_model_path=fake_model_path)
    assert is_llm_stage_available(settings) is True
    with pytest.raises(NotImplementedError):
        extract_with_local_llm("some note text", settings)
