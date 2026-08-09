import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from soundmaster.core.config import AppPaths
from soundmaster.core.tts import QwenVoiceService


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


def test_qwen_empty_reference_text_uses_local_transcription(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    model_dir = paths.models / "Qwen3-TTS-12Hz-1.7B-Base"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"sample")
    output = tmp_path / "generated.wav"
    service = QwenVoiceService(paths)
    fake_model = SimpleNamespace()
    captured: dict[str, str] = {}

    monkeypatch.setattr(service, "_load_engine", lambda *_args: fake_model)

    def fake_transcribe(ref_audio: Path, language: str) -> str:
        captured["audio"] = str(ref_audio)
        captured["language"] = language
        return "Texte transcrit localement"

    monkeypatch.setattr(service, "_auto_transcribe", fake_transcribe)
    monkeypatch.setattr(
        QwenVoiceService,
        "_generate_qwen",
        staticmethod(
            lambda model, text, ref_audio, ref_text, language: (
                [0.0, 0.1, -0.1],
                24_000,
            )
        ),
    )

    def fake_write(path: str, _audio: object, _sample_rate: int) -> None:
        Path(path).write_bytes(b"RIFF" + b"\\0" * 64)

    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(write=fake_write))

    result = service.generate_clone(
        "Bonjour",
        sample,
        "",
        output,
        "French",
        "qwen3-tts",
    )

    assert result == output
    assert captured == {"audio": str(sample), "language": "French"}
    assert output.is_file()
    assert output.stat().st_size > 44


def test_windows_paging_file_exhaustion_becomes_an_actionable_message() -> None:
    from soundmaster.core.tts import OUT_OF_MEMORY_HINT, _is_out_of_memory

    windows_error = OSError("Le fichier de pagination est insuffisant pour terminer cette opération.")
    windows_error.winerror = 1455
    assert _is_out_of_memory(windows_error) is True
    assert _is_out_of_memory(MemoryError()) is True
    assert _is_out_of_memory(RuntimeError("os error 1455")) is True
    assert _is_out_of_memory(RuntimeError("paging file is too small")) is True
    assert _is_out_of_memory(RuntimeError("connexion refusée")) is False

    # The cause chain matters: loaders wrap the OS error in their own exception.
    wrapped = RuntimeError("Chargement impossible")
    wrapped.__cause__ = windows_error
    assert _is_out_of_memory(wrapped) is True

    assert "fichier de pagination" in OUT_OF_MEMORY_HINT
    assert "Mémoire virtuelle" in OUT_OF_MEMORY_HINT


def test_model_load_failure_reports_the_memory_hint(tmp_path, monkeypatch) -> None:
    from soundmaster.core.tts import OUT_OF_MEMORY_HINT, QwenVoiceService, VoiceGenerationError

    paths = _paths(tmp_path)
    service = QwenVoiceService(paths)
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    def explode(*_args, **_kwargs):
        error = OSError("Le fichier de pagination est insuffisant pour terminer cette opération.")
        error.winerror = 1455
        raise error

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: False),
            float32="float32",
        )
    )
    monkeypatch.setitem(sys.modules, "qwen_tts", SimpleNamespace(
        Qwen3TTSModel=SimpleNamespace(from_pretrained=explode)
    ))

    with pytest.raises(VoiceGenerationError) as raised:
        service._load_engine(model_dir, "qwen3-tts")
    assert str(raised.value) == OUT_OF_MEMORY_HINT


class _FakePocketModel:
    """Mimics the pocket_tts TTSModel surface used by SoundMaster."""

    sample_rate = 24_000

    def __init__(self) -> None:
        self.prompt_calls: list[str] = []
        self.generated: list[tuple[object, str]] = []

    def get_state_for_audio_prompt(self, path: str) -> object:
        self.prompt_calls.append(path)
        return {"voice": path}

    def generate_audio(self, state: object, text: str):
        self.generated.append((state, text))
        return SimpleNamespace(
            detach=lambda: SimpleNamespace(
                cpu=lambda: SimpleNamespace(numpy=lambda: [0.0, 0.5, -0.5])
            )
        )


def test_pocket_tts_needs_no_transcript_and_caches_the_cloned_voice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from soundmaster.core.tts import QwenVoiceService

    paths = _paths(tmp_path)
    service = QwenVoiceService(paths)
    sample = tmp_path / "voice.wav"
    sample.write_bytes(b"RIFF" + b"\0" * 64)
    model = _FakePocketModel()
    monkeypatch.setattr(service, "_load_engine", lambda *_args: model)

    written: list[tuple[str, int]] = []

    def fake_write(path: str, _audio: object, sample_rate: int) -> None:
        Path(path).write_bytes(b"RIFF" + b"\0" * 64)
        written.append((path, sample_rate))

    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(write=fake_write))

    first = service.generate_clone(
        "Bonjour", sample, "", tmp_path / "a.wav", "French", "pocket-tts"
    )
    second = service.generate_clone(
        "Autre phrase", sample, "", tmp_path / "b.wav", "French", "pocket-tts"
    )

    assert first.is_file() and second.is_file()
    # Whisper is never consulted: no transcript is required by this engine.
    assert service._whisper_model is None
    # Cloning the sample is the expensive step, so it must happen exactly once.
    assert model.prompt_calls == [str(sample)]
    assert [text for _state, text in model.generated] == ["Bonjour", "Autre phrase"]
    assert [rate for _path, rate in written] == [24_000, 24_000]

    # Re-recording the sample must invalidate the cached voice.
    sample.write_bytes(b"RIFF" + b"\1" * 128)
    service.generate_clone(
        "Encore", sample, "", tmp_path / "c.wav", "French", "pocket-tts"
    )
    assert model.prompt_calls == [str(sample), str(sample)]


def test_pocket_tts_reports_a_missing_runtime(tmp_path: Path, monkeypatch) -> None:
    from soundmaster.core.tts import QwenVoiceService, VoiceGenerationError

    service = QwenVoiceService(_paths(tmp_path))
    monkeypatch.setitem(sys.modules, "pocket_tts", None)

    with pytest.raises(VoiceGenerationError, match=r"soundmaster\[pocket\]"):
        service._load_pocket_engine(tmp_path / "missing")


def test_pocket_tts_does_not_require_a_managed_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The engine downloads its own weights, so an empty model dir is fine."""

    from soundmaster.core.tts import QwenVoiceService

    service = QwenVoiceService(_paths(tmp_path))
    sample = tmp_path / "voice.wav"
    sample.write_bytes(b"RIFF" + b"\0" * 64)
    model = _FakePocketModel()
    loaded: list[object] = []

    def fake_load(local_model, engine_key):
        loaded.append((local_model, engine_key))
        return model

    monkeypatch.setattr(service, "_load_engine", fake_load)
    monkeypatch.setitem(
        sys.modules,
        "soundfile",
        SimpleNamespace(write=lambda path, *_a: Path(path).write_bytes(b"RIFF")),
    )

    service.generate_clone("Salut", sample, "", tmp_path / "out.wav", "Auto", "pocket-tts")

    assert loaded, "the engine must still be loaded"
