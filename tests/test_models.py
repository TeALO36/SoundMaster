import os
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

from soundmaster.core.config import AppPaths
from soundmaster.core.models import (
    MODEL_PROFILES,
    get_profile,
    is_downloaded,
    main,
    model_directory,
    model_path,
    set_model_directory,
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
        "qwen3-tts-0.6b",
        "qwen3-tts-tokenizer",
        "omnivoice",
        "pocket-tts",
        "f5-tts",
    }
    assert all("/" in profile.repository for profile in MODEL_PROFILES)
    assert get_profile("pocket-tts").repository == "kyutai/pocket-tts"


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


def test_download_disables_progress_bars_for_the_packaged_app(
    monkeypatch, tmp_path: Path
) -> None:
    """A download must never render huggingface_hub's tqdm progress bars.

    Regression: in the packaged windowed app ``sys.stdout``/``sys.stderr`` are
    ``None``, so tqdm crashed with "'NoneType' object has no attribute 'write'"
    and every model download failed. The env var is huggingface_hub's official
    way to disable the bars, which are useless in a GUI anyway.
    """

    from soundmaster.core.models import download_model

    seen: list[str | None] = []

    class _FakeSibling:
        def __init__(self, rfilename: str, size: int) -> None:
            self.rfilename = rfilename
            self.size = size

    class _FakeInfo:
        siblings: ClassVar[list[_FakeSibling]] = [
            _FakeSibling("config.json", 500),
            _FakeSibling("model.safetensors", 1000),
        ]

    def fake_model_info(*_args, **_kwargs) -> _FakeInfo:
        seen.append(os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"))
        return _FakeInfo()

    def fake_hf_download(*_args, **_kwargs) -> str:
        seen.append(os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS"))
        return "x"

    monkeypatch.setattr("huggingface_hub.HfApi", lambda *a, **k: SimpleNamespace(model_info=fake_model_info))
    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_hf_download)
    download_model(get_profile("qwen3-tts"), _paths(tmp_path))
    assert seen and set(seen) == {"1"}


def test_entry_point_forces_hf_progress_bars_off() -> None:
    """main.py disables the bars before anything can import huggingface_hub."""

    import importlib

    import soundmaster.main

    importlib.reload(soundmaster.main)
    assert os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] == "1"


def test_f5_profile_points_to_the_existing_repository() -> None:
    """SWAC/F5-TTS never existed on the Hub (404): the official repo is SWivid."""

    assert get_profile("f5-tts").repository == "SWivid/F5-TTS"


def test_model_directory_can_be_overridden_at_runtime(monkeypatch, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    custom = tmp_path / "D-models"

    assert model_directory(paths) == paths.models
    set_model_directory(custom)
    try:
        assert model_directory(paths) == custom.resolve()
        assert model_path(get_profile("qwen3-tts"), paths).parent == custom.resolve()
    finally:
        set_model_directory(None)
    assert model_directory(paths) == paths.models


def test_download_reports_byte_progress_per_file(monkeypatch, tmp_path: Path) -> None:
    """The download must report (downloaded, total, filename) as files land."""

    from soundmaster.core.models import download_model

    class _FakeSibling:
        def __init__(self, rfilename: str, size: int) -> None:
            self.rfilename = rfilename
            self.size = size

    class _FakeInfo:
        siblings: ClassVar[list[_FakeSibling]] = [
            _FakeSibling("config.json", 400),
            _FakeSibling("model.safetensors", 3600),
        ]

    downloaded: list[tuple[int, int, str]] = []
    monkeypatch.setattr(
        "huggingface_hub.HfApi",
        lambda *a, **k: SimpleNamespace(model_info=lambda *a2, **k2: _FakeInfo()),
    )
    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download", lambda *a, **k: str(tmp_path)
    )

    download_model(
        get_profile("qwen3-tts"),
        _paths(tmp_path),
        progress=lambda d, t, name: downloaded.append((d, t, name)),
    )

    assert downloaded == [
        (400, 4000, "config.json"),
        (4000, 4000, "model.safetensors"),
    ]
