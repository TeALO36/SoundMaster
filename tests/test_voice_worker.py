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
    assert paths.voice_record_button.text == "● Enregistrer"
