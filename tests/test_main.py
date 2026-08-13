"""Tests for the application entry point (Hugging Face cache relocation)."""

import os
from pathlib import Path

import pytest

from soundmaster.core.config import AppPaths
from soundmaster.main import configure_hf_environment


def _paths(tmp_path: Path) -> AppPaths:
    data = tmp_path / "data"
    return AppPaths(
        data_dir=data,
        database=data / "soundmaster.db",
        legal_profile=data / "legal.json",
        models=data / "models",
        audio_cache=data / "audio-cache",
        voice_samples=data / "voice-samples",
        logs=data / "logs",
    )


def test_hf_cache_follows_the_saved_model_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pocket TTS weight downloads must land on the user-chosen disk (e.g. D:),
    never silently on the system disk (C:) where a full drive breaks installs."""

    from soundmaster.data.library import SoundLibrary

    paths = _paths(tmp_path)
    chosen = tmp_path / "models-on-d"
    SoundLibrary(paths.database).set_preference("model_directory", str(chosen))

    cache = configure_hf_environment(paths)

    assert cache == chosen / "hf-cache"
    assert os.environ["HF_HUB_CACHE"] == str(chosen / "hf-cache")
    # The login-token location (HF_HOME) must stay untouched.
    assert "HF_HOME" not in os.environ


def test_hf_cache_defaults_to_the_models_directory(tmp_path: Path) -> None:
    """Without a saved choice, the cache follows the default model directory."""

    paths = _paths(tmp_path)

    cache = configure_hf_environment(paths, auto_select=False)

    assert cache == paths.models / "hf-cache"
    assert os.environ["HF_HUB_CACHE"] == str(paths.models / "hf-cache")


def test_hf_cache_never_overrides_an_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A power user's own HF_HUB_CACHE stays authoritative."""

    paths = _paths(tmp_path)
    monkeypatch.setenv("HF_HUB_CACHE", "D:\\my-own-hf-cache")

    configure_hf_environment(paths, auto_select=False)

    assert os.environ["HF_HUB_CACHE"] == "D:\\my-own-hf-cache"


def test_model_directory_change_redirects_the_live_hub_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing the model folder mid-session must move future Pocket TTS weight
    downloads immediately — and resetting restores the startup default."""

    from soundmaster.core.models import set_model_directory

    paths = _paths(tmp_path)
    configure_hf_environment(paths, auto_select=False)  # records paths/models/hf-cache
    chosen = tmp_path / "models-on-d"

    set_model_directory(chosen)

    assert os.environ["HF_HUB_CACHE"] == str(chosen / "hf-cache")
    # Once huggingface_hub is loaded its constants are read live by
    # hf_hub_download/scan_cache_dir — they must be patched too.
    import huggingface_hub.constants as hf_constants

    assert hf_constants.HF_HUB_CACHE == str(chosen / "hf-cache")

    set_model_directory(None)

    assert os.environ["HF_HUB_CACHE"] == str(paths.models / "hf-cache")
    assert hf_constants.HF_HUB_CACHE == str(paths.models / "hf-cache")


def test_auto_selects_another_drive_when_the_system_disk_is_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nearly full system disk must not break first-run installs: the app
    falls back to the largest other local drive (e.g. D:)."""

    from types import SimpleNamespace

    import soundmaster.main as main_mod

    paths = _paths(tmp_path)
    default_anchor = str(paths.models.anchor)

    def fake_disk_usage(path: object) -> SimpleNamespace:
        if str(path).startswith(default_anchor):
            return SimpleNamespace(free=500 * 1024**2)  # 0.5 GiB — too small
        return SimpleNamespace(free=120 * 1024**3)  # 120 GiB — plenty

    # All drives are local: the pick is purely the largest free space.
    monkeypatch.setattr(main_mod, "_is_local_fixed_drive", lambda root: True)
    monkeypatch.setattr(main_mod.shutil, "disk_usage", fake_disk_usage)

    expected: Path | None = None
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:\\")
        if root.exists() and root.anchor != paths.models.anchor and expected is None:
            expected = root / "SoundMaster-models"

    assert main_mod._auto_model_directory(paths) == expected


def test_auto_select_never_picks_a_network_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Network drives (Freebox NAS, Google Drive, …) must never be chosen.

    Regression: on a machine with a mapped NAS, the picker chose the network
    share (DriveType 4, huge free space) instead of the local NVMe (D:),
    sending multi-gigabyte model downloads over the LAN. The NAS advertises
    much more free space than the local disk, yet the local disk wins.
    """

    from types import SimpleNamespace

    import soundmaster.main as main_mod

    paths = _paths(tmp_path)
    default_anchor = str(paths.models.anchor)

    def fake_disk_usage(path: object) -> SimpleNamespace:
        if str(path).startswith(default_anchor):
            return SimpleNamespace(free=500 * 1024**2)  # 0.5 GiB — too small
        if str(path).startswith("E:"):
            return SimpleNamespace(free=500 * 1024**3)  # NAS: 500 GiB
        return SimpleNamespace(free=50 * 1024**3)  # local: 50 GiB

    monkeypatch.setattr(main_mod.shutil, "disk_usage", fake_disk_usage)

    def fake_exists(path: object) -> bool:
        text = str(path)
        # Only D: (local) and E: (NAS) exist besides the default anchor.
        return text.startswith(("D:\\", "E:\\"))

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(main_mod, "_is_local_fixed_drive", lambda root: not str(root).startswith("E:"))

    result = main_mod._auto_model_directory(paths)

    # The NAS (E:, 500 GiB) must lose to the local disk (D:, 50 GiB).
    assert result is not None
    assert str(result).startswith("D:\\")


def test_configure_auto_persists_the_choice_when_disk_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The auto-selected folder is persisted so later sessions reuse it."""

    from types import SimpleNamespace

    import soundmaster.main as main_mod
    from soundmaster.data.library import SoundLibrary

    paths = _paths(tmp_path)
    default_anchor = str(paths.models.anchor)

    def fake_disk_usage(path: object) -> SimpleNamespace:
        if str(path).startswith(default_anchor):
            return SimpleNamespace(free=500 * 1024**2)
        return SimpleNamespace(free=120 * 1024**3)

    monkeypatch.setattr(main_mod.shutil, "disk_usage", fake_disk_usage)

    cache = main_mod.configure_hf_environment(paths)

    saved = SoundLibrary(paths.database).preference("model_directory", "")
    assert saved, "the auto-selected folder must be remembered"
    assert cache == Path(saved) / "hf-cache"
    assert os.environ["HF_HUB_CACHE"] == str(cache)


def test_a_sleeping_network_drive_is_never_probed(monkeypatch, tmp_path) -> None:
    """Regression: startup could freeze for the whole SMB timeout.

    The drive scan called ``exists()`` before asking Windows what kind of drive
    it was, so a mapped-but-asleep NAS was touched — and blocked — even though
    it was rejected as a network share on the very next line.
    """

    import shutil

    from soundmaster import main as main_module

    touched: list[str] = []

    real_exists = Path.exists

    def spying_exists(self):
        touched.append(str(self))
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", spying_exists)
    # Everything looks like a network share: nothing may be probed at all.
    monkeypatch.setattr(main_module, "_is_local_fixed_drive", lambda _root: False)
    monkeypatch.setattr(
        shutil, "disk_usage", lambda _p: shutil._ntuple_diskusage(1, 1, 0)
    )

    paths = _paths(tmp_path)
    assert main_module._auto_model_directory(paths) is None
    assert not any(item.endswith(":\\") for item in touched), touched
