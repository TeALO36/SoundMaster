"""Application configuration and local data paths."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "SoundMaster"
DATA_DIR_ENV = "SOUNDMASTER_DATA_DIR"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """All persistent paths used by SoundMaster.

    Paths are resolved centrally so future audio, database, and TTS services do not
    each invent their own storage locations. Directories are created explicitly by
    :meth:`ensure_runtime_directories` rather than as an import side effect.
    """

    data_dir: Path
    database: Path
    legal_profile: Path
    models: Path
    audio_cache: Path
    voice_samples: Path
    logs: Path

    @classmethod
    def from_environment(cls) -> AppPaths:
        configured_dir = os.environ.get(DATA_DIR_ENV)
        if configured_dir:
            data_dir = Path(configured_dir).expanduser()
        elif is_portable_mode():
            data_dir = Path(sys.executable).resolve().parent / "data"
        else:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                data_dir = Path(local_app_data) / APP_NAME
            else:
                # Keeps development usable on non-Windows machines without changing
                # the intended Windows default.
                data_dir = Path.home() / ".local" / "share" / APP_NAME

        data_dir = data_dir.resolve()
        configured_model_dir = os.environ.get("SOUNDMASTER_MODEL_DIR")
        models = (
            Path(configured_model_dir).expanduser().resolve()
            if configured_model_dir
            else data_dir / "models"
        )
        return cls(
            data_dir=data_dir,
            database=data_dir / "soundmaster.db",
            legal_profile=data_dir / "legal_profile.json",
            models=models,
            audio_cache=data_dir / "audio-cache",
            voice_samples=data_dir / "voice-samples",
            logs=data_dir / "logs",
        )

    def ensure_runtime_directories(self) -> None:
        """Create directories required by the running application."""

        for directory in (self.data_dir, self.models, self.audio_cache, self.voice_samples, self.logs):
            directory.mkdir(parents=True, exist_ok=True)


def is_portable_mode() -> bool:
    """Return whether a frozen build was launched from a portable distribution."""

    if not getattr(sys, "frozen", False):
        return False
    return (Path(sys.executable).resolve().parent / ".portable").is_file()


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Non-secret application settings used by the bootstrap."""

    app_name: str = APP_NAME
    favorite_limit: int = 10
    minimize_to_tray: bool = True

    def __post_init__(self) -> None:
        if self.favorite_limit < 1:
            raise ValueError("favorite_limit must be greater than zero")


def load_config() -> tuple[AppConfig, AppPaths]:
    """Return validated settings and resolved persistent paths."""

    return AppConfig(), AppPaths.from_environment()
