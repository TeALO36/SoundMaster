import sys
from pathlib import Path

from soundmaster.core import config


def test_spec_bundles_the_zero_latency_audio_libraries() -> None:
    """The packaged app must embed sounddevice AND soundfile.

    soundfile decodes WAV/MP3/OGG/FLAC for the FastAudioEngine. If it is missing
    from the bundle, every sound silently falls back to QMediaPlayer and the
    playback latency regresses to ~2 s — exactly what happened before soundfile
    was declared a base dependency and collected in the spec.
    """

    spec = Path("packaging/SoundMaster.spec").read_text(encoding="utf-8")
    assert 'collect_all("sounddevice")' in spec
    assert 'collect_all("soundfile")' in spec
    assert "*soundfile_datas" in spec
    assert "*soundfile_binaries" in spec
    assert "*soundfile_hiddenimports" in spec


def test_spec_bundles_the_default_voice_engine() -> None:
    """The packaged app must embed pocket_tts, the default voice engine.

    Regression: v0.8.7 shipped without it. is_engine_runtime_installed() then
    returned False for the user's default, the generation fallback switched to
    omnivoice (its unconditional last resort) and the user was asked to install
    the OmniVoice model although they had Pocket TTS selected.
    """

    spec = Path("packaging/SoundMaster.spec").read_text(encoding="utf-8")
    assert 'collect_all("pocket_tts")' in spec
    assert "*pocket_datas" in spec
    assert "*pocket_binaries" in spec
    assert "*pocket_hiddenimports" in spec


def test_spec_bundles_the_recommended_qwen_engine_and_its_transcriber() -> None:
    """The packaged app must embed the Qwen3-TTS runtime and faster-whisper.

    Without them every engine except Pocket TTS answers "runtime manque" in the
    packaged app, exactly like the user-reported "Le runtime qwen-tts manque"
    (qwen-tts/omnivoice/f5-tts were never installed at build time because the
    `tts` extra was unresolvable).
    """

    spec = Path("packaging/SoundMaster.spec").read_text(encoding="utf-8")
    assert 'collect_all("qwen_tts")' in spec
    assert 'collect_all("faster_whisper")' in spec
    assert "*qwen_datas" in spec
    assert "*whisper_hiddenimports" in spec
    assert '"torch"' in spec


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
