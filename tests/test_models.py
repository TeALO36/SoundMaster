from pathlib import Path

from soundmaster.core.config import AppPaths
from soundmaster.core.models import (
    MODEL_PROFILES,
    get_profile,
    is_downloaded,
    main,
    model_directory,
    model_path,
)


def _paths(tmp_path: Path) -> AppPaths:
    data_dir = tmp_path / "data"
    return AppPaths(
        data_dir=data_dir,
        database=data_dir / "soundmaster.db",
        legal_profile=data_dir / "legal_profile.json",
        models=data_dir / "models",
        audio_cache=data_dir / "audio-cache",
        voice_samples=data_dir / "voice-samples",
        logs=data_dir / "logs",
    )


def test_public_model_profiles_have_hugging_face_repositories() -> None:
    assert {profile.key for profile in MODEL_PROFILES} == {
        "qwen3-tts",
        "qwen3-tts-tokenizer",
        "omnivoice",
    }
    assert all("/" in profile.repository for profile in MODEL_PROFILES)


def test_model_storage_can_be_overridden_by_environment(monkeypatch, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    custom = tmp_path / "large-model-disk"
    monkeypatch.setenv("SOUNDMASTER_MODEL_DIR", str(custom))

    assert model_directory(paths) == custom.resolve()


def test_download_requires_an_explicit_profile(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOUNDMASTER_DATA_DIR", str(tmp_path / "data"))

    try:
        main(["download"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("download without a profile should be rejected")


def test_model_status_is_false_until_a_snapshot_has_files(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    profile = get_profile("qwen3-tts")

    assert model_path(profile, paths) == paths.models / profile.directory_name
    assert is_downloaded(profile, paths) is False

    destination = model_path(profile, paths)
    destination.mkdir(parents=True)
    (destination / "config.json").write_text("{}", encoding="utf-8")

    assert is_downloaded(profile, paths) is True
