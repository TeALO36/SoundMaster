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
    # Pocket TTS leads: it is the fast CPU engine and needs no transcript.
    assert window.voice_engine.currentData() == "pocket-tts"
    assert window.voice_engine.itemData(1) == "qwen3-tts"
    assert window.voice_engine.itemData(2) == "omnivoice"
    assert window.voice_model.text() == "kyutai/pocket-tts"
    assert window.voice_reference_text.isEnabled() is False
    assert "inutile" in window.voice_reference_text.placeholderText().lower()
    assert window.voice_progress.isHidden()
    assert window.search_progress.isHidden()
    assert window.download_group.isHidden()
    assert window.favorite_selected_myinstants.isEnabled() is False
    assert window.bulk_download_progress.isHidden()
    assert window.voice_system_record_button.isEnabled() is True
    window.voice_engine.setCurrentIndex(2)
    assert window.voice_model.text() == "k2-fsa/OmniVoice"
    assert window.voice_reference_text.isEnabled() is True
    assert "facultatif" in window.voice_reference_text.placeholderText().lower()
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
    assert not window.nav_buttons[1].icon().isNull()
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


def test_consent_redirect_explains_itself_and_leads_back(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    window.show()
    qapp.processEvents()

    consent = window.voice_consent
    assert consent.redirect_banner.isVisible() is False
    assert consent.open_button.isVisible() is False

    window.nav_buttons[1].click()
    qapp.processEvents()
    # The jump is explained, and the exact row to act on is highlighted.
    assert consent.redirect_banner.isVisible() is True
    assert consent.action_row.objectName() == "consentActionHighlight"
    assert window._voice_consent_pending_redirect is True

    consent.accept_box.setChecked(True)
    qapp.processEvents()
    # A visible way back exists instead of expecting a second menu click.
    assert consent.open_button.isVisible() is True
    window._return_to_voice_after_consent()
    qapp.processEvents()
    assert window.pages.currentIndex() == 1
    assert window._voice_consent_pending_redirect is False
    assert consent.redirect_banner.isVisible() is False

    window._allow_close = True
    window.close()


def test_consent_return_is_abandoned_if_consent_is_withdrawn_first(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    window.show()
    window.nav_buttons[1].click()
    window.voice_consent.accept_box.setChecked(True)
    window.voice_consent.accept_box.setChecked(False)
    qapp.processEvents()

    # The pending jump must not drop a locked user into the workspace.
    window._return_to_voice_after_consent()
    qapp.processEvents()
    assert window.pages.currentIndex() == 4
    assert window.voice_stack.currentIndex() == 0

    window._allow_close = True
    window.close()


def test_consent_accepted_without_redirect_does_not_hijack_navigation(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    window.show()
    window._select_settings()
    window.voice_consent.accept_box.setChecked(True)
    qapp.processEvents()

    assert window._voice_consent_pending_redirect is False
    assert window.pages.currentIndex() == 4
    assert window.voice_consent.redirect_banner.isVisible() is False
    assert window.voice_consent.open_button.isVisible() is True

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
    # Loaded and ready, but never played without the user asking for it.
    assert window.voice_sample_player.is_playing() is False
    assert "réécouter" in window.voice_profile_status.text().lower()

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


def test_recent_sounds_exclude_favorites_and_expose_full_actions(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())

    favorite_audio = tmp_path / "favorite.wav"
    favorite_audio.write_bytes(b"RIFF")
    played_audio = tmp_path / "played.wav"
    played_audio.write_bytes(b"RIFF")
    favorite = window.library.add_sound("Un favori", favorite_audio, favorite=True)
    played = window.library.add_sound("Déjà joué", played_audio, favorite=False)
    window.library.record_use(favorite.id)
    window.library.record_use(played.id)
    window._refresh_dashboard()

    favorite_titles = {card.item.title for card in window._dashboard_cards}
    recent_titles = {card.item.title for card in window._recent_cards}
    assert favorite_titles == {"Un favori"}
    # A favorite that was just played must not appear twice on the dashboard.
    assert recent_titles == {"Déjà joué"}

    # Same actions as a Myinstants card: listen, send, re-favorite — plus rename.
    card = window._recent_cards[0]
    assert card.preview_button.text() == "▶ Tester"
    assert card.send_button.text() == "Envoyer"
    assert card.favorite_button.text() == "☆ Favori"
    assert card.favorite_button.isChecked() is False
    assert card.rename_button.text() == "Renommer"
    assert window._dashboard_cards[0].favorite_button.text() == "★ Favori"

    # Starring a recent sound promotes it into the favorites grid.
    window._set_favorite(played.id, True)
    assert {c.item.title for c in window._dashboard_cards} == {"Un favori", "Déjà joué"}
    assert window._recent_cards == []

    window._allow_close = True
    window.close()


def test_favorites_can_be_renamed(qapp: QApplication, tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    audio = tmp_path / "rename-me.wav"
    audio.write_bytes(b"RIFF")
    sound = window.library.add_sound("Ancien nom", audio, favorite=True)

    renamed = window.library.rename_sound(sound.id, "  Nouveau nom  ")
    assert renamed is not None
    assert renamed.title == "Nouveau nom"

    window._refresh_dashboard()
    assert {card.item.title for card in window._dashboard_cards} == {"Nouveau nom"}

    with pytest.raises(ValueError):
        window.library.rename_sound(sound.id, "   ")

    window._allow_close = True
    window.close()


def test_favorite_limit_blocks_promoting_another_sound(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig(favorite_limit=1))
    first = tmp_path / "first.wav"
    first.write_bytes(b"RIFF")
    second = tmp_path / "second.wav"
    second.write_bytes(b"RIFF")
    window.library.add_sound("Premier", first, favorite=True)
    extra = window.library.add_sound("Second", second, favorite=False)

    monkeypatched: list[str] = []
    from PyQt6.QtWidgets import QMessageBox

    original = QMessageBox.warning
    QMessageBox.warning = staticmethod(  # type: ignore[method-assign]
        lambda *args, **kwargs: monkeypatched.append(args[1] if len(args) > 1 else "")
    )
    try:
        window._set_favorite(extra.id, True)
    finally:
        QMessageBox.warning = original  # type: ignore[method-assign]

    assert monkeypatched == ["Limite atteinte"]
    assert len(window.library.sounds(favorites_only=True)) == 1

    window._allow_close = True
    window.close()


class _FakePlayer:
    """Records what the window asks the media backend to do."""

    def __init__(self) -> None:
        self.sources: list[str] = []
        self.plays = 0
        self.positions: list[int] = []
        self.state = None

    def setSource(self, url) -> None:
        self.sources.append(url.toString())

    def setPosition(self, position: int) -> None:
        self.positions.append(position)

    def play(self) -> None:
        self.plays += 1

    def stop(self) -> None:
        return None

    def playbackState(self):
        from PyQt6.QtMultimedia import QMediaPlayer

        return self.state or QMediaPlayer.PlaybackState.StoppedState


def test_replaying_the_same_sound_skips_the_costly_source_reload(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    first = tmp_path / "a.wav"
    first.write_bytes(b"RIFF")
    second = tmp_path / "b.wav"
    second.write_bytes(b"RIFF")
    player = _FakePlayer()
    window._players[False] = player

    window._play_file(first, False)
    assert len(player.sources) == 1
    assert player.plays == 1

    # Same file again: re-resolving it costs ~150 ms, so only seek and play.
    window._play_file(first, False)
    assert len(player.sources) == 1
    assert player.positions == [0]
    assert player.plays == 2

    # A different file must of course still be loaded.
    window._play_file(second, False)
    assert len(player.sources) == 2

    window._allow_close = True
    window.close()


def test_hovering_a_card_preloads_it_but_never_interrupts_playback(
    qapp: QApplication, tmp_path: Path
) -> None:
    from PyQt6.QtMultimedia import QMediaPlayer

    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    audio = tmp_path / "hover.wav"
    audio.write_bytes(b"RIFF")
    sound = window.library.add_sound("Hover", audio, favorite=True)
    window._refresh_dashboard()
    player = _FakePlayer()
    window._players[False] = player

    window._warm_local_preview(sound.id)
    assert len(player.sources) == 1
    # Already warmed: hovering again must not reload it.
    window._warm_local_preview(sound.id)
    assert len(player.sources) == 1
    # And the click itself now only has to play.
    window._play_file(audio, False)
    assert len(player.sources) == 1
    assert player.plays == 1

    # While something is playing, a hover must not steal the player.
    window._player_sources.clear()
    player.state = QMediaPlayer.PlaybackState.PlayingState
    window._warm_local_preview(sound.id)
    assert len(player.sources) == 1

    # The card wires the hover signal through.
    card = window._dashboard_cards[0]
    warmed: list[int] = []
    card.preview_hovered.connect(warmed.append)
    card.preview_hovered.emit(sound.id)
    assert warmed == [sound.id]

    window._allow_close = True
    window.close()


def test_bound_favorites_get_a_preloaded_player_for_instant_shortcuts(
    qapp: QApplication, tmp_path: Path
) -> None:
    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    audio = tmp_path / "bound.wav"
    audio.write_bytes(b"RIFF")
    other = tmp_path / "unbound.wav"
    other.write_bytes(b"RIFF")
    bound = window.library.add_sound("Bound", audio, favorite=True)
    unbound = window.library.add_sound("Unbound", other, favorite=True)
    window.library.set_keybind(bound.id, "alt+1")

    window._prepare_hotkey_players()
    assert set(window._hotkey_players) == {bound.id}

    # The shortcut path uses the preloaded player, not the shared one.
    shared = _FakePlayer()
    window._players[True] = shared
    preloaded = _FakePlayer()
    window._hotkey_players[bound.id] = (preloaded, object())
    window._play_sound(bound.id, True)
    assert preloaded.plays == 1
    assert preloaded.positions == [0]
    assert shared.plays == 0

    # A favorite without a binding still goes through the shared player.
    window._play_sound(unbound.id, True)
    assert shared.plays == 1

    window._release_hotkey_players()
    assert window._hotkey_players == {}

    window._allow_close = True
    window.close()


def test_update_panel_matches_the_asset_to_the_install_mode(
    qapp: QApplication, tmp_path: Path, monkeypatch
) -> None:
    """The panel must offer the right file, and never a stale one."""

    import soundmaster.ui.update_settings as panel_module
    from soundmaster.core.updater import InstallKind, ReleaseAsset, ReleaseInfo

    paths = _paths(tmp_path)
    window = MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())
    panel = window.update_panel
    newer = ReleaseInfo(
        tag="v9.9.9",
        name="n",
        notes="n",
        page_url="https://example.com/r",
        assets=(
            ReleaseAsset("SoundMaster-v9.9.9-Setup.exe", "https://e/exe", 43_143_366),
            ReleaseAsset("SoundMaster-v9.9.9-Portable.zip", "https://e/zip", 60_803_544),
        ),
    )

    monkeypatch.setattr(panel_module, "install_kind", lambda: InstallKind.INSTALLER)
    panel._check_finished(newer)
    assert panel._asset.name.endswith("Setup.exe")

    monkeypatch.setattr(panel_module, "install_kind", lambda: InstallKind.PORTABLE)
    panel._check_finished(newer)
    assert panel._asset.name.endswith("Portable.zip")

    # A source checkout is told to use git, and gets no installer offer.
    monkeypatch.setattr(panel_module, "install_kind", lambda: InstallKind.SOURCE)
    panel._check_finished(newer)
    assert "git pull" in panel.status_label.text()
    assert panel.install_button.isVisible() is False

    # Already up to date: no asset may stay armed from the previous check.
    monkeypatch.setattr(panel_module, "install_kind", lambda: InstallKind.INSTALLER)
    panel._check_finished(
        ReleaseInfo(tag="v0.0.1", name="old", notes="", page_url="https://e", assets=())
    )
    assert panel._asset is None
    assert panel.install_button.isVisible() is False
    assert "à jour" in panel.status_label.text()

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
    assert card.preview_button.text() == "▶ Tester"

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


def test_language_choice_offers_every_pocket_bundle_and_survives_a_save(
    qapp: QApplication, tmp_path: Path
) -> None:
    from soundmaster.core.tts import POCKET_LANGUAGE_BUNDLES, pocket_language_bundle

    window = _unlocked_window(tmp_path)
    tokens = [
        window.voice_language.itemData(index)
        for index in range(window.voice_language.count())
    ]
    # A French application must not silently clone with the English model.
    assert tokens[0] == "French"
    assert "Auto" in tokens
    # Every published Pocket TTS language must be reachable from the UI.
    assert set(POCKET_LANGUAGE_BUNDLES).issubset(set(tokens))
    for token in tokens:
        assert pocket_language_bundle(token) is not None

    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"RIFF")
    window._start_new_voice_profile()
    window.voice_profile_name.setText("Voix française")
    window.voice_sample.setText(str(sample))
    window.voice_language.setCurrentIndex(window.voice_language.findData("French"))
    window.voice_high_quality.setChecked(True)
    window._save_voice_profile()

    profile = window.library.voice_profiles()[0]
    # The canonical token is stored, not the translated label.
    assert profile.language == "French"
    assert profile.settings["pocket_high_quality"] is True
    assert pocket_language_bundle(profile.language, True) == "french_24l"

    # Reloading the saved voice must restore both, whatever the editor shows.
    window.voice_language.setCurrentIndex(0)
    window.voice_high_quality.setChecked(False)
    window._voice_profile_changed(window.voice_profile_combo.currentIndex())
    assert window._voice_language() == "French"
    assert window.voice_high_quality.isChecked() is True

    window._allow_close = True
    window.close()


def test_pocket_only_controls_hide_for_the_other_engines(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = _unlocked_window(tmp_path)
    window.show()
    window._select_page(1)
    window.voice_advanced_button.setChecked(True)
    qapp.processEvents()

    assert window.voice_engine.currentData() == "pocket-tts"
    assert window.voice_high_quality.isVisibleTo(window) is True
    assert window.voice_quantize.isVisibleTo(window) is True

    window.voice_engine.setCurrentIndex(window.voice_engine.findData("qwen3-tts"))
    qapp.processEvents()
    assert window.voice_high_quality.isVisibleTo(window) is False
    assert window.voice_quantize.isVisibleTo(window) is False
    assert window.voice_reference_text.isEnabled() is True

    window._allow_close = True
    window.close()
