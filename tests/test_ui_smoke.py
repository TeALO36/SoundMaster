import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from soundmaster.core.config import AppConfig, AppPaths
from soundmaster.core.legal import LegalProfile
from soundmaster.core.myinstants import MyInstantResult
from soundmaster.ui.legal_settings import LegalSettingsWidget, SettingsWindow
from soundmaster.ui.main_window import MainWindow, ShortcutCaptureButton
from soundmaster.ui.myinstants_widgets import MyInstantCard
from soundmaster.ui.voice_consent import LIABILITY_HTML


@pytest.fixture
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    return application


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        data_dir=tmp_path / "data",
        database=tmp_path / "data" / "soundmaster.db",
        legal_profile=tmp_path / "data" / "legal_profile.json",
        models=tmp_path / "data" / "models",
        audio_cache=tmp_path / "data" / "audio-cache",
        voice_samples=tmp_path / "data" / "voice-samples",
        logs=tmp_path / "data" / "logs",
    )


def _unlocked_window(tmp_path: Path) -> MainWindow:
    """Build a window whose voice-cloning terms are already accepted."""

    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    window._set_voice_cloning_consent(True)
    return window


def test_main_window_builds_offscreen(qapp: QApplication, tmp_path: Path) -> None:
    window = _unlocked_window(tmp_path)

    assert window.pages.count() == 5
    assert len(window.nav_buttons) == 4
    assert window.page_title.text() == "Tableau de bord"

    window.show()
    qapp.processEvents()
    window._select_page(1)
    qapp.processEvents()
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
    assert window.voice_system_record_button.isEnabled() is True
    window.voice_engine.setCurrentIndex(1)
    assert window.voice_model.text() == "k2-fsa/OmniVoice"
    window.voice_advanced_button.click()
    qapp.processEvents()
    qapp.processEvents()
    assert window.voice_advanced_button.isChecked() is True
    assert window.voice_advanced.isVisible() is True
    assert window.voice_engine.isVisible() is True
    assert window.voice_temperature.isVisible() is True
    assert window.voice_speed.isVisible() is True
    window.voice_advanced_button.click()
    qapp.processEvents()
    assert window.voice_advanced_button.isChecked() is False
    assert window.voice_advanced.isHidden()

    window._allow_close = True
    window.close()


