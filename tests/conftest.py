"""Shared pytest fixtures.

The model-directory override and the Hugging Face cache location are module
globals mutated by the code under test (``set_model_directory``,
``configure_hf_environment``). Without an autouse reset applied to *every*
module, a test in one file leaves the override pointing at a real drive and the
next file (e.g. test_tts.py) resolves models to the wrong location.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_model_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts from a clean model-directory override and environment."""

    from soundmaster.core.models import record_hf_cache_default, set_model_directory

    set_model_directory(None)
    record_hf_cache_default(None)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("SOUNDMASTER_MODEL_DIR", raising=False)
    # Non-UTF-8 console output in tests (French accents on Windows CI).
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
