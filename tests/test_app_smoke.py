"""Import-smoke test for the Gradio app module (docs/12 UI acceptance).

Verifies the module imports without error and build_app() can be called
without launching a server — no Gradio installation required for this test
(the module guards its own import gracefully).
"""

from __future__ import annotations


def test_app_module_imports_without_error():
    import dsfs.app  # noqa: F401  — must not raise at import time


def test_build_app_raises_import_error_when_gradio_missing(monkeypatch):
    """If gradio is not installed, build_app must raise ImportError with a
    clear message — not AttributeError or a silent no-op."""
    import dsfs.app as app_mod

    monkeypatch.setattr(app_mod, "_GRADIO_AVAILABLE", False)
    monkeypatch.setattr(app_mod, "gr", None)

    import pytest
    with pytest.raises(ImportError, match="gradio"):
        app_mod.build_app()
