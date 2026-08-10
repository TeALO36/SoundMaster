"""Tests for serving Pocket TTS weights from a mirror instead of the gated repo."""

from __future__ import annotations

from pathlib import Path

import pytest

from soundmaster.core.pocket_mirror import (
    ATTRIBUTION,
    MIRROR_ENV,
    UPSTREAM_REPO,
    configured_mirror,
    is_valid_repo_id,
    mirror_config,
    rewrite_config,
)

UPSTREAM_YAML = """# sig: 709d9f84.yaml

weights_path: hf://kyutai/pocket-tts/languages/french_24l/model.safetensors@39592ff23c9e
weights_path_without_voice_cloning: hf://kyutai/pocket-tts-without-voice-cloning/languages/french_24l/model.safetensors@d29db797

flow_lm:
  lookup_table:
    tokenizer_path: hf://kyutai/pocket-tts-without-voice-cloning/languages/french_24l/tokenizer.model@d29db797
"""


def test_repo_identifiers_are_validated() -> None:
    assert is_valid_repo_id("TeALO36/pocket-tts-soundmaster") is True
    assert is_valid_repo_id("kyutai/pocket-tts") is True
    assert is_valid_repo_id("pas-de-slash") is False
    assert is_valid_repo_id("trop/de/slashs") is False
    assert is_valid_repo_id("") is False
    assert is_valid_repo_id("  ") is False
    assert is_valid_repo_id("/vide") is False


def test_only_the_gated_weights_are_redirected() -> None:
    rewritten = rewrite_config(UPSTREAM_YAML, "moi/mon-miroir")

    # The cloning weights now come from the mirror, without the pinned revision.
    assert "weights_path: hf://moi/mon-miroir/languages/french_24l/model.safetensors" in rewritten
    assert f"weights_path: hf://{UPSTREAM_REPO}/" not in rewritten

    # The fallback weights and the tokenizer already live in an ungated repo, so
    # rewriting them would point at files the mirror does not have.
    assert "weights_path_without_voice_cloning: hf://kyutai/pocket-tts-without-voice-cloning" in rewritten
    assert "tokenizer_path: hf://kyutai/pocket-tts-without-voice-cloning" in rewritten


def test_configured_mirror_prefers_preference_then_environment(monkeypatch) -> None:
    monkeypatch.delenv(MIRROR_ENV, raising=False)
    assert configured_mirror("moi/depuis-preference") == "moi/depuis-preference"

    monkeypatch.setenv(MIRROR_ENV, "moi/depuis-env")
    assert configured_mirror("") == "moi/depuis-env"
    assert configured_mirror("moi/preference") == "moi/preference"

    # An unusable value must never be forwarded to the engine.
    assert configured_mirror("pas-valide") == "moi/depuis-env"
    monkeypatch.delenv(MIRROR_ENV, raising=False)
    assert configured_mirror("pas-valide") == ""


