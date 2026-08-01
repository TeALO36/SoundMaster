from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication

from soundmaster.ui.main_window import MainWindow, VoiceWorker


@pytest.fixture
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeVoiceService:
    def generate_clone(
        self,
        text: str,
        sample: Path,
        ref_text: str,
        output: Path,
        language: str,
        engine_key: str,
    ) -> Path:
        assert (text, sample, ref_text, language, engine_key) == (
            "Bonjour",
            Path("sample.wav"),
            "",
            "French",
            "omnivoice",
        )
        return output


def test_voice_worker_emits_frozen_generation_metadata(qapp: QApplication, tmp_path: Path) -> None:
    worker = VoiceWorker(
        FakeVoiceService(),
        "Bonjour",
        Path("sample.wav"),
        "",
        tmp_path / "voice.wav",
        "French",
        "omnivoice",
        "k2-fsa/OmniVoice",
    )
    received: list[tuple[str, str, str, str, str]] = []
    worker.finished.connect(lambda *args: received.append(args))

    worker.run()

    assert received == [
        (
            str(tmp_path / "voice.wav"),
            "omnivoice",
            "k2-fsa/OmniVoice",
            "Bonjour",
            "sample.wav",
        )
    ]


class AdvancedFakeVoiceService:
    def __init__(self) -> None:
        self.settings: dict[str, object] | None = None

    def generate_clone(
        self,
        _text: str,
        _sample: Path,
        _ref_text: str,
        output: Path,
        _language: str,
        _engine_key: str,
        settings: dict[str, object],
    ) -> Path:
        self.settings = settings
        return output


def test_voice_worker_passes_advanced_settings_only_when_present(
    qapp: QApplication, tmp_path: Path
) -> None:
    service = AdvancedFakeVoiceService()
    worker = VoiceWorker(
        service,
        "Bonjour",
        Path("sample.wav"),
        "",
        tmp_path / "voice.wav",
        "French",
        "qwen3-tts",
        "Qwen/Qwen3-TTS",
        {"temperature": 0.4, "speed": 1.1},
    )

    worker.run()

    assert service.settings == {"temperature": 0.4, "speed": 1.1}


def test_recording_error_resets_recording_state(qapp: QApplication, tmp_path: Path) -> None:
    # Keep this focused on UI state; MainWindow's optional multimedia backend may be
    # unavailable in CI, so no real microphone is required.
    paths = MainWindow.__new__(MainWindow)
    paths._recording_path = tmp_path / "unfinished.wav"
    paths.voice_record_button = type("Button", (), {})()
    paths.voice_record_button.setText = lambda value: setattr(paths.voice_record_button, "text", value)
    paths.voice_record_button.setToolTip = lambda value: setattr(paths.voice_record_button, "tooltip", value)
    paths.statusBar = lambda: type("Status", (), {"showMessage": lambda *_args: None})()

    MainWindow._recording_error(paths, None, "microphone failure")

    assert paths._recording_path is None
    assert paths.voice_record_button.text == MainWindow._MIC_BUTTON_LABEL