def test_voice_cloning_is_locked_until_the_user_accepts_the_terms(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    window.show()
    qapp.processEvents()

    # A fresh install has never accepted anything: the menu is locked.
    assert window._voice_cloning_accepted() is False
    assert window.nav_buttons[1].objectName() == "navButtonLocked"
    assert "🔒" in window.nav_buttons[1].text()
    assert window.voice_stack.currentIndex() == 0

    # Clicking the locked entry redirects to the terms instead of the workspace.
    window.nav_buttons[1].click()
    qapp.processEvents()
    assert window.pages.currentIndex() == 4
    assert window.settings_tabs.currentIndex() == 0
    assert window.voice_consent.isVisibleTo(window)
    # The redirect target must state plainly who carries the responsibility.
    assert "n’est pas responsable" in LIABILITY_HTML
    assert "seul responsable" in LIABILITY_HTML

    # Accepting unlocks the workspace and the navigation entry.
    window.voice_consent.accept_box.setChecked(True)
    qapp.processEvents()
    assert window._voice_cloning_accepted() is True
    assert window.nav_buttons[1].objectName() == "navButton"
    assert window.voice_stack.currentIndex() == 1
    window._select_page(1)
    qapp.processEvents()
    assert window.pages.currentIndex() == 1
    assert window.voice_generate_button.isVisibleTo(window)

    # Unticking locks it again and pushes the user out of the page immediately.
    window.voice_consent.accept_box.setChecked(False)
    qapp.processEvents()
    assert window._voice_cloning_accepted() is False
    assert window.voice_stack.currentIndex() == 0
    assert window.pages.currentIndex() == 4

    window._allow_close = True
    window.close()


def test_voice_consent_survives_a_restart(qapp: QApplication, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    first = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    first.voice_consent.accept_box.setChecked(True)
    first._allow_close = True
    first.close()

    second = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    assert second._voice_cloning_accepted() is True
    assert second.voice_consent.accept_box.isChecked() is True
    assert second.voice_stack.currentIndex() == 1
    second._allow_close = True
    second.close()


def test_recorded_sample_is_immediately_playable(qapp: QApplication, tmp_path: Path) -> None:
    window = _unlocked_window(tmp_path)
    sample = tmp_path / "recorded.wav"
    sample.write_bytes(b"RIFF sample")

    assert window.voice_sample_player.has_source() is False
    window._register_recorded_sample(sample, "Voix microphone")

    assert window.voice_sample.text() == str(sample)
    assert window.voice_sample_player.has_source() is True
    assert window.voice_sample_player.source_path() == sample
    assert window.voice_sample_player.play_button.isEnabled() is True
    assert "écoute" in window.voice_profile_status.text().lower()

    window._start_new_voice_profile()
    assert window.voice_sample_player.has_source() is False
    assert window.voice_sample.text() == ""

    window._allow_close = True
    window.close()


def test_generated_result_is_playable_and_test_runs_stay_out_of_history(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = _unlocked_window(tmp_path)
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"RIFF sample")
    generated = tmp_path / "voice.wav"
    generated.write_bytes(b"RIFF generated")
    window.voice_favorite.setChecked(False)

    window._voice_test_mode = True
    window._voice_finished(str(generated), "qwen3-tts", "Qwen/Qwen3-TTS", "Bonjour", str(sample))
    assert window.library.voice_generations() == []
    assert window.voice_result_player.source_path() == generated
    assert window.voice_result_favorite_button.isEnabled() is True
    assert window.voice_result_folder_button.isEnabled() is True

    window._voice_test_mode = False
    window._voice_finished(str(generated), "qwen3-tts", "Qwen/Qwen3-TTS", "Bonjour", str(sample))
    generations = window.library.voice_generations()
    assert len(generations) == 1
    assert generations[0].output_path == str(generated)
    assert window.voice_history.count() == 1
    assert window.voice_history.item(0).data(Qt.ItemDataRole.UserRole) == str(generated)

    window._allow_close = True
    window.close()


def test_test_phrase_falls_back_to_a_built_in_sentence(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = _unlocked_window(tmp_path)

    assert window._test_phrase() == MainWindow._VOICE_TEST_SENTENCE
    window.voice_text.setPlainText("  Salut   les   amis  ")
    assert window._test_phrase() == "Salut les amis"
    window.voice_text.setPlainText("a" * 400)
    assert len(window._test_phrase()) == 120

    window._allow_close = True
    window.close()


def test_dashboard_grid_columns_follow_available_width(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
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


def test_voice_layout_reflows_at_compact_width_without_hiding_actions(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = _unlocked_window(tmp_path)
    window.show()
    window._select_page(1)
    window.resize(820, 560)
    qapp.processEvents()

    assert window.minimumWidth() <= 820
    assert window.minimumHeight() >= 680
    assert window.voice_text.isVisibleTo(window)
    assert window.voice_generate_button.isVisibleTo(window)
    assert window.voice_test_button.isVisibleTo(window)
    assert window.voice_save_button.isVisibleTo(window)
    assert window.voice_sample_player.isVisibleTo(window)
    assert window.voice_result_player.isVisibleTo(window)
    assert window.voice_record_button.isVisibleTo(window)
    assert window.voice_system_record_button.isVisibleTo(window)
    assert window.voice_import_button.isVisibleTo(window)
    assert window._voice_record_widgets[1].geometry().top() > window._voice_record_widgets[0].geometry().top()

    window.resize(1180, 760)
    qapp.processEvents()
    assert window._voice_record_widgets[0].geometry().top() == window._voice_record_widgets[1].geometry().top()
    # The editor must stay comfortably writable at every width.
    assert window.voice_text.minimumHeight() >= 110
    assert window.voice_text.height() >= 110

    window._allow_close = True
    window.close()


def test_shortcut_capture_records_and_cancels(qapp: QApplication) -> None:
    button = ShortcutCaptureButton()
    captured: list[str] = []
    button.shortcut_recorded.connect(captured.append)

    button.start_recording()
    button.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_1,
            Qt.KeyboardModifier.ControlModifier,
        )
    )
    assert captured == ["ctrl+1"]
    assert button.sequence == "ctrl+1"
    assert button.recording is False

    button.start_recording()
    button.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert button.sequence == "ctrl+1"
    assert button.recording is False


def test_keybinds_are_recorded_for_each_favorite(qapp: QApplication, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    sounds = []
    for index in range(2):
        audio = tmp_path / f"shortcut-{index}.wav"
        audio.write_bytes(b"RIFF")
        sounds.append(window.library.add_sound(f"Shortcut {index}", audio, favorite=True))

    window._refresh_keybinds()
    first = window._keybind_capture_buttons[sounds[0].id]
    second = window._keybind_capture_buttons[sounds[1].id]
    first.start_recording()
    first.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_1,
            Qt.KeyboardModifier.AltModifier,
        )
    )
    second.start_recording()
    second.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_2,
            Qt.KeyboardModifier.ControlModifier,
        )
    )

    assert window.library.keybinds() == {
        sounds[0].id: "alt+1",
        sounds[1].id: "ctrl+2",
    }
    window._clear_keybind(sounds[0].id)
    assert window.library.keybinds() == {sounds[1].id: "ctrl+2"}

    window._allow_close = True
    window.close()


