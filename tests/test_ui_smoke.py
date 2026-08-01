import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from soundmaster.core.config import AppConfig, AppPaths
from soundmaster.core.legal import LegalProfile
from soundmaster.ui.legal_settings import LegalSettingsWidget, SettingsWindow
from soundmaster.ui.main_window import MainWindow


@pytest.fixture
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    return application


def test_main_window_builds_offscreen(qapp: QApplication, tmp_path: Path) -> None:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "soundmaster.db",
        legal_profile=tmp_path / "data" / "legal_profile.json",
        models=tmp_path / "data" / "models",
        audio_cache=tmp_path / "data" / "audio-cache",
        voice_samples=tmp_path / "data" / "voice-samples",
        logs=tmp_path / "data" / "logs",
    )
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())

    assert window.pages.count() == 5
    assert len(window.nav_buttons) == 4
    assert window.page_title.text() == "Tableau de bord"

    window._select_page(1)
    assert window.voice_advanced_button.isChecked() is False
    assert window.voice_advanced.isVisible() is False
    assert window.voice_advanced.isHidden()
    assert "facultatif" in window.voice_reference_text.placeholderText().lower()
    assert window.voice_engine.currentData() == "qwen3-tts"
    assert window.voice_engine.itemData(1) == "omnivoice"
    assert window.voice_progress.isHidden()
    assert window.search_progress.isHidden()
    assert window.download_group.isHidden()
    assert window.favorite_selected_myinstants.isEnabled() is False
    assert window.bulk_download_progress.isHidden()
    window.voice_engine.setCurrentIndex(1)
    assert window.voice_model.text() == "k2-fsa/OmniVoice"
    window.voice_advanced_button.click()
    assert not window.voice_advanced.isHidden()
    window.voice_advanced_button.click()
    assert window.voice_advanced.isHidden()

    window._allow_close = True
    window.close()


def test_voice_editor_height_is_adjustable_and_persistent(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "soundmaster.db",
        legal_profile=tmp_path / "data" / "legal_profile.json",
        models=tmp_path / "data" / "models",
        audio_cache=tmp_path / "data" / "audio-cache",
        voice_samples=tmp_path / "data" / "voice-samples",
        logs=tmp_path / "data" / "logs",
    )
    first = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    first.voice_workspace_splitter.setSizes([220, 440])
    first._voice_workspace_splitter_moved(220, 0)
    saved_sizes = first.library.preference("voice_workspace_sizes")
    assert saved_sizes
    assert len(saved_sizes.split(",")) == 2
    first._allow_close = True
    first.close()

    second = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    restored_sizes = second.voice_workspace_splitter.sizes()
    assert restored_sizes[0] > 0 and restored_sizes[1] > 0
    second._allow_close = True
    second.close()


def test_dashboard_grid_columns_follow_available_width(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "soundmaster.db",
        legal_profile=tmp_path / "data" / "legal_profile.json",
        models=tmp_path / "data" / "models",
        audio_cache=tmp_path / "data" / "audio-cache",
        voice_samples=tmp_path / "data" / "voice-samples",
        logs=tmp_path / "data" / "logs",
    )
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())

    assert window._grid_columns(500) == 2
    assert window._grid_columns(900) == 3
    assert window._grid_columns(1200) == 4

    files = []
    for index in range(4):
        audio = tmp_path / f"sound-{index}.wav"
        audio.write_bytes(b"RIFF")
        files.append(window.library.add_sound(f"Sound {index}", audio, favorite=True))
    window._refresh_dashboard()
    window._reflow_grid(window.card_grid, window._dashboard_cards, 4)

    rendered = [
        window.card_grid.itemAt(index).widget().item
        for index in range(window.card_grid.count())
        if window.card_grid.itemAt(index).widget() is not None
    ]
    assert {item.title for item in rendered} == {item.title for item in files}
    assert window.card_grid.itemAtPosition(0, 3).widget().item.title == "Sound 3"
    assert window.card_grid.itemAtPosition(1, 0) is None

    window._allow_close = True
    window.close()


def test_sound_card_tester_toggles_to_stop(qapp: QApplication, tmp_path: Path) -> None:
    paths = AppPaths(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "soundmaster.db",
        legal_profile=tmp_path / "data" / "legal_profile.json",
        models=tmp_path / "data" / "models",
        audio_cache=tmp_path / "data" / "audio-cache",
        voice_samples=tmp_path / "data" / "voice-samples",
        logs=tmp_path / "data" / "logs",
    )
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    audio = tmp_path / "tester.wav"
    audio.write_bytes(b"RIFF")
    sound = window.library.add_sound("Tester sound", audio, favorite=True)
    window._refresh_dashboard()
    card = next(card for card in window._dashboard_cards if card.item.id == sound.id)
    played: list[tuple[int, bool]] = []
    stopped: list[int] = []
    card.play_requested.connect(lambda sound_id, virtual: played.append((sound_id, virtual)))
    card.stop_requested.connect(stopped.append)

    card.preview_button.click()
    assert played == [(sound.id, False)]
    card.set_preview_playing(True)
    assert card.preview_button.text() == "■ Stop"
    card.preview_button.click()
    assert stopped == [sound.id]
    card.set_preview_playing(False)
    assert card.preview_button.text() == "Tester"

    window._allow_close = True
    window.close()


def test_legal_settings_panel_builds_offscreen(qapp: QApplication, tmp_path: Path) -> None:
    widget = LegalSettingsWidget(LegalProfile(), tmp_path / "legal_profile.json")
    window = SettingsWindow(widget)

    assert widget.status_label.text()
    assert "Non prêt à commercialiser" in widget.status_label.text()
    assert window.windowTitle() == "SoundMaster — Paramètres"

    window.close()
