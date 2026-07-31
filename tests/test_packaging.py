import sys
from pathlib import Path

from soundmaster.core import config


def test_portable_mode_uses_executable_directory(monkeypatch, tmp_path: Path) -> None:
    executable_dir = tmp_path / "SoundMaster"
    executable_dir.mkdir()
    (executable_dir / ".portable").write_text("portable", encoding="utf-8")
    executable = executable_dir / "SoundMaster.exe"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.delenv("SOUNDMASTER_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert config.is_portable_mode() is True
    _, paths = config.load_config()

    assert paths.data_dir == executable_dir / "data"


def test_portable_marker_is_ignored_for_source_runs(monkeypatch, tmp_path: Path) -> None:
    executable_dir = tmp_path / "SoundMaster"
    executable_dir.mkdir()
    (executable_dir / ".portable").write_text("portable", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable_dir / "SoundMaster.exe"))

    assert config.is_portable_mode() is False
