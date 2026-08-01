"""Inline audio player used wherever SoundMaster must let you hear a file.

The voice workspace needs to play a freshly recorded sample and a freshly
generated result without leaving the page. Each bar owns its own player so the
soundboard and the Myinstants previews keep their independent playing states.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:  # pragma: no cover - optional platform runtime
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
except ImportError:  # pragma: no cover - optional platform runtime
    QAudioOutput = None  # type: ignore[assignment,misc]
    QMediaPlayer = None  # type: ignore[assignment,misc]

UNAVAILABLE_HINT = "Lecture indisponible : QtMultimedia n’est pas installé."


def format_duration(milliseconds: int) -> str:
    """Return ``mm:ss`` for a millisecond position, clamped at zero."""

    seconds = max(0, int(milliseconds)) // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class AudioPreviewBar(QWidget):
    """Play, scrub, and stop one local audio file without leaving the page."""

    started = pyqtSignal()
    stopped = pyqtSignal()

    def __init__(
        self,
        placeholder: str = "Aucun audio",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("playerBar")
        # A QWidget subclass only paints its stylesheet surface with this set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._placeholder = placeholder
        self._path: Path | None = None
        self._scrubbing = False
        self._player = None
        self._output = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("playerButton")
        self.play_button.setFixedWidth(44)
        self.play_button.setToolTip("Écouter")
        self.play_button.clicked.connect(self.toggle)
        top.addWidget(self.play_button)
        self.title_label = QLabel(placeholder)
        self.title_label.setObjectName("playerTitle")
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        top.addWidget(self.title_label, 1)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("playerTime")
        top.addWidget(self.time_label)
        layout.addLayout(top)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("playerSlider")
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(self._scrub_started)
        self.slider.sliderReleased.connect(self._scrub_finished)
        layout.addWidget(self.slider)

        if QMediaPlayer is not None and QAudioOutput is not None:
            self._output = QAudioOutput(self)
            self._output.setVolume(1.0)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._output)
            self._player.positionChanged.connect(self._position_changed)
            self._player.durationChanged.connect(self._duration_changed)
            self._player.playbackStateChanged.connect(self._playback_state_changed)
            self._player.errorOccurred.connect(self._playback_error)
        else:
            self.play_button.setToolTip(UNAVAILABLE_HINT)
        self.set_source(None)

    # -- public API ---------------------------------------------------------

    def has_source(self) -> bool:
        return self._path is not None

    def source_path(self) -> Path | None:
        return self._path

    def is_playing(self) -> bool:
        if self._player is None or QMediaPlayer is None:
            return False
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def set_device(self, device: object | None) -> None:
        """Route previews to the headset device chosen in the settings."""

        if self._output is not None and device is not None:
            self._output.setDevice(device)

    def set_source(self, path: Path | str | None, title: str | None = None) -> None:
        """Load a file, or clear the bar back to its empty state."""

        self.stop()
        candidate = Path(path) if path else None
        if candidate is None or not candidate.is_file():
            self._path = None
            self.title_label.setText(self._placeholder)
            self.title_label.setToolTip("")
            self.play_button.setEnabled(False)
            self.slider.setEnabled(False)
            self.slider.setRange(0, 0)
            self.slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")
            return
        self._path = candidate
        self.title_label.setText(title or candidate.name)
        self.title_label.setToolTip(str(candidate))
        self.play_button.setEnabled(self._player is not None)
        self.slider.setEnabled(self._player is not None)
        self.time_label.setText("00:00 / 00:00")
        if self._player is not None:
            self._player.setSource(QUrl.fromLocalFile(str(candidate)))

    def play(self) -> None:
        if self._player is None or self._path is None:
            return
        self._player.play()

    def stop(self) -> None:
        if self._player is None:
            return
        self._player.stop()
        self.slider.setValue(0)

    def toggle(self) -> None:
        if self.is_playing():
            self.stop()
        else:
            self.play()

    # -- internals ----------------------------------------------------------

    def _scrub_started(self) -> None:
        self._scrubbing = True

    def _scrub_finished(self) -> None:
        self._scrubbing = False
        if self._player is not None:
            self._player.setPosition(self.slider.value())

    def _position_changed(self, position: int) -> None:
        if not self._scrubbing:
            self.slider.setValue(position)
        self.time_label.setText(
            f"{format_duration(position)} / {format_duration(self.slider.maximum())}"
        )

    def _duration_changed(self, duration: int) -> None:
        self.slider.setRange(0, max(0, duration))
        self.time_label.setText(f"00:00 / {format_duration(duration)}")

    def _playback_state_changed(self, state) -> None:
        if QMediaPlayer is None:
            return
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("■" if playing else "▶")
        self.play_button.setToolTip("Arrêter" if playing else "Écouter")
        if playing:
            self.started.emit()
        else:
            self.stopped.emit()
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self.slider.setValue(0)

    def _playback_error(self, _error, message: str = "") -> None:
        self.time_label.setText("Illisible")
        self.title_label.setToolTip(
            message or "Ce fichier audio ne peut pas être lu sur cette installation."
        )
