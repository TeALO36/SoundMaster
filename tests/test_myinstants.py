from pathlib import Path
from typing import Self

import pytest

from soundmaster.core.myinstants import (
    MAX_DOWNLOAD_BYTES,
    MyInstantResult,
    MyInstantsError,
    cache_audio,
    parse_search_html,
)


def test_empty_query_loads_the_official_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b'<div class="instant"><button onclick="play(\'/media/sounds/airhorn.mp3\')"></button><a href="/en/instant/airhorn/">Airhorn</a></div>'

    requested: list[str] = []

    def fake_urlopen(request, **_kwargs):
        requested.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    from soundmaster.core.myinstants import search_myinstants

    results = search_myinstants("")

    assert requested == ["https://www.myinstants.com/en/index/us/"]
    assert [result.title for result in results] == ["Airhorn"]


def test_parse_current_myinstants_instant_markup() -> None:
    html = """
    <div class="instant">
      <button onclick="play('/media/sounds/dj-airhorn-sound-effect.mp3', 'loader-1', 'dj-airhorn')"></button>
      <a href="/en/instant/dj-airhorn/" class="instant-link">DJ Airhorn</a>
    </div>
    """

    results = parse_search_html(html, "https://www.myinstants.com")

    assert results == [
        MyInstantResult(
            "DJ Airhorn",
            "https://www.myinstants.com/en/instant/dj-airhorn/",
            "https://www.myinstants.com/media/sounds/dj-airhorn-sound-effect.mp3",
        )
    ]


def test_parse_search_html_supports_data_audio_and_onclick_markup() -> None:
    html = """
    <article class="instant">
      <a href="/en/instant/dj-airhorn/">DJ Airhorn</a>
      <button data-audio="/media/sounds/dj-airhorn.mp3">play</button>
    </article>
    <div class="instant">
      <a href="/en/instant/robot/">Robot</a>
      <button onclick="playSound('/media/sounds/robot.ogg')">play</button>
    </div>
    """

    results = parse_search_html(html, "https://www.myinstants.com")

    assert [result.title for result in results] == ["DJ Airhorn", "Robot"]
    assert results[0].audio_url.endswith("/media/sounds/dj-airhorn.mp3")
    assert results[1].audio_url.endswith("/media/sounds/robot.ogg")


def test_cache_audio_requires_rights_acknowledgement(tmp_path: Path) -> None:
    result = MyInstantResult("Test", "https://www.myinstants.com/en/instant/test/", "https://www.myinstants.com/media/sounds/test.mp3")

    with pytest.raises(MyInstantsError, match="droits"):
        cache_audio(result, tmp_path, False)


def test_cache_audio_allows_official_myinstants_subdomains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.headers = {"Content-Length": "4"}

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://media.myinstants.com/media/sounds/test.mp3"

        def read(self, _size: int) -> bytes:
            if not hasattr(self, "done"):
                self.done = True
                return b"test"
            return b""

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    result = MyInstantResult(
        "Test",
        "https://www.myinstants.com/en/instant/test/",
        "https://media.myinstants.com/media/sounds/test.mp3",
    )

    path = cache_audio(result, tmp_path, True)

    assert path.read_bytes() == b"test"


def test_cache_audio_rejects_non_myinstants_hosts(tmp_path: Path) -> None:
    result = MyInstantResult("Test", "https://www.myinstants.com/en/instant/test/", "https://evil.example/test.mp3")

    with pytest.raises(MyInstantsError, match="HTTPS"):
        cache_audio(result, tmp_path, True)


def test_cache_audio_reports_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.headers = {"Content-Length": "4"}

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://www.myinstants.com/media/sounds/test.mp3"

        def read(self, _size: int) -> bytes:
            if not hasattr(self, "done"):
                self.done = True
                return b"test"
            return b""

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    progress: list[tuple[int, int]] = []
    result = MyInstantResult("Test", "https://www.myinstants.com/en/instant/test/", "https://www.myinstants.com/media/sounds/test.mp3")

    cache_audio(result, tmp_path, True, lambda completed, total: progress.append((completed, total)))

    assert progress[0] == (0, 4)
    assert progress[-1] == (4, 4)


def test_cache_audio_enforces_download_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeResponse:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b"x" * (MAX_DOWNLOAD_BYTES + 1)

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    result = MyInstantResult("Test", "https://www.myinstants.com/en/instant/test/", "https://www.myinstants.com/media/sounds/test.mp3")

    with pytest.raises(MyInstantsError, match="25 Mo"):
        cache_audio(result, tmp_path, True)
    assert list(tmp_path.iterdir()) == []


def test_myinstant_card_toggles_favorite_state() -> None:
    from PyQt6.QtWidgets import QApplication
    from soundmaster.ui.myinstants_widgets import MyInstantCard

    _app = QApplication.instance() or QApplication([])

    result = MyInstantResult(
        "Airhorn",
        "https://www.myinstants.com/en/instant/airhorn/",
        "https://www.myinstants.com/media/sounds/airhorn.mp3",
    )
    card = MyInstantCard(result)

    assert "Ajouter" in card.favorite_button.text()
    assert card._is_favorite is False

    events: list[str] = []
    card.favorite_requested.connect(lambda _res: events.append("add"))
    card.remove_favorite_requested.connect(lambda _res: events.append("remove"))

    card.favorite_button.click()
    assert events == ["add"]

    card.set_is_favorite(True)
    assert "Supprimer" in card.favorite_button.text()
    assert card._is_favorite is True

    card.favorite_button.click()
    assert events == ["add", "remove"]