def test_mirror_config_writes_a_usable_file(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "configs"
    source_dir.mkdir()
    (source_dir / "french_24l.yaml").write_text(UPSTREAM_YAML, encoding="utf-8")
    monkeypatch.setattr(
        "soundmaster.core.pocket_mirror.upstream_config_path",
        lambda language: source_dir / f"{language}.yaml"
        if (source_dir / f"{language}.yaml").is_file()
        else None,
    )

    destination = tmp_path / "out"
    written = mirror_config("french_24l", "moi/mon-miroir", destination)
    assert written is not None
    assert written.is_file()
    assert "hf://moi/mon-miroir/" in written.read_text(encoding="utf-8")
    # The mirror is part of the name, so switching mirrors cannot reuse a stale file.
    assert "moi__mon-miroir" in written.name

    # Rewriting is idempotent.
    again = mirror_config("french_24l", "moi/mon-miroir", destination)
    assert again == written

    # Unknown language and invalid mirror fall back to the normal path.
    assert mirror_config("klingon", "moi/mon-miroir", destination) is None
    assert mirror_config("french_24l", "pas-valide", destination) is None


def test_attribution_carries_the_licence_and_the_author() -> None:
    """CC-BY-4.0 requires the credit and the licence to travel with the copy."""

    assert "Kyutai" in ATTRIBUTION
    assert "CC-BY-4.0" in ATTRIBUTION
    assert "creativecommons.org/licenses/by/4.0" in ATTRIBUTION
    assert "huggingface.co/kyutai/pocket-tts" in ATTRIBUTION


def test_service_swaps_language_for_the_mirrored_config(tmp_path: Path, monkeypatch) -> None:
    """The engine rejects language and config together, so it must be a swap."""

    from soundmaster.core.config import AppPaths
    from soundmaster.core.tts import QwenVoiceService

    root = tmp_path / "data"
    paths = AppPaths(
        data_dir=root,
        database=root / "s.db",
        legal_profile=root / "l.json",
        models=root / "models",
        audio_cache=root / "cache",
        voice_samples=root / "voices",
        logs=root / "logs",
    )
    service = QwenVoiceService(paths)
    fake_config = tmp_path / "mirror.yaml"
    fake_config.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "soundmaster.core.tts.mirror_config", lambda *_args, **_kw: fake_config
    )

    options = service._apply_pocket_mirror(
        {"language": "french_24l", "temp": 0.7}, {"pocket_mirror": "moi/mon-miroir"}
    )
    assert "language" not in options
    assert options == {"temp": 0.7, "config": str(fake_config)}

    # No mirror configured: the language path is left exactly as it was.
    monkeypatch.delenv(MIRROR_ENV, raising=False)
    untouched = service._apply_pocket_mirror(
        {"language": "french_24l", "temp": 0.7}, {"pocket_mirror": ""}
    )
    assert untouched == {"language": "french_24l", "temp": 0.7}


def test_a_broken_mirror_never_blocks_cloning(tmp_path: Path, monkeypatch) -> None:
    from soundmaster.core.config import AppPaths
    from soundmaster.core.tts import QwenVoiceService

    root = tmp_path / "data"
    paths = AppPaths(
        data_dir=root,
        database=root / "s.db",
        legal_profile=root / "l.json",
        models=root / "models",
        audio_cache=root / "cache",
        voice_samples=root / "voices",
        logs=root / "logs",
    )
    service = QwenVoiceService(paths)

    def explode(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr("soundmaster.core.tts.mirror_config", explode)
    options = service._apply_pocket_mirror(
        {"language": "french_24l"}, {"pocket_mirror": "moi/mon-miroir"}
    )
    assert options == {"language": "french_24l"}


def test_publishing_script_credits_kyutai_and_keeps_the_use_policy() -> None:
    """The mirror replaces Kyutai's gate, so it must carry what the gate said."""

    script = Path("scripts/publier_miroir_pocket_tts.py").read_text(encoding="utf-8")
    assert "cc-by-4.0" in script
    assert "kyutai/pocket-tts" in script
    assert "consentement explicite" in script
    assert "base_model: kyutai/pocket-tts" in script


@pytest.mark.parametrize("language", ["french_24l", "english", "spanish"])
def test_rewrite_matches_the_installed_runtime_layout(language: str) -> None:
    """Against the real configs when the runtime is installed."""

    pytest.importorskip("pocket_tts")
    from soundmaster.core.pocket_mirror import upstream_config_path

    source = upstream_config_path(language)
    assert source is not None, f"{language} should ship a config"
    original = source.read_text(encoding="utf-8")
    rewritten = rewrite_config(original, "moi/mon-miroir")

    assert rewritten != original, "the gated weights path should have been redirected"
    assert "weights_path: hf://moi/mon-miroir/" in rewritten
    assert f"weights_path: hf://{UPSTREAM_REPO}/" not in rewritten