def test_sound_card_tester_toggles_to_stop(qapp: QApplication, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
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


def test_myinstants_tester_toggles_to_stop_and_stops_preview(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    result = MyInstantResult(
        "Airhorn",
        "https://www.myinstants.com/en/instant/airhorn/",
        "https://www.myinstants.com/media/sounds/airhorn.mp3",
    )
    card = MyInstantCard(result)

    class FakePlayer:
        def __init__(self) -> None:
            self.play_count = 0
            self.stop_count = 0

        def setSource(self, _url) -> None:
            return None

        def play(self) -> None:
            self.play_count += 1

        def stop(self) -> None:
            self.stop_count += 1

    player = FakePlayer()
    window._players[False] = player
    window._myinstant_cards[result.audio_url] = card
    card.preview_requested.connect(lambda selected: window._download_myinstant(selected, False))

    card.preview_button.click()
    assert player.play_count == 1
    assert window._active_remote_preview_url == result.audio_url
    assert card.preview_button.text() == "■ Stop"

    card.preview_button.click()
    assert player.stop_count == 1
    assert window._active_remote_preview_url is None
    assert card.preview_button.text() == "▶ Tester"

    window._allow_close = True
    window.close()


def test_system_output_recording_button_starts_stops_and_attaches_sample(
    qapp: QApplication, tmp_path: Path, monkeypatch
) -> None:
    stopped = threading.Event()

    class FakeSystemAudioRecorder:
        @staticmethod
        def capability_error() -> str | None:
            return None

        def __init__(self, output_path: Path, _device=None) -> None:
            self.output_path = output_path

        def start(self) -> None:
            stopped.wait(timeout=2)
            self.output_path.write_bytes(b"RIFF fake output capture")

        def stop(self) -> None:
            stopped.set()

    monkeypatch.setattr(
        "soundmaster.ui.main_window.SystemAudioRecorder", FakeSystemAudioRecorder
    )
    window = _unlocked_window(tmp_path)

    window._toggle_system_recording()
    deadline = time.time() + 2
    while (
        window._system_recording_thread is None
        or not window._system_recording_thread.is_alive()
    ) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert window.voice_system_record_button.text() == "■ Arrêter la sortie"

    window._toggle_system_recording()
    deadline = time.time() + 2
    while window._system_recording_thread is not None and time.time() < deadline:
        qapp.processEvents()
        window._poll_system_recording()
        time.sleep(0.01)
    window._poll_system_recording()

    assert window.voice_system_record_button.text() == MainWindow._SYSTEM_BUTTON_LABEL
    assert window.voice_sample.text().endswith(".wav")
    assert Path(window.voice_sample.text()).is_file()

    window._allow_close = True
    window.close()


def test_voice_profile_is_named_and_saved_after_sample_selection(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = _unlocked_window(tmp_path)
    sample = tmp_path / "recorded-sample.wav"
    sample.write_bytes(b"RIFF sample")

    window._start_new_voice_profile()
    window.voice_profile_name.setText("Discord — voix grave")
    window.voice_sample.setText(str(sample))
    window.voice_reference_text.setText("Bonjour")
    window.voice_temperature.setValue(0.45)
    window.voice_speed.setValue(1.15)
    window._save_voice_profile()

    profiles = window.library.voice_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "Discord — voix grave"
    assert profiles[0].sample_path == str(sample)
    assert profiles[0].settings["temperature"] == 0.45
    assert profiles[0].settings["speed"] == 1.15
    assert window.voice_profile_combo.currentText() == "Discord — voix grave"

    window.voice_profile_combo.setCurrentIndex(0)
    assert window.voice_profile_name.text() == "Discord — voix grave"
    assert window.voice_sample.text() == str(sample)
    assert window.voice_reference_text.text() == "Bonjour"
    assert window.voice_temperature.value() == 0.45
    assert window.voice_speed.value() == 1.15

    window._allow_close = True
    window.close()


def test_legal_settings_panel_builds_offscreen(qapp: QApplication, tmp_path: Path) -> None:
    widget = LegalSettingsWidget(LegalProfile(), tmp_path / "legal_profile.json")
    window = SettingsWindow(widget)

    assert widget.status_label.text()
    assert "Non prêt à commercialiser" in widget.status_label.text()
    assert window.windowTitle() == "SoundMaster — Paramètres"
    assert widget.section_tabs.count() == 5
    assert [widget.section_tabs.tabText(index) for index in range(widget.section_tabs.count())] == [
        "Éditeur",
        "Documents",
        "Données",
        "Checklist",
        "À vérifier",
    ]
    assert widget._document_inputs["qwen_model_id"].text() == "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    assert widget._document_inputs["qwen_notice_reference"].text() == ""

    window.close()
