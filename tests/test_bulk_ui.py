import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")
from PyQt6.QtWidgets import QApplication

from soundmaster.core.config import AppConfig, AppPaths
from soundmaster.core.legal import LegalProfile
from soundmaster.core.myinstants import MyInstantResult
from soundmaster.ui.main_window import MainWindow


@pytest.fixture
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(tmp_path: Path) -> MainWindow:
    data = tmp_path / "data"
    paths = AppPaths(
        data_dir=data,
        database=data / "soundmaster.db",
        legal_profile=data / "legal.json",
        models=data / "models",
        audio_cache=data / "audio-cache",
        voice_samples=data / "voice-samples",
        logs=data / "logs",
    )
    return MainWindow(LegalProfile(), paths.legal_profile, paths, AppConfig())


def test_opening_myinstants_page_starts_catalog_load(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(tmp_path)
    started: list[bool] = []
    monkeypatch.setattr(window, "_search_myinstants", lambda: started.append(True))

    window._select_page(2)

    assert started == [True]
    assert window.page_title.text() == "Explorateur Myinstants"

    window._allow_close = True
    window.close()


def test_myinstants_preview_streams_without_creating_a_download_job(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = _window(tmp_path)
    result = MyInstantResult(
        "Streamed Airhorn",
        "https://www.myinstants.com/en/instant/streamed-airhorn/",
        "https://www.myinstants.com/media/sounds/streamed-airhorn.mp3",
    )
    played: list[str] = []
    monkeypatch.setattr(window, "_play_remote", lambda url, **_kwargs: played.append(url))

    assert window._download_myinstant(result, False) is True
    assert played == [result.audio_url]
    assert result.audio_url not in window._download_jobs
    assert not hasattr(window, "myinstants_rights")

    window._allow_close = True
    window.close()


def test_myinstants_page_can_render_catalog_results(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(tmp_path)
    result = MyInstantResult(
        "Popular Airhorn",
        "https://www.myinstants.com/en/instant/popular-airhorn/",
        "https://www.myinstants.com/media/sounds/popular-airhorn.mp3",
    )

    window._search_finished([result])

    assert window._myinstants_catalog_loaded is True
    assert window.myinstants_grid.count() == 1
    assert window._myinstant_cards[result.audio_url].result == result

    window._allow_close = True
    window.close()


def test_myinstants_selection_updates_bulk_action(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(tmp_path)
    result = MyInstantResult(
        "DJ Airhorn",
        "https://www.myinstants.com/en/instant/dj-airhorn/",
        "https://www.myinstants.com/media/sounds/dj-airhorn.mp3",
    )

    window._search_finished([result])
    card = window._myinstant_cards[result.audio_url]
    assert window.favorite_selected_myinstants.isEnabled() is False

    card.set_selected(True)
    assert window._selected_myinstants == {result.audio_url: result}
    assert window.favorite_selected_myinstants.isEnabled() is True
    assert window.myinstants_selection_status.text() == "1 son sélectionné"

    card.set_selected(False)
    assert window._selected_myinstants == {}
    assert window.favorite_selected_myinstants.isEnabled() is False

    window._allow_close = True
    window.close()


def test_bulk_state_disables_card_and_selection_controls(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(tmp_path)
    result = MyInstantResult(
        "Sound",
        "https://www.myinstants.com/en/instant/sound/",
        "https://www.myinstants.com/media/sounds/sound.mp3",
    )
    window._search_finished([result])
    card = window._myinstant_cards[result.audio_url]

    window._set_myinstants_cards_enabled(False)
    assert card.preview_button.isEnabled() is False
    assert card.favorite_button.isEnabled() is False
    assert card.select_check.isEnabled() is False
    assert window.select_all_myinstants.isEnabled() is False
    assert window.clear_myinstants_selection.isEnabled() is False

    window._set_myinstants_cards_enabled(True)
    assert card.preview_button.isEnabled() is True
    assert card.favorite_button.isEnabled() is True
    assert card.select_check.isEnabled() is True

    window._allow_close = True
    window.close()


def test_bulk_progress_reports_partial_failure(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(tmp_path)
    first = "https://www.myinstants.com/media/sounds/first.mp3"
    second = "https://www.myinstants.com/media/sounds/second.mp3"
    window._bulk_active = True
    window._bulk_job_ids = {first, second}
    window._bulk_total = 2

    window._bulk_download_finished(first, False)
    assert window._bulk_active is True
    assert window._bulk_completed == 1
    assert window._bulk_failed == 1
    assert window.bulk_download_progress.value() == 50

    window._bulk_download_finished(second, True)
    assert window._bulk_active is False
    assert window._bulk_completed == 2
    assert window._bulk_failed == 1
    assert window.bulk_download_progress.isHidden()
    assert "1 échec" in window.myinstants_status.text()

    window._allow_close = True
    window.close()


def test_select_all_and_clear_selection(qapp: QApplication, tmp_path: Path) -> None:
    window = _window(tmp_path)
    results = [
        MyInstantResult(
            f"Sound {index}",
            f"https://www.myinstants.com/en/instant/sound-{index}/",
            f"https://www.myinstants.com/media/sounds/sound-{index}.mp3",
        )
        for index in range(2)
    ]

    window._search_finished(results)
    window._select_all_myinstants()
    assert set(window._selected_myinstants) == {result.audio_url for result in results}
    assert window.myinstants_selection_status.text() == "2 sons sélectionnés"

    window._clear_myinstants_selection()
    assert window._selected_myinstants == {}
    assert window.myinstants_selection_status.text() == "0 son sélectionné"

    window._allow_close = True
    window.close()
