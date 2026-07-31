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
