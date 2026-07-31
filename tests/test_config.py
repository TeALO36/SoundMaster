from pathlib import Path

from soundmaster.core.config import AppConfig, AppPaths, load_config


def test_default_config_is_ready_for_alt_number_favorites() -> None:
    config = AppConfig()

    assert config.favorite_limit == 10
    assert config.minimize_to_tray is True


def test_paths_use_soundmaster_data_dir_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOUNDMASTER_DATA_DIR", str(tmp_path / "profile"))

    _, paths = load_config()

    assert paths.data_dir == (tmp_path / "profile").resolve()
    assert paths.database == paths.data_dir / "soundmaster.db"
    assert paths.legal_profile == paths.data_dir / "legal_profile.json"
    assert paths.models == paths.data_dir / "models"
    assert paths.audio_cache == paths.data_dir / "audio-cache"
    assert paths.voice_samples == paths.data_dir / "voice-samples"
    assert paths.logs == paths.data_dir / "logs"


def test_runtime_directories_are_created_explicitly(tmp_path: Path) -> None:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "soundmaster.db",
        legal_profile=tmp_path / "data" / "legal_profile.json",
        models=tmp_path / "data" / "models",
        audio_cache=tmp_path / "data" / "audio-cache",
        voice_samples=tmp_path / "data" / "voice-samples",
        logs=tmp_path / "data" / "logs",
    )

    paths.ensure_runtime_directories()

    assert paths.data_dir.is_dir()
    assert paths.models.is_dir()
    assert paths.audio_cache.is_dir()
    assert paths.voice_samples.is_dir()
    assert paths.logs.is_dir()
