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


def test_legal_settings_panel_builds_offscreen(qapp: QApplication, tmp_path: Path) -> None:
    widget = LegalSettingsWidget(LegalProfile(), tmp_path / "legal_profile.json")
    window = SettingsWindow(widget)

    assert widget.status_label.text()
    assert "Non prêt à commercialiser" in widget.status_label.text()
    assert window.windowTitle() == "SoundMaster — Paramètres"

    window.close()
