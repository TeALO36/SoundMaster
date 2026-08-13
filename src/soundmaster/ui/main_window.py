"""Main SoundMaster desktop shell and embedded local-first feature UI."""

from __future__ import annotations

import importlib.util
import shutil
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, ClassVar

from PyQt6.QtCore import QEvent, QObject, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from soundmaster.core.audio_capture import SystemAudioRecorder, wasapi_output_devices
from soundmaster.core.config import AppConfig, AppPaths
from soundmaster.core.f5_emotions import (
    EMOTION_FORMAT_PROPERTY,
    F5_EMOTION_BY_KEY,
    F5_EMOTIONS,
    EmotionSpan,
    render_emotion_tags,
)
from soundmaster.core.fast_audio import FastAudioEngine
from soundmaster.core.media import (
    VideoAudioExtractionError,
    extract_audio_from_video,
    is_video_file,
    sample_destination,
)
from soundmaster.core.models import (
    MODEL_PROFILES,
    ModelProfile,
    delete_model,
    download_model,
    get_profile,
    is_downloaded,
    model_directory,
    model_size_str,
    set_model_directory,
)
from soundmaster.core.myinstants import (
    MyInstantResult,
    MyInstantsError,
    cache_audio,
    search_myinstants,
)
from soundmaster.core.pocket_mirror import (
    DEFAULT_MIRROR_REPO,
    MIRROR_PREFERENCE_KEY,
)
from soundmaster.core.tts import (
    POCKET_GATED_HINT,
    QwenVoiceService,
    VoiceGenerationError,
    is_engine_runtime_installed,
    pocket_has_quality_variant,
    pocket_weights_cached,
)
from soundmaster.data.library import SoundItem, SoundLibrary
from soundmaster.hotkeys import HotkeyManager
from soundmaster.resources import get_app_icon, get_icon, get_settings_icon
from soundmaster.ui.audio_preview import AudioPreviewBar
from soundmaster.ui.legal_settings import LegalSettingsWidget
from soundmaster.ui.myinstants_widgets import MyInstantCard
from soundmaster.ui.theme import APP_STYLE, animate_opacity
from soundmaster.ui.update_settings import UpdateSettingsPanel
from soundmaster.ui.voice_consent import CONSENT_PREFERENCE_KEY, VoiceConsentPanel

if TYPE_CHECKING:
    from soundmaster.core.legal import LegalProfile

try:
    from PyQt6.QtMultimedia import (
        QAudioInput,
        QAudioOutput,
        QMediaCaptureSession,
        QMediaDevices,
        QMediaFormat,
        QMediaPlayer,
        QMediaRecorder,
    )
except ImportError:  # pragma: no cover - optional platform runtime
    QAudioInput = None  # type: ignore[assignment,misc]
    QAudioOutput = None  # type: ignore[assignment,misc]
    QMediaCaptureSession = None  # type: ignore[assignment,misc]
    QMediaDevices = None  # type: ignore[assignment,misc]
    QMediaFormat = None  # type: ignore[assignment,misc]
    QMediaPlayer = None  # type: ignore[assignment,misc]
    QMediaRecorder = None  # type: ignore[assignment,misc]


# One language choice drives every engine: Pocket TTS loads its dedicated
# bundle, Qwen3-TTS / OmniVoice use it at generation time, and "Auto" lets
# each engine pick its own default. The visible label is French; the data is
# the canonical token shared with the saved voices and the engines.
VOICE_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("Français", "French"),
    ("English", "English"),
    ("Deutsch", "German"),
    ("Español", "Spanish"),
    ("Italiano", "Italian"),
    ("Português", "Portuguese"),
    ("Auto (anglais par défaut)", "Auto"),
)
DEFAULT_LANGUAGE_PREFERENCE = "default_language"
MODEL_DIRECTORY_PREFERENCE = "model_directory"


def _module_available(module_name: str) -> bool:
    """Check an optional module without allowing broken import metadata to escape."""

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def collect_gpu_diagnostics(paths: AppPaths) -> str:
    """Return actionable local TTS/GPU diagnostics without importing torch at startup.

    Pocket TTS is the default engine and runs on the CPU with no GPU and no
    PyTorch, so a missing CUDA stack is not an error on a fresh install: the
    report focuses on what the user actually needs for their chosen engine.
    """

    pocket_runtime = _module_available("pocket_tts")
    qwen_runtime = _module_available("qwen_tts")
    soundfile_runtime = _module_available("soundfile")
    qwen_model_ready = is_downloaded(get_profile("qwen3-tts"), paths)
    lines = [
        (
            "Moteur par défaut (Pocket TTS) : installé — CPU uniquement, sans GPU ni PyTorch."
            if pocket_runtime
            else "Moteur par défaut (Pocket TTS) : absent — installez l’extra : "
            "python -m pip install \"soundmaster[pocket]\"."
        ),
        f"Runtime Qwen3-TTS (optionnel) : {'installé' if qwen_runtime else 'non installé'}",
        f"Modèle Qwen local : {'prêt' if qwen_model_ready else 'non téléchargé'}",
        f"Décodage audio basse latence : {'disponible' if soundfile_runtime else 'absent — relancez l’installation pour la lecture instantanée'}",
    ]
    try:
        import torch
    except ImportError:
        lines.append(
            "PyTorch : non installé (normal — il n’est utile que pour Qwen3-TTS, OmniVoice ou F5-TTS)."
        )
        if qwen_runtime or _module_available("f5_tts"):
            lines.append("Action : lancez setup_gpu.bat (NVIDIA) ou setup_amd.bat (AMD), sinon installez l’extra CPU.")
        return "\n".join(lines)

    hip_version = getattr(torch.version, "hip", None)
    if hip_version:
        lines.extend(
            (
                f"PyTorch : {torch.__version__} (ROCm {hip_version}) — accélération AMD détectée",
                "GPU AMD : support ROCm actif, génération accélérée disponible.",
            )
        )
        return "\n".join(lines)

    lines.append(f"PyTorch : {torch.__version__}")
    if not torch.cuda.is_available():
        lines.append("Accélération : CPU — ni CUDA ni ROCm détectés, génération plus lente.")
        lines.append("Action : installez les pilotes NVIDIA puis lancez setup_gpu.bat, ou les pilotes AMD puis setup_amd.bat.")
        return "\n".join(lines)

    device = torch.cuda.current_device()
    properties = torch.cuda.get_device_properties(device)
    total_gb = properties.total_memory / (1024**3)
    allocated_gb = torch.cuda.memory_allocated(device) / (1024**3)
    reserved_gb = torch.cuda.memory_reserved(device) / (1024**3)
    bf16 = "oui" if torch.cuda.is_bf16_supported() else "non (FP16 utilisé)"
    lines.extend(
        (
            f"GPU : {properties.name}",
            f"VRAM : {total_gb:.1f} Go total · {allocated_gb:.1f} Go utilisée · {reserved_gb:.1f} Go réservée",
            f"CUDA : {torch.version.cuda or 'inconnue'} · BF16 : {bf16}",
            "Mode : CUDA + BF16/FP16 + inference_mode",
        )
    )
    return "\n".join(lines)


class EmotionTextEdit(QTextEdit):
    """Text editor that reports when a mouse selection has been completed."""

    selection_finished = pyqtSignal()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.selection_finished.emit()

    def keyReleaseEvent(self, event) -> None:
        super().keyReleaseEvent(event)
        if self.textCursor().hasSelection():
            self.selection_finished.emit()


class WheelScrollComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel events while the popup is closed.

    Without this, hovering a combo box (the model list, the language picker)
    while scrolling the page silently changes the selected item — the user
    scrolls the page and the language flips under the cursor. The wheel event
    is ignored so it propagates to the enclosing scroll area instead.
    """

    def wheelEvent(self, event) -> None:
        if not self.view().isVisible():
            event.ignore()
            return
        super().wheelEvent(event)


class ShortcutCaptureButton(QPushButton):
    """Button that records one keyboard combination when the user presses it."""

    shortcut_recorded = pyqtSignal(str)

    _MODIFIER_KEYS: ClassVar[set[Qt.Key]] = {
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    }

    def __init__(self, sequence: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shortcutCaptureButton")
        self.sequence = sequence.strip()
        self._recording = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_text()

    @property
    def recording(self) -> bool:
        return self._recording

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_recording()
        super().mousePressEvent(event)

    def start_recording(self) -> None:
        self._recording = True
        self.setFocus()
        self.grabKeyboard()
        self.setObjectName("recordingButton")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("Appuyez sur les touches…")
        self.setToolTip("Appuyez simultanément sur les touches, ou Échap pour annuler")

    def cancel_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self.releaseKeyboard()
        self.setObjectName("")
        self._update_text()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_recording()
            event.accept()
            return
        if event.key() in self._MODIFIER_KEYS:
            event.accept()
            return
        sequence = QKeySequence(
            event.modifiers().value | int(event.key())
        ).toString(QKeySequence.SequenceFormat.PortableText)
        sequence = self._normalise(sequence)
        if sequence:
            self._recording = False
            self.releaseKeyboard()
            self.setObjectName("")
            self.sequence = sequence
            self._update_text()
            self.shortcut_recorded.emit(sequence)
        event.accept()

    @staticmethod
    def _normalise(sequence: str) -> str:
        """Use the lowercase syntax accepted by the ``keyboard`` package."""

        parts = [part.strip() for part in sequence.replace("Meta", "Windows").split("+")]
        return "+".join(part.lower() for part in parts if part)

    def _update_text(self) -> None:
        self.setText(self.sequence or "Cliquer puis appuyer…")
        self.setToolTip(
            "Cliquer puis appuyer sur une combinaison"
            if not self.sequence
            else f"Raccourci enregistré : {self.sequence} · Cliquer pour remplacer"
        )


class SoundCard(QWidget):
    """Local sound card with separate headset and virtual-output actions."""

    play_requested = pyqtSignal(int, bool)
    stop_requested = pyqtSignal(int)
    favorite_changed = pyqtSignal(int, bool)
    rename_requested = pyqtSignal(int)
    preview_hovered = pyqtSignal(int)

    def __init__(self, item: SoundItem, keybind: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self._preview_playing = False
        layout = QVBoxLayout(self)
        self.title_label = QLabel(f"<b>{item.title}</b>")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        shortcut_text = keybind if keybind else "Aucun raccourci"
        metadata = QLabel(f"{item.source} · {shortcut_text}")
        metadata.setObjectName("muted")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)
        # Two rows of labelled actions: icon-only buttons were unreadable at
        # this size, and every action here needs to be obvious.
        primary = QHBoxLayout()
        primary.setSpacing(6)
        self.preview_button = QPushButton("▶ Tester")
        self.preview_button.setObjectName("compactButton")
        self.preview_button.setToolTip("Lire dans le casque")
        self.preview_button.installEventFilter(self)
        self.preview_button.clicked.connect(self._toggle_preview)
        self.send_button = QPushButton("Envoyer")
        self.send_button.setObjectName("compactButton")
        self.send_button.setToolTip("Lire vers la sortie 2 sélectionnée")
        self.send_button.installEventFilter(self)
        self.send_button.clicked.connect(lambda: self.play_requested.emit(item.id, True))
        primary.addWidget(self.preview_button, 1)
        primary.addWidget(self.send_button, 1)
        layout.addLayout(primary)

        secondary = QHBoxLayout()
        secondary.setSpacing(6)
        self.favorite_button = QPushButton()
        self.favorite_button.setObjectName("compactButton")
        self.favorite_button.setCheckable(True)
        self.favorite_button.setChecked(item.favorite)
        self._apply_favorite_label(item.favorite)
        self.favorite_button.clicked.connect(self._favorite_clicked)
        self.rename_button = QPushButton("Renommer")
        self.rename_button.setObjectName("compactButton")
        self.rename_button.setToolTip("Changer le nom affiché de ce son")
        self.rename_button.clicked.connect(lambda: self.rename_requested.emit(item.id))
        secondary.addWidget(self.favorite_button, 1)
        secondary.addWidget(self.rename_button, 1)
        layout.addLayout(secondary)
        self.setObjectName("soundCard")

    def _apply_favorite_label(self, favorite: bool) -> None:
        self.favorite_button.setText("★ Favori" if favorite else "☆ Favori")
        self.favorite_button.setToolTip(
            "Retirer des favoris" if favorite else "Ajouter aux favoris pour un accès hors ligne"
        )

    def _favorite_clicked(self, checked: bool) -> None:
        self._apply_favorite_label(checked)
        self.favorite_changed.emit(self.item.id, checked)

    def eventFilter(self, watched, event) -> bool:
        if watched in (self.preview_button, self.send_button) and event.type() == QEvent.Type.Enter:
            # Resolve and buffer the file while the pointer is still travelling,
            # so the click only has to issue play().
            self.preview_hovered.emit(self.item.id)
        return super().eventFilter(watched, event)

    def _toggle_preview(self) -> None:
        if self._preview_playing:
            self.stop_requested.emit(self.item.id)
        else:
            self.play_requested.emit(self.item.id, False)

    def set_preview_playing(self, playing: bool) -> None:
        self._preview_playing = playing
        self.preview_button.setText("■ Stop" if playing else "▶ Tester")
        self.preview_button.setToolTip("Arrêter la lecture" if playing else "Lire dans le casque")

class SearchWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, query: str) -> None:
        super().__init__()
        self.query = query

    def run(self) -> None:
        try:
            self.finished.emit(search_myinstants(self.query))
        except MyInstantsError as error:
            self.failed.emit(str(error))


class DownloadWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, result: MyInstantResult, cache_dir: Path) -> None:
        super().__init__()
        self.result = result
        self.cache_dir = cache_dir

    def run(self) -> None:
        try:
            path = cache_audio(
                self.result,
                self.cache_dir,
                True,
                lambda completed, total: self.progress.emit(completed, total),
            )
            self.finished.emit(str(path))
        except MyInstantsError as error:
            self.failed.emit(str(error))


class DownloadProgressRow(QWidget):
    """Compact live status row for one independent Myinstants transfer."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("downloadRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        header = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setWordWrap(True)
        self.status = QLabel("Préparation…")
        self.status.setObjectName("muted")
        header.addWidget(self.title, 1)
        header.addWidget(self.status)
        layout.addLayout(header)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

    def set_progress(self, completed: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(completed * 100 / total)))
            self.status.setText(f"{self.progress.value()} %")
        else:
            self.progress.setRange(0, 0)
            self.status.setText("Téléchargement…")

    def set_finished(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText("Prêt hors ligne")

    def set_failed(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText("Échec")


class ModelDownloadThread(QThread):
    finished_signal = pyqtSignal(bool, str, str)
    # Emitted after each file: (downloaded_bytes, total_bytes, filename).
    progress_signal = pyqtSignal(int, int, str)

    def __init__(self, profile: ModelProfile, paths: AppPaths, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.paths = paths

    def run(self) -> None:
        try:
            download_model(
                self.profile, self.paths, progress=self._report_progress
            )
            self.finished_signal.emit(True, self.profile.key, f"Téléchargement du modèle {self.profile.key} terminé avec succès !")
        except Exception as err:
            self.finished_signal.emit(False, self.profile.key, str(err))

    def _report_progress(self, downloaded: int, total: int, filename: str) -> None:
        self.progress_signal.emit(downloaded, total, filename)


class PocketInstallThread(QThread):
    """Download the Pocket TTS weights through the runtime's own loader.

    Loading the model is what triggers the weight download, so this runs on a
    worker thread. A success is only reported when the voice-cloning weights of
    the gated ``kyutai/pocket-tts`` repository actually landed in the cache:
    the runtime otherwise silently falls back to a build that cannot clone.
    """

    finished_signal = pyqtSignal(bool, str)

    def __init__(
        self,
        service: QwenVoiceService,
        language: str,
        settings: dict[str, object] | None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.language = language
        self.settings = settings

    def run(self) -> None:
        try:
            self.service.preload_pocket_tts(self.language, self.settings)
            if not pocket_weights_cached():
                raise VoiceGenerationError(POCKET_GATED_HINT)
            self.finished_signal.emit(
                True,
                "Pocket TTS installé : les poids vocaux sont prêts à l'emploi.",
            )
        except Exception as error:  # noqa: BLE001 - surfaced to the UI dialog.
            self.finished_signal.emit(False, str(error))


class VoiceWorker(QObject):
    finished = pyqtSignal(str, str, str, str, str, float)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: QwenVoiceService,
        text: str,
        sample: Path,
        ref_text: str,
        output: Path,
        language: str,
        engine_key: str,
        model_name: str,
        settings: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        self.service, self.text, self.sample = service, text, sample
        self.ref_text, self.output, self.language, self.engine_key = (
            ref_text,
            output,
            language,
            engine_key,
        )
        self.model_name = model_name
        self.settings = settings or {}

    def run(self) -> None:
        import time

        start_time = time.perf_counter()
        try:
            arguments = (
                self.text,
                self.sample,
                self.ref_text,
                self.output,
                self.language,
                self.engine_key,
            )
            # Keep the worker compatible with lightweight integrations and older
            # service adapters when no advanced controls were requested.
            result = (
                self.service.generate_clone(*arguments, self.settings)
                if self.settings
                else self.service.generate_clone(*arguments)
            )
        except VoiceGenerationError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - optional third-party boundary.
            self.failed.emit(f"Erreur inattendue du moteur vocal : {error}")
        else:
            elapsed = time.perf_counter() - start_time
            self.finished.emit(
                str(result),
                self.engine_key,
                self.model_name,
                self.text,
                str(self.sample),
                elapsed,
            )


class MainWindow(QMainWindow):
    """Full French application shell with embedded local workflows."""

    hotkey_play_requested = pyqtSignal(int)
    # Fired (via a queued connection) when the zero-latency engine finishes
    # playing the headset output, so the "Stop" state on the cards is released.
    _fast_audio_finished = pyqtSignal()

    _MIC_BUTTON_LABEL = "● Enregistrer au micro"
    _SYSTEM_BUTTON_LABEL = "◉ Capturer la sortie audio"
    _MIC_BUTTON_HINT = "Enregistrer un échantillon de 3 à 10 secondes avec le microphone"

    def __init__(self, legal_profile: LegalProfile, legal_profile_path: Path, paths: AppPaths, config: AppConfig) -> None:
        super().__init__()
        self.paths, self.config = paths, config
        self.library = SoundLibrary(paths.database)
        # Restore the user-chosen model folder (e.g. a second disk) before any
        # model status/size lookup runs.
        saved_model_dir = self.library.preference(MODEL_DIRECTORY_PREFERENCE, "")
        if saved_model_dir:
            set_model_directory(Path(saved_model_dir))
        self.legal_profile, self.legal_profile_path = legal_profile, legal_profile_path
        self._players: dict[bool, object] = {}
        self._player_sources: dict[bool, str] = {}
        self._hotkey_players: dict[int, tuple[object, object]] = {}
        self._favorite_players: dict[str, tuple[object, object]] = {}
        self._fast_audio = FastAudioEngine()
        # The engine callback runs on the audio thread; the signal marshals it
        # back to the UI thread so the "Stop" state on cards is released when
        # the last queued buffer finishes playing.
        self._fast_audio.set_completion_callback(self._fast_audio_finished.emit)
        self._fast_audio_finished.connect(self._on_fast_audio_finished)
        self._audio_outputs: dict[bool, object] = {}
        self._network_thread: QThread | None = None
        self._network_worker: QObject | None = None
        self._voice_thread: QThread | None = None
        self._voice_worker: VoiceWorker | None = None
        self._voice_service = QwenVoiceService(paths)
        self._active_voice_engine = "qwen3-tts"
        self._remote_preview_title: str | None = None
        self._remote_preview_url: str | None = None
        self._active_remote_preview_url: str | None = None
        self._remote_preview_warm_timer: QTimer | None = None
        self._active_preview_sound_id: int | None = None
        self._capture_session = None
        self._audio_input = None
        self._recorder = None
        self._recording_path: Path | None = None
        self._recording_poll_timer: QTimer | None = None
        self._system_recorder: SystemAudioRecorder | None = None
        self._system_recording_thread: Thread | None = None
        self._system_recording_path: Path | None = None
        self._system_record_poll_timer: QTimer | None = None
        self._download_jobs: dict[
            str, tuple[QThread, DownloadWorker, DownloadProgressRow, MyInstantResult, bool]
        ] = {}
        self._active_downloads: set[str] = set()
        self._myinstants_results: list[MyInstantResult] = []
        self._myinstants_catalog_loaded = False
        self._myinstant_cards: dict[str, MyInstantCard] = {}
        self._dashboard_cards: list[SoundCard] = []
        self._recent_cards: list[SoundCard] = []
        self._selected_myinstants: dict[str, MyInstantResult] = {}
        self._bulk_job_ids: set[str] = set()
        self._bulk_total = 0
        self._bulk_completed = 0
        self._bulk_failed = 0
        self._bulk_active = False
        self._voice_generation_ok = False
        self._voice_ui_generation = 0
        self._voice_consent_pending_redirect = False
        self._last_generation_path: Path | None = None
        self._last_generation_title = ""
        self._editing_voice_profile_id: int | None = None
        self._hotkeys = HotkeyManager()
        self.hotkey_play_requested.connect(lambda sound_id: self._play_sound(sound_id, True))
        if QMediaPlayer is not None and QAudioOutput is not None:
            for virtual in (False, True):
                output = QAudioOutput(self)
                output.setVolume(1.0)
                player = QMediaPlayer(self)
                player.setAudioOutput(output)
                player.errorOccurred.connect(
                    lambda _error, output_key=virtual: self._player_error(output_key)
                )
                if not virtual:
                    player.playbackStateChanged.connect(self._local_playback_state_changed)
                self._audio_outputs[virtual] = output
                self._players[virtual] = player
        self.setWindowTitle("SoundMaster — Soundboard local")
        self.setStyleSheet(APP_STYLE)
        self.resize(1180, 760)
        # The voice workspace needs a little vertical room for the editor and
        # its scrollable controls. Width stays compact; height remains usable
        # instead of silently crushing the editor and action bar.
        self.setMinimumSize(820, 680)
        self._build_shell()
        self._setup_recording()
        self._build_tray()
        self._apply_voice_lock_state()
        self._refresh_dashboard()
        self._refresh_voice_profiles()
        self._refresh_voice_history()

    def _build_shell(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(176)
        sidebar.setMaximumWidth(220)
        sidebar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.sidebar = sidebar
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 12, 12, 16)
        side_layout.setSpacing(4)
        brand = QLabel("◈ SoundMaster")
        brand.setObjectName("brandMark")
        brand.setContentsMargins(14, 18, 10, 2)
        side_layout.addWidget(brand)
        brand_meta = QLabel("LOCAL-FIRST SOUNDBOARD")
        brand_meta.setObjectName("brandMeta")
        brand_meta.setContentsMargins(14, 0, 10, 24)
        side_layout.addWidget(brand_meta)
        self.nav_buttons: list[QPushButton] = []
        entries = (("Tableau de bord", "⌂"), ("Clonage de voix", "◉"), ("Explorateur Myinstants", "♫"), ("Raccourcis", "⌘"))
        for index, (label, icon) in enumerate(entries):
            button = QPushButton(f"{icon}  {label}")
            button.setCheckable(True)
            button.setObjectName("navButton")
            button.clicked.connect(lambda _checked=False, i=index: self._select_page(i))
            self.nav_buttons.append(button)
            side_layout.addWidget(button)
        side_layout.addStretch(1)
        settings = QPushButton("Paramètres")
        settings_icon = get_settings_icon()
        if not settings_icon.isNull():
            settings.setIcon(settings_icon)
        settings.setObjectName("settingsButton")
        settings.clicked.connect(self._select_settings)
        side_layout.addWidget(settings)
        root_layout.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 22)
        content_layout.setSpacing(16)
        self.content = content
        title_block = QVBoxLayout()
        title_block.setSpacing(4)
        eyebrow = QLabel("SOUNDBOARD / LOCAL WORKSPACE")
        eyebrow.setObjectName("eyebrow")
        title_block.addWidget(eyebrow)
        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        title_block.addWidget(self.page_title)
        self.page_subtitle = QLabel("Un espace calme pour vos sons, vos voix et vos raccourcis.")
        self.page_subtitle.setObjectName("pageSubtitle")
        title_block.addWidget(self.page_subtitle)
        content_layout.addLayout(title_block)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._dashboard_page())
        self.pages.addWidget(self._voice_page())
        self.pages.addWidget(self._myinstants_page())
        self.pages.addWidget(self._keybinds_page())
        self.pages.addWidget(self._settings_page())
        content_layout.addWidget(self.pages, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)
        self._select_page(0)

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        toolbar = QHBoxLayout()
        self.dashboard_search = QLineEdit()
        self.dashboard_search.setPlaceholderText("Rechercher dans vos favoris…")
        self.dashboard_search.textChanged.connect(self._refresh_dashboard)
        toolbar.addWidget(self.dashboard_search, 1)
        add = QPushButton("+ Ajouter un fichier")
        add.setToolTip(
            "Ajouter un fichier audio ou vidéo à vos favoris — "
            "les vidéos sont converties en audio automatiquement"
        )
        add.clicked.connect(self._add_local_file)
        toolbar.addWidget(add)
        layout.addLayout(toolbar)
        self.dashboard_hint = QLabel()
        self.dashboard_hint.setObjectName("muted")
        layout.addWidget(self.dashboard_hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.card_container = QWidget()
        container_layout = QVBoxLayout(self.card_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(10)
        self.card_grid = QGridLayout()
        self.card_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card_grid.setContentsMargins(0, 0, 0, 0)
        container_layout.addLayout(self.card_grid)
        self.recent_header = QLabel("Récemment utilisés")
        self.recent_header.setObjectName("sectionLabel")
        container_layout.addWidget(self.recent_header)
        self.recent_hint = QLabel(
            "Sons joués récemment qui ne sont pas dans vos favoris. "
            "★ les ajoute pour les garder hors ligne et leur donner un raccourci."
        )
        self.recent_hint.setObjectName("muted")
        self.recent_hint.setWordWrap(True)
        container_layout.addWidget(self.recent_hint)
        self.recent_grid = QGridLayout()
        self.recent_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.recent_grid.setContentsMargins(0, 0, 0, 0)
        container_layout.addLayout(self.recent_grid)
        container_layout.addStretch(1)
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll, 1)
        return page

    # ------------------------------------------------------------------ voice

    @staticmethod
    def _step_card(number: str, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        """Return a numbered card so the cloning flow reads as ordered steps."""

        card = QWidget()
        card.setObjectName("stepCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 15)
        layout.setSpacing(11)
        header = QHBoxLayout()
        header.setSpacing(11)
        badge = QLabel(number)
        badge.setObjectName("stepBadge")
        badge.setFixedSize(27, 27)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        heading.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName("stepTitle")
        heading.addWidget(label)
        hint = QLabel(subtitle)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        heading.addWidget(hint)
        header.addLayout(heading, 1)
        layout.addLayout(header)
        return card, layout

    def _voice_page(self) -> QWidget:
        """Gate the workspace behind the user's own cloning terms."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.voice_stack = QStackedWidget()
        self.voice_stack.addWidget(self._voice_locked_panel())
        self.voice_stack.addWidget(self._voice_workspace_panel())
        layout.addWidget(self.voice_stack, 1)
        return page

    _LOCKED_CARD_WIDTH = 500
    _LOCKED_CARD_PADDING = 26

    def _voice_locked_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        card = QWidget()
        card.setObjectName("lockedCard")
        # A centred card must be given its width: a word-wrapped label alone
        # would let the layout shrink it until the text is clipped.
        card.setFixedWidth(self._LOCKED_CARD_WIDTH)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            self._LOCKED_CARD_PADDING, 24, self._LOCKED_CARD_PADDING, 24
        )
        card_layout.setSpacing(12)
        title = QLabel("Clonage de voix verrouillé")
        title.setObjectName("stepTitle")
        card_layout.addWidget(title)
        body = QLabel(
            "Pour utiliser le clonage de voix, acceptez d’abord ses conditions "
            "d’utilisation dans les paramètres.<br><br>"
            "Vous devez disposer de l’accord de la personne dont vous clonez la voix. "
            "<b>SoundMaster n’est pas responsable</b> de l’usage que vous faites de "
            "cette fonction."
        )
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        body.setObjectName("muted")
        # A word-wrapped rich-text label reports a one-paragraph size hint, so the
        # card would clip the rest. Pin the width and ask for the real wrapped height.
        text_width = self._LOCKED_CARD_WIDTH - 2 * self._LOCKED_CARD_PADDING
        body.setFixedWidth(text_width)
        body.setMinimumHeight(body.heightForWidth(text_width))
        card_layout.addWidget(body)
        open_settings = QPushButton("Ouvrir les conditions d’utilisation")
        open_settings.setObjectName("primaryButton")
        open_settings.clicked.connect(self._open_voice_consent_settings)
        card_layout.addWidget(open_settings)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)
        return panel

    def _voice_workspace_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("voicePageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(12)
        layout.addWidget(self._voice_step_choose())
        layout.addWidget(self._voice_step_sample())
        layout.addWidget(self._voice_step_generate())
        layout.addWidget(self._voice_result_card())
        layout.addWidget(self._voice_advanced_section())
        layout.addWidget(self._voice_history_card())
        layout.addStretch(1)
        scroll.setWidget(inner)
        self.voice_page_scroll = scroll
        self._relayout_voice_controls()
        return scroll

    def _voice_step_choose(self) -> QWidget:
        card, layout = self._step_card(
            "1",
            "Nommez ou choisissez une voix",
            "Une voix = un nom, un échantillon audio et ses réglages. Créez-en autant que vous voulez.",
        )
        setup_row = QGridLayout()
        setup_row.setHorizontalSpacing(8)
        setup_row.setVerticalSpacing(6)
        self._voice_setup_layout = setup_row
        self.voice_profile_combo = WheelScrollComboBox()
        self.voice_profile_combo.setPlaceholderText("Mes voix sauvegardées…")
        self.voice_profile_combo.currentIndexChanged.connect(self._voice_profile_changed)
        setup_row.addWidget(self.voice_profile_combo, 0, 0)
        add_voice = QPushButton("+ Nouvelle voix")
        add_voice.setObjectName("compactPrimaryButton")
        add_voice.setToolTip("Repartir d’une voix vierge : un nom, un échantillon, c’est tout")
        add_voice.clicked.connect(self._start_new_voice_profile)
        self._voice_new_setup_button = add_voice
        setup_row.addWidget(add_voice, 0, 1)
        self.delete_voice_button = QPushButton("Supprimer")
        self.delete_voice_button.setObjectName("compactButton")
        self.delete_voice_button.setToolTip("Supprimer la voix sélectionnée et son échantillon")
        self.delete_voice_button.clicked.connect(self._delete_voice_profile)
        self._voice_delete_setup_button = self.delete_voice_button
        setup_row.addWidget(self.delete_voice_button, 0, 2)
        layout.addLayout(setup_row)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.voice_profile_name = QLineEdit()
        self.voice_profile_name.setPlaceholderText("Nom de la voix (ex. Discord — voix grave)")
        self.voice_profile_name.setToolTip(
            "Ce nom regroupe l’échantillon et tous les réglages avancés de cette voix."
        )
        name_row.addWidget(self.voice_profile_name, 1)
        self.voice_save_button = QPushButton("Sauvegarder")
        self.voice_save_button.setIcon(get_icon("save"))
        self.voice_save_button.setObjectName("compactButton")
        self.voice_save_button.setToolTip(
            "Sauvegarder cette voix pour la réutiliser plus tard (facultatif pour générer)"
        )
        self.voice_save_button.clicked.connect(self._save_voice_profile)
        name_row.addWidget(self.voice_save_button)
        layout.addLayout(name_row)

        self.voice_profile_status = QLabel(
            "Créez une voix ou choisissez-en une, puis ajoutez son échantillon à l’étape 2."
        )
        self.voice_profile_status.setObjectName("muted")
        self.voice_profile_status.setWordWrap(True)
        layout.addWidget(self.voice_profile_status)
        return card

    def _voice_step_sample(self) -> QWidget:
        card, layout = self._step_card(
            "2",
            "Capturez ou importez un échantillon audio ou vidéo",
            "3 à 10 secondes de parole claire suffisent. Écoutez toujours l’échantillon "
            "avant de générer : c’est lui qui décide du résultat.",
        )
        record_row = QGridLayout()
        record_row.setHorizontalSpacing(6)
        record_row.setVerticalSpacing(6)
        self._voice_record_layout = record_row
        self.voice_record_button = QPushButton(self._MIC_BUTTON_LABEL)
        self.voice_record_button.setIcon(get_icon("mic"))
        self.voice_record_button.setObjectName("compactButton")
        self.voice_record_button.setToolTip(self._MIC_BUTTON_HINT)
        self.voice_record_button.clicked.connect(self._toggle_micro_recording)
        if QMediaRecorder is None or QMediaCaptureSession is None or QAudioInput is None:
            self.voice_record_button.setEnabled(False)
            self.voice_record_button.setToolTip(
                "Enregistrement microphone indisponible sur cette installation"
            )
        self._voice_record_widgets = [self.voice_record_button]
        record_row.addWidget(self.voice_record_button, 0, 0)
        self.voice_system_record_button = QPushButton(self._SYSTEM_BUTTON_LABEL)
        self.voice_system_record_button.setObjectName("compactButton")
        self.voice_system_record_button.clicked.connect(self._toggle_system_recording)
        if SystemAudioRecorder.capability_error() is None:
            self.voice_system_record_button.setToolTip(
                "Capturer la sortie Windows sélectionnée, par exemple une voix de "
                "Discord via WASAPI loopback"
            )
        else:
            # Keep the action clickable so the user gets an actionable message
            # instead of a button that appears broken when the optional backend
            # or a WASAPI endpoint is missing.
            self.voice_system_record_button.setToolTip(
                "Capture indisponible : relancez setup_env.bat puis sélectionnez une sortie Windows"
            )
        self._voice_record_widgets.append(self.voice_system_record_button)
        record_row.addWidget(self.voice_system_record_button, 0, 1)
        self.voice_import_button = QPushButton("Importer un fichier")
        self.voice_import_button.setIcon(get_icon("import_file"))
        self.voice_import_button.setObjectName("compactButton")
        self.voice_import_button.setToolTip(
            "Importer un fichier audio ou vidéo — les vidéos sont converties en audio automatiquement"
        )
        self.voice_import_button.clicked.connect(self._import_voice_sample)
        self._voice_record_widgets.append(self.voice_import_button)
        record_row.addWidget(self.voice_import_button, 0, 2)

        # "Retirer" button: visible only when a sample is loaded, hides
        # record/import buttons to prevent accidental overwrites.
        self.voice_remove_sample_button = QPushButton("Retirer l'échantillon")
        self.voice_remove_sample_button.setObjectName("compactButton")
        self.voice_remove_sample_button.setStyleSheet(
            "QPushButton { color: #f87171; border-color: #7f1d1d; }"
            "QPushButton:hover { background: #1c0a0a; border-color: #f87171; }"
        )
        self.voice_remove_sample_button.setToolTip("Retirer l'échantillon chargé pour en capturer ou importer un autre")
        self.voice_remove_sample_button.clicked.connect(self._remove_voice_sample)
        self.voice_remove_sample_button.setVisible(False)
        record_row.addWidget(self.voice_remove_sample_button, 0, 3)
        layout.addLayout(record_row)

        self.voice_sample_player = AudioPreviewBar(
            "Aucun échantillon — capturez ou importez un audio ci-dessus"
        )
        self.voice_sample_player.setToolTip("Réécoutez l’échantillon qui servira de modèle")
        layout.addWidget(self.voice_sample_player)

        # The full path stays available for advanced users; the simple flow only
        # needs the player above.
        self.voice_sample = QLineEdit()
        self.voice_sample.setPlaceholderText("Capturez au micro, capturez la sortie ou importez un audio / une vidéo")
        self.voice_sample.setReadOnly(True)
        return card

    def _voice_step_generate(self) -> QWidget:
        card, layout = self._step_card(
            "3",
            "Écrivez, testez, générez",
            "Testez d’abord une phrase courte pour vérifier que la voix vous convient, "
            "puis lancez la génération complète.",
        )
        self.voice_text = EmotionTextEdit()
        self.voice_text.setObjectName("voiceText")
        self.voice_text.setPlaceholderText("Ce que la voix doit dire…")
        self.voice_text.setMinimumHeight(110)
        self.voice_text.setMaximumHeight(260)
        self.voice_text.selection_finished.connect(self._apply_active_f5_emotion)
        layout.addWidget(self.voice_text)

        self.voice_emotion_toolbar = QWidget()
        emotion_layout = QHBoxLayout(self.voice_emotion_toolbar)
        emotion_layout.setContentsMargins(0, 0, 0, 0)
        emotion_layout.setSpacing(5)
        emotion_label = QLabel("Émotions F5-TTS")
        emotion_label.setObjectName("sectionLabel")
        emotion_layout.addWidget(emotion_label)
        self.voice_emotion_buttons: dict[str, QPushButton] = {}
        for emotion in F5_EMOTIONS:
            button = QPushButton(emotion.label)
            button.setCheckable(True)
            button.setObjectName("emotionButton")
            button.setToolTip(
                f"{emotion.description}. Cliquez puis sélectionnez le texte à colorer. "
                "Resélectionner la même émotion retire la couleur."
            )
            button.setStyleSheet(
                f"QPushButton#emotionButton {{ color: {emotion.foreground}; "
                f"background: {emotion.background}; border-color: {emotion.background}; }}"
                f"QPushButton#emotionButton:checked {{ border: 2px solid #f8fafc; }}"
            )
            button.clicked.connect(
                lambda _checked, key=emotion.key: self._select_f5_emotion(key)
            )
            emotion_layout.addWidget(button)
            self.voice_emotion_buttons[emotion.key] = button
        emotion_layout.addStretch(1)
        self.voice_emotion_toolbar.setToolTip(
            "Choisissez une émotion, puis surlignez la partie du texte concernée."
        )
        self.voice_emotion_toolbar.setVisible(False)
        layout.addWidget(self.voice_emotion_toolbar)

        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)
        self.voice_generate_button = QPushButton("Générer")
        self.voice_generate_button.setIcon(get_icon("sparkle"))
        self.voice_generate_button.setObjectName("primaryButton")
        self.voice_generate_button.setToolTip("Générer le texte complet avec cette voix, en local")
        self.voice_generate_button.clicked.connect(self._generate_voice)
        action_bar.addWidget(self.voice_generate_button, 1)
        layout.addLayout(action_bar)

        self.voice_favorite = QCheckBox("Ajouter chaque génération aux favoris")
        self.voice_favorite.setChecked(True)
        layout.addWidget(self.voice_favorite)

        self.voice_progress = QProgressBar()
        self.voice_progress.setRange(0, 100)
        self.voice_progress.setValue(0)
        self.voice_progress.setTextVisible(False)
        self.voice_progress.setVisible(False)
        layout.addWidget(self.voice_progress)
        self.voice_status = QLabel("Prêt — tout est généré sur votre ordinateur")
        self.voice_status.setObjectName("muted")
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)
        return card

    def _voice_result_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("stepCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 15)
        layout.setSpacing(10)
        title = QLabel("Résultat")
        title.setObjectName("stepTitle")
        layout.addWidget(title)
        self.voice_result_player = AudioPreviewBar(
            "Aucune génération pour l’instant — le résultat s’écoutera ici"
        )
        layout.addWidget(self.voice_result_player)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.voice_result_favorite_button = QPushButton("★ Ajouter aux favoris")
        self.voice_result_favorite_button.setObjectName("compactButton")
        self.voice_result_favorite_button.setEnabled(False)
        self.voice_result_favorite_button.clicked.connect(self._favorite_last_generation)
        actions.addWidget(self.voice_result_favorite_button, 1)
        self.voice_result_folder_button = QPushButton("Ouvrir le dossier")
        self.voice_result_folder_button.setIcon(get_icon("folder_open"))
        self.voice_result_folder_button.setObjectName("compactButton")
        self.voice_result_folder_button.setEnabled(False)
        self.voice_result_folder_button.clicked.connect(self._open_last_generation_folder)
        actions.addWidget(self.voice_result_folder_button, 1)
        layout.addLayout(actions)
        return card

    def _voice_advanced_section(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.voice_advanced_button = QToolButton()
        self.voice_advanced_button.setText("Réglages avancés de cette voix")
        self.voice_advanced_button.setCheckable(True)
        self.voice_advanced_button.setChecked(False)
        settings_icon = get_settings_icon()
        if not settings_icon.isNull():
            self.voice_advanced_button.setIcon(settings_icon)
            self.voice_advanced_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        else:
            self.voice_advanced_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.voice_advanced_button.setObjectName("advancedButton")
        layout.addWidget(self.voice_advanced_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.voice_advanced = QWidget()
        advanced_form = QGridLayout(self.voice_advanced)
        advanced_form.setContentsMargins(14, 10, 14, 12)
        advanced_form.setHorizontalSpacing(12)
        advanced_form.setVerticalSpacing(8)
        self.voice_engine = WheelScrollComboBox()
        self.voice_engine.addItem("Qwen3-TTS 1.7B — qualité maximale (recommandé)", "qwen3-tts")
        self.voice_engine.addItem("Qwen3-TTS 0.6B — léger et rapide (~1.2 Go)", "qwen3-tts-0.6b")
        self.voice_engine.addItem("Pocket TTS — rapide, sans GPU", "pocket-tts")
        self.voice_engine.addItem("OmniVoice — multilingue", "omnivoice")
        self.voice_engine.addItem("F5-TTS — expressif & émotions textuelles", "f5-tts")
        self.voice_engine.setToolTip(
            "Choisissez le moteur vocal. F5-TTS permet de contrôler les émotions par des balises [sad], [happy], etc."
        )
        default_engine = self.library.preference("default_voice_engine", "pocket-tts")
        default_idx = self.voice_engine.findData(default_engine)
        if default_idx >= 0:
            self.voice_engine.setCurrentIndex(default_idx)
        self.voice_engine.currentIndexChanged.connect(self._voice_engine_changed)
        advanced_form.addWidget(QLabel("Moteur vocal"), 0, 0)
        advanced_form.addWidget(self.voice_engine, 0, 1)

        self.voice_reference_text = QLineEdit()
        self.voice_reference_text.setPlaceholderText(
            "Facultatif : transcription exacte de l’échantillon"
        )
        advanced_form.addWidget(QLabel("Transcription"), 2, 0)
        advanced_form.addWidget(self.voice_reference_text, 2, 1)
        self.voice_model = QLineEdit(
            get_profile(str(self.voice_engine.currentData())).repository
        )
        self.voice_model.setReadOnly(True)
        advanced_form.addWidget(QLabel("Modèle local"), 3, 0)
        advanced_form.addWidget(self.voice_model, 3, 1)
        self.voice_language = WheelScrollComboBox()
        # The visible label is French; the data stays the canonical engine token
        # so saved voices and the other engines keep working unchanged.
        for label, token in VOICE_LANGUAGES:
            self.voice_language.addItem(label, token)
        # Start from the global default language chosen in the settings.
        default_lang = self.library.preference(DEFAULT_LANGUAGE_PREFERENCE, "French")
        default_lang_index = self.voice_language.findData(default_lang)
        if default_lang_index >= 0:
            self.voice_language.setCurrentIndex(default_lang_index)
        self.voice_language.setToolTip(
            "Langue utilisée pour ce clonage. La langue par défaut se choisit "
            "dans Paramètres : Pocket TTS charge son modèle dédié, Qwen3-TTS et "
            "OmniVoice l’utilisent à la génération."
        )
        self.voice_language.currentIndexChanged.connect(
            lambda _index: self._sync_pocket_quality_control()
        )
        advanced_form.addWidget(QLabel("Langue"), 3, 0)
        advanced_form.addWidget(self.voice_language, 3, 1)
        self.voice_high_quality = QCheckBox(
            "Modèle haute qualité (24 couches, plus lent)"
        )
        self.voice_high_quality.setToolTip(
            "Pocket TTS uniquement : variante plus lourde des langues autres que "
            "l’anglais. Décochez-la pour la génération la plus rapide."
        )
        advanced_form.addWidget(self.voice_high_quality, 4, 1)
        self.voice_quantize = QCheckBox("Génération accélérée (quantification)")
        self.voice_quantize.setToolTip(
            "Pocket TTS sans carte graphique : réduit la précision du modèle pour "
            "générer plus vite (mesuré : 11,5 s → 9,6 s) sans perte audible. "
            "Ignoré quand un GPU est disponible, car le GPU est déjà plus rapide "
            "et ne sait pas exécuter un modèle quantifié."
        )
        advanced_form.addWidget(self.voice_quantize, 5, 1)
        self.voice_temperature = QDoubleSpinBox()
        self.voice_temperature.setRange(0.0, 2.0)
        self.voice_temperature.setSingleStep(0.05)
        self.voice_temperature.setValue(0.7)
        self.voice_temperature.setToolTip("Plus haut = plus expressif et plus imprévisible")
        advanced_form.addWidget(QLabel("Température / émotion"), 6, 0)
        advanced_form.addWidget(self.voice_temperature, 6, 1)
        self.voice_speed = QDoubleSpinBox()
        self.voice_speed.setRange(0.5, 2.0)
        self.voice_speed.setSingleStep(0.05)
        self.voice_speed.setValue(1.0)
        advanced_form.addWidget(QLabel("Vitesse"), 7, 0)
        advanced_form.addWidget(self.voice_speed, 7, 1)
        self.voice_top_p = QDoubleSpinBox()
        self.voice_top_p.setRange(0.05, 1.0)
        self.voice_top_p.setSingleStep(0.05)
        self.voice_top_p.setValue(0.9)
        advanced_form.addWidget(QLabel("Top-p"), 8, 0)
        advanced_form.addWidget(self.voice_top_p, 8, 1)
        self.voice_repetition_penalty = QDoubleSpinBox()
        self.voice_repetition_penalty.setRange(0.5, 2.0)
        self.voice_repetition_penalty.setSingleStep(0.05)
        self.voice_repetition_penalty.setValue(1.05)
        advanced_form.addWidget(QLabel("Anti-répétition"), 9, 0)
        advanced_form.addWidget(self.voice_repetition_penalty, 9, 1)
        self.voice_capture_output = WheelScrollComboBox()
        self._populate_voice_capture_outputs()
        advanced_form.addWidget(QLabel("Sortie à capturer"), 10, 0)
        advanced_form.addWidget(self.voice_capture_output, 10, 1)
        advanced_form.addWidget(QLabel("Fichier de l’échantillon"), 11, 0)
        advanced_form.addWidget(self.voice_sample, 11, 1)
        advanced_form.setColumnStretch(1, 1)
        self.voice_advanced.setObjectName("voiceAdvanced")
        self.voice_advanced.setVisible(False)
        self.voice_advanced_button.toggled.connect(self._set_voice_advanced_visible)
        layout.addWidget(self.voice_advanced)
        # All engine-dependent widgets exist now, so apply the default engine's
        # state instead of waiting for the first user change.
        self._voice_engine_changed(self.voice_engine.currentIndex())
        return container

    def _voice_history_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("stepCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 15)
        layout.setSpacing(9)
        header = QHBoxLayout()
        history_label = QLabel("Historique des générations")
        history_label.setObjectName("stepTitle")
        header.addWidget(history_label)
        header.addStretch(1)
        self.voice_search = QLineEdit()
        self.voice_search.setObjectName("compactSearch")
        self.voice_search.setPlaceholderText("Filtrer…")
        self.voice_search.setMaximumWidth(240)
        self.voice_search.textChanged.connect(self._refresh_voice_history)
        header.addWidget(self.voice_search)
        layout.addLayout(header)
        hint = QLabel("Double-cliquez sur une ligne pour la réécouter dans le lecteur ci-dessus.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.voice_history = QListWidget()
        self.voice_history.setMinimumHeight(96)
        self.voice_history.setMaximumHeight(180)
        self.voice_history.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.voice_history.itemDoubleClicked.connect(self._play_history_item)
        layout.addWidget(self.voice_history)
        return card

    def _myinstants_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h3>Explorateur Myinstants intégré</h3>"))
        self.myinstants_catalog_hint = QLabel(
            "Les sons populaires de Myinstants s’affichent ici automatiquement. "
            "Recherchez ensuite un terme pour affiner le catalogue."
        )
        self.myinstants_catalog_hint.setObjectName("muted")
        self.myinstants_catalog_hint.setWordWrap(True)
        layout.addWidget(self.myinstants_catalog_hint)
        row = QHBoxLayout()
        self.myinstants_search = QLineEdit()
        self.myinstants_search.setPlaceholderText("airhorn, meme, applause…")
        self.myinstants_search.returnPressed.connect(self._search_myinstants)
        row.addWidget(self.myinstants_search, 1)
        self.myinstants_search_button = QPushButton("Rechercher / actualiser")
        self.myinstants_search_button.setObjectName("primaryButton")
        self.myinstants_search_button.clicked.connect(self._search_myinstants)
        row.addWidget(self.myinstants_search_button)
        layout.addLayout(row)
        usage_hint = QLabel(
            "▶ Tester lit le son en direct, comme sur Myinstants, sans le conserver. "
            "★ Ajouter aux favoris télécharge une copie locale pour le mode hors ligne et les raccourcis."
        )
        usage_hint.setObjectName("muted")
        usage_hint.setWordWrap(True)
        layout.addWidget(usage_hint)
        bulk_actions = QHBoxLayout()
        self.select_all_myinstants = QPushButton("Tout sélectionner")
        self.select_all_myinstants.setObjectName("ghostButton")
        self.select_all_myinstants.clicked.connect(self._select_all_myinstants)
        bulk_actions.addWidget(self.select_all_myinstants)
        self.clear_myinstants_selection = QPushButton("Effacer la sélection")
        self.clear_myinstants_selection.setObjectName("ghostButton")
        self.clear_myinstants_selection.clicked.connect(self._clear_myinstants_selection)
        bulk_actions.addWidget(self.clear_myinstants_selection)
        self.favorite_selected_myinstants = QPushButton("Ajouter la sélection aux favoris")
        self.favorite_selected_myinstants.setObjectName("primaryButton")
        self.favorite_selected_myinstants.setEnabled(False)
        self.favorite_selected_myinstants.clicked.connect(self._favorite_selected_myinstants)
        bulk_actions.addWidget(self.favorite_selected_myinstants, 1)
        layout.addLayout(bulk_actions)
        self.myinstants_selection_status = QLabel("0 son sélectionné")
        self.myinstants_selection_status.setObjectName("muted")
        layout.addWidget(self.myinstants_selection_status)
        self.bulk_download_progress = QProgressBar()
        self.bulk_download_progress.setRange(0, 100)
        self.bulk_download_progress.setValue(0)
        self.bulk_download_progress.setTextVisible(False)
        self.bulk_download_progress.setVisible(False)
        layout.addWidget(self.bulk_download_progress)
        self.myinstants_status = QLabel("Prêt à rechercher")
        self.myinstants_status.setObjectName("muted")
        layout.addWidget(self.myinstants_status)
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setTextVisible(False)
        self.search_progress.setVisible(False)
        layout.addWidget(self.search_progress)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.myinstants_container = QWidget()
        self.myinstants_grid = QGridLayout(self.myinstants_container)
        self.myinstants_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.myinstants_container)
        layout.addWidget(scroll, 1)
        download_group = QGroupBox("Téléchargements en cours")
        download_layout = QVBoxLayout(download_group)
        self.download_summary = QLabel("Aucun téléchargement actif")
        self.download_summary.setObjectName("muted")
        download_layout.addWidget(self.download_summary)
        self.download_rows = QVBoxLayout()
        self.download_rows.setSpacing(6)
        download_layout.addLayout(self.download_rows)
        download_group.setVisible(False)
        self.download_group = download_group
        layout.addWidget(download_group)
        footer = QLabel(
            "Merci à Myinstants pour la plateforme. Les sons restent soumis à leurs "
            "conditions et aux droits de leurs auteurs. "
            '<a href="https://www.myinstants.com/en/">Visiter le site officiel</a> · '
            '<a href="https://www.myinstants.com/en/terms_of_use.html">Conditions d’utilisation</a>'
        )
        footer.setWordWrap(True)
        footer.setOpenExternalLinks(True)
        footer.setObjectName("muted")
        layout.addWidget(footer)
        return page

    def _keybinds_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "<h3>Raccourcis globaux</h3>"
            "<p>Cliquez sur <b>Enregistrer</b> pour un favori, puis appuyez sur les touches "
            "simultanément. Chaque combinaison est sauvegardée immédiatement et déclenche "
            "l’envoi vers la sortie 2, même pendant un jeu.</p>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.keybind_table = QTableWidget(0, 4)
        self.keybind_table.setHorizontalHeaderLabels(("Son", "Source", "Raccourci", "Action"))
        header = self.keybind_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.keybind_table.verticalHeader().setDefaultSectionSize(40)
        self.keybind_table.verticalHeader().setMinimumSectionSize(36)
        self.keybind_table.verticalHeader().setMaximumSectionSize(44)
        self.keybind_table.setColumnWidth(1, 130)
        self.keybind_table.setColumnWidth(2, 210)
        self.keybind_table.setColumnWidth(3, 110)
        self.keybind_table.setAlternatingRowColors(True)
        layout.addWidget(self.keybind_table, 1)
        actions = QHBoxLayout()
        self.hotkey_toggle = QPushButton("Activer les raccourcis")
        self.hotkey_toggle.clicked.connect(self._toggle_hotkeys)
        actions.addWidget(self.hotkey_toggle)
        actions.addWidget(QLabel("Les changements sont enregistrés automatiquement."))
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _settings_page(self) -> QWidget:
        """Split settings into tabs so the cloning terms have their own room."""

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.addTab(self._voice_consent_tab(), "Clonage de voix")
        tabs.addTab(self._audio_settings_tab(), "Audio et système")
        tabs.addTab(self._updates_tab(), "Mises à jour")
        legal = LegalSettingsWidget(self.legal_profile, self.legal_profile_path, page)
        legal.saved.connect(lambda: self.statusBar().showMessage("Paramètres enregistrés", 5000))
        tabs.addTab(legal, "Conformité éditeur")
        self.settings_tabs = tabs
        layout.addWidget(tabs, 1)
        return page

    def _voice_consent_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 6, 0)
        inner_layout.setSpacing(14)
        self.voice_consent = VoiceConsentPanel(self._voice_cloning_accepted())
        self.voice_consent.changed.connect(self._set_voice_cloning_consent)
        self.voice_consent.open_requested.connect(lambda: self._select_page(1))
        inner_layout.addWidget(self.voice_consent)
        inner_layout.addWidget(self._voice_language_settings_group())
        inner_layout.addWidget(self._voice_models_settings_group())
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        self.voice_consent_scroll = scroll
        layout.addWidget(scroll, 1)
        return tab

    def _voice_language_settings_group(self) -> QGroupBox:
        """Global default language, applied to every cloning engine."""

        group = QGroupBox("Langue par défaut (tous les moteurs)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        intro = QLabel(
            "Choisie une seule fois ici, la langue est appliquée par défaut à tous "
            "les modèles : Pocket TTS charge son modèle dédié (français, anglais, "
            "etc.), Qwen3-TTS et OmniVoice l’utilisent à la génération. "
            "« Auto » laisse chaque moteur choisir son réglage."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.default_language = WheelScrollComboBox()
        for label, token in VOICE_LANGUAGES:
            self.default_language.addItem(label, token)
        saved = self.library.preference(DEFAULT_LANGUAGE_PREFERENCE, "French")
        saved_index = self.default_language.findData(saved)
        self.default_language.setCurrentIndex(max(0, saved_index))
        self.default_language.currentIndexChanged.connect(self._default_language_changed)
        layout.addWidget(self.default_language)
        return group

    def _default_language_changed(self, _index: int) -> None:
        token = str(self.default_language.currentData() or "French")
        self.library.set_preference(DEFAULT_LANGUAGE_PREFERENCE, token)
        # Follow in the voice page for the current editing session, so the new
        # default applies immediately without forcing the user to re-pick it.
        if hasattr(self, "voice_language"):
            voice_index = self.voice_language.findData(token)
            if voice_index >= 0:
                self.voice_language.setCurrentIndex(voice_index)
        self.statusBar().showMessage(
            f"Langue par défaut : {self.default_language.currentText()}", 4000
        )

    def _voice_models_settings_group(self) -> QGroupBox:
        group = QGroupBox("Modèles de clonage de voix (Gestion & Sélection)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        intro = QLabel(
            "Sélectionnez le modèle par défaut pour le clonage de voix. "
            "Vous pouvez aussi télécharger ou supprimer les modèles locaux pour gérer votre espace disque."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Where the models are stored — lets the user pick a disk with room
        # (e.g. D:) without touching environment variables.
        self.model_directory_label = QLabel()
        self.model_directory_label.setWordWrap(True)
        layout.addWidget(self.model_directory_label)
        dir_actions = QHBoxLayout()
        dir_actions.setSpacing(8)
        self.model_directory_button = QPushButton("Changer le dossier des modèles…")
        self.model_directory_button.setObjectName("compactButton")
        self.model_directory_button.setToolTip(
            "Choisissez un dossier sur un disque disposant d’espace libre "
            r"(ex. D:\SoundMaster-models) pour y stocker les modèles téléchargés."
        )
        self.model_directory_button.clicked.connect(self._choose_model_directory)
        dir_actions.addWidget(self.model_directory_button, 1)
        self.model_directory_reset_button = QPushButton("Réinitialiser")
        self.model_directory_reset_button.setObjectName("compactButton")
        self.model_directory_reset_button.setToolTip(
            "Revenir au dossier par défaut (%LOCALAPPDATA%\\SoundMaster\\models)."
        )
        self.model_directory_reset_button.clicked.connect(self._reset_model_directory)
        dir_actions.addWidget(self.model_directory_reset_button)
        layout.addLayout(dir_actions)

        self.voice_models_progress = QProgressBar()
        self.voice_models_progress.setVisible(False)
        self.voice_models_progress.setTextVisible(False)
        layout.addWidget(self.voice_models_progress)
        self.voice_models_progress_label = QLabel("")
        self.voice_models_progress_label.setObjectName("muted")
        self.voice_models_progress_label.setWordWrap(True)
        self.voice_models_progress_label.setVisible(False)
        layout.addWidget(self.voice_models_progress_label)

        self._refresh_model_directory_label()
        self.voice_models_cards_layout = QVBoxLayout()
        self.voice_models_cards_layout.setSpacing(8)
        layout.addLayout(self.voice_models_cards_layout)
        self._refresh_voice_model_settings()
        return group

    def _refresh_model_directory_label(self) -> None:
        """Show the active model folder with the free space available on it."""

        directory = model_directory(self.paths)
        try:
            usage = shutil.disk_usage(directory)
            free_text = f"{usage.free / (1024**3):.0f} Go libres"
        except OSError:
            free_text = "espace inconnu"
        self.model_directory_label.setText(
            f"<b>Dossier des modèles :</b> {directory}<br>"
            f"<span style='color: #94a3b8;'>{free_text} — les modèles téléchargés y seront enregistrés.</span>"
        )

    def _choose_model_directory(self) -> None:
        from PyQt6.QtWidgets import QFileDialog

        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choisir le dossier des modèles",
            str(model_directory(self.paths)),
        )
        if not chosen:
            return
        directory = Path(chosen).expanduser().resolve()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(
                self,
                "Dossier inaccessible",
                f"Impossible de créer le dossier {directory} : {error}",
            )
            return
        set_model_directory(directory)
        self.library.set_preference(MODEL_DIRECTORY_PREFERENCE, str(directory))
        self.statusBar().showMessage(
            f"Dossier des modèles défini : {directory}", 5000
        )
        self._refresh_model_directory_label()
        self._refresh_voice_model_settings()

    def _reset_model_directory(self) -> None:
        set_model_directory(None)
        self.library.set_preference(MODEL_DIRECTORY_PREFERENCE, "")
        self.statusBar().showMessage(
            "Dossier des modèles réinitialisé (dossier par défaut)", 5000
        )
        self._refresh_model_directory_label()
        self._refresh_voice_model_settings()

    def _refresh_voice_model_settings(self) -> None:
        if not hasattr(self, "voice_models_cards_layout"):
            return
        while self.voice_models_cards_layout.count():
            item = self.voice_models_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        default_engine = self.library.preference("default_voice_engine", "pocket-tts")
        for profile in MODEL_PROFILES:
            if profile.key == "qwen3-tts-tokenizer":
                continue

            card = QGroupBox()
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(10)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(3)

            title_text = f"<b>{profile.directory_name}</b> ({profile.key})"
            if profile.key == default_engine:
                title_text += " &nbsp;<span style='color: #4ade80;'><b>[Actif par défaut]</b></span>"
            title_lbl = QLabel(title_text)
            title_lbl.setTextFormat(Qt.TextFormat.RichText)
            info_layout.addWidget(title_lbl)

            desc_lbl = QLabel(profile.purpose)
            desc_lbl.setObjectName("muted")
            desc_lbl.setWordWrap(True)
            info_layout.addWidget(desc_lbl)

            downloaded = is_downloaded(profile, self.paths)
            if profile.key == "pocket-tts":
                # Pocket TTS ships its weights inside the runtime cache, not in
                # the managed model folder, so the generic size label would
                # always read "Non installé". Report the two real signals: the
                # bundled runtime and the voice-cloning weights in the cache.
                # find_spec is used (not is_engine_runtime_installed) because
                # importing pocket_tts drags in torch and costs seconds on
                # every settings rebuild.
                runtime_ok = _module_available("pocket_tts")
                weights_ok = pocket_weights_cached()
                runtime_text = "intégré ✓" if runtime_ok else "absent"
                weights_text = "installés ✓" if weights_ok else "à télécharger"
                status_lbl = QLabel(
                    f"Runtime : {runtime_text}  ·  Poids vocaux : {weights_text}"
                )
            else:
                size_text = model_size_str(profile, self.paths)
                avg_time = self.library.avg_generation_time(profile.key)
                time_text = (
                    f"~{avg_time:.1f} s"
                    if avg_time is not None
                    else "Aucune donnée (premier essai requis)"
                )
                status_lbl = QLabel(
                    f"Taille : {size_text}  ·  ⏱ Temps moyen de génération : {time_text}"
                )
            status_lbl.setObjectName("muted")
            info_layout.addWidget(status_lbl)

            card_layout.addLayout(info_layout, 1)

            actions_layout = QVBoxLayout()
            actions_layout.setSpacing(4)

            is_active = (profile.key == default_engine)
            select_btn = QPushButton("Actif par défaut" if is_active else "Choisir par défaut")
            select_btn.setObjectName("primaryButton" if is_active else "compactButton")
            select_btn.setEnabled(not is_active)
            select_btn.clicked.connect(lambda _, k=profile.key: self._set_default_voice_engine(k))
            actions_layout.addWidget(select_btn)

            if profile.key == "pocket-tts":
                # The weights travel with the runtime, so the only "install"
                # action is to download them (or repair them) through the
                # engine itself. The button stays available even when Pocket
                # TTS is the active default engine.
                install_btn = QPushButton(
                    "Réinstaller les poids"
                    if pocket_weights_cached()
                    else "Installer Pocket TTS"
                )
                install_btn.setObjectName("compactButton")
                install_btn.setToolTip(
                    "Télécharge les poids du clonage vocal Pocket TTS "
                    "(~300 Mo, premier usage inclus). Utile après une mise à "
                    "jour ou un nettoyage du cache Hugging Face."
                )
                install_btn.clicked.connect(
                    lambda _checked=False, p=profile: self._install_pocket_tts(p)
                )
                actions_layout.addWidget(install_btn)
            elif not downloaded:
                dl_btn = QPushButton("Télécharger")
                dl_btn.setObjectName("compactButton")
                dl_btn.setToolTip(f"Télécharger {profile.key} ({profile.approximate_storage})")
                dl_btn.clicked.connect(lambda _, p=profile: self._download_voice_model(p))
                actions_layout.addWidget(dl_btn)
            elif downloaded:
                del_btn = QPushButton("Supprimer")
                del_btn.setObjectName("compactButton")
                del_btn.setStyleSheet(
                    "QPushButton { color: #f87171; border-color: #7f1d1d; }"
                    "QPushButton:hover { background: #1c0a0a; border-color: #f87171; }"
                )
                del_btn.setToolTip(f"Supprimer le modèle {profile.key} du disque")
                del_btn.clicked.connect(lambda _, p=profile: self._delete_voice_model(p))
                actions_layout.addWidget(del_btn)

            card_layout.addLayout(actions_layout)
            self.voice_models_cards_layout.addWidget(card)

    def _set_default_voice_engine(self, engine_key: str) -> None:
        self.library.set_preference("default_voice_engine", engine_key)
        profile = get_profile(engine_key)
        if engine_key == "pocket-tts":
            # The runtime is bundled with the app; only the weights can be
            # missing, and they are downloaded through the engine itself.
            if (
                is_engine_runtime_installed("pocket-tts")
                and not pocket_weights_cached()
            ):
                ans = QMessageBox.question(
                    self,
                    "Installer Pocket TTS ?",
                    "Pocket TTS est maintenant le moteur par défaut, mais ses "
                    "poids vocaux ne sont pas encore téléchargés. Les "
                    "télécharger maintenant (~300 Mo) ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ans == QMessageBox.StandardButton.Yes:
                    self._install_pocket_tts(profile)
        elif not is_downloaded(profile, self.paths):
            ans = QMessageBox.question(
                self,
                "Télécharger le modèle ?",
                f"Le modèle {engine_key} n'est pas encore téléchargé. Souhaitez-vous le télécharger maintenant ({profile.approximate_storage}) ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                self._download_voice_model(profile)
        idx = self.voice_engine.findData(engine_key)
        if idx >= 0:
            self.voice_engine.setCurrentIndex(idx)
        self.statusBar().showMessage(f"Modèle vocal par défaut défini : {engine_key}", 4000)
        self._refresh_voice_model_settings()

    def _download_voice_model(self, profile: ModelProfile) -> None:
        self.statusBar().showMessage(
            f"Téléchargement du modèle {profile.key} en cours…", 15000
        )
        self._show_model_download_progress(0, 1, f"Préparation du téléchargement de {profile.key}…")
        if not hasattr(self, "_model_download_threads"):
            self._model_download_threads = []
        thread = ModelDownloadThread(profile, self.paths, self)
        thread.progress_signal.connect(self._voice_model_download_progress)
        thread.finished_signal.connect(self._voice_model_download_finished)
        thread.start()
        self._model_download_threads.append(thread)

    def _show_model_download_progress(
        self, downloaded: int, total: int, message: str
    ) -> None:
        """Drive the shared download bar used by model and Pocket TTS installs."""

        if not hasattr(self, "voice_models_progress"):
            return
        self.voice_models_progress.setVisible(True)
        if total <= 0:
            self.voice_models_progress.setRange(0, 0)  # indeterminate
            self.voice_models_progress.setValue(0)
            self.voice_models_progress.setTextVisible(False)
        else:
            self.voice_models_progress.setRange(0, max(total, 1))
            self.voice_models_progress.setValue(max(0, min(downloaded, total)))
            self.voice_models_progress.setTextVisible(True)
            percent = int(downloaded * 100 / max(total, 1))
            self.voice_models_progress.setFormat(f"{percent} %")
        self.voice_models_progress_label.setText(message)
        self.voice_models_progress_label.setVisible(True)

    def _hide_model_download_progress(self) -> None:
        if hasattr(self, "voice_models_progress"):
            self.voice_models_progress.setVisible(False)
        if hasattr(self, "voice_models_progress_label"):
            self.voice_models_progress_label.setVisible(False)

    def _voice_model_download_progress(
        self, downloaded: int, total: int, filename: str
    ) -> None:
        self._show_model_download_progress(
            downloaded,
            total,
            f"{filename} — {self._format_bytes(downloaded)} / {self._format_bytes(total)}",
        )

    def _voice_model_download_finished(self, success: bool, key: str, message: str) -> None:
        self._hide_model_download_progress()
        if success:
            self.statusBar().showMessage(message, 5000)
        else:
            QMessageBox.warning(self, "Téléchargement échoué", message)
        self._refresh_voice_model_settings()

    def _format_bytes(self, size: int) -> str:
        """Human-readable byte size (Mo/Go)."""

        if size >= 1024**3:
            return f"{size / (1024**3):.1f} Go"
        if size >= 1024**2:
            return f"{size / (1024**2):.0f} Mo"
        if size >= 1024:
            return f"{size / 1024:.0f} Ko"
        return f"{size} o"

    def _install_pocket_tts(self, profile: ModelProfile) -> None:
        """Download (or repair) the Pocket TTS voice-cloning weights.

        The download runs inside the engine's own loader on a worker thread;
        once cached, first generation no longer pays the download cost.
        """

        if not is_engine_runtime_installed("pocket-tts"):
            QMessageBox.warning(
                self,
                "Runtime Pocket TTS manquant",
                "Le moteur Pocket TTS n'est pas présent dans cette installation. "
                "Réinstallez l'application avec l'extra Pocket TTS (ou exécutez "
                "setup_env.bat en développement), puis réessayez.",
            )
            return
        language = self._pocket_install_language()
        self.statusBar().showMessage(
            f"Installation de Pocket TTS ({language}) — téléchargement des poids…",
            15000,
        )
        # The runtime downloads its own weights without a byte callback, so the
        # shared bar runs indeterminate during the install.
        self._show_model_download_progress(
            0, 0, f"Téléchargement des poids Pocket TTS ({language})…"
        )
        if not hasattr(self, "_pocket_install_threads"):
            self._pocket_install_threads = []
        thread = PocketInstallThread(
            self._voice_service, language, self._voice_settings(), self
        )
        thread.finished_signal.connect(self._pocket_install_finished)
        thread.start()
        self._pocket_install_threads.append(thread)

    def _pocket_install_language(self) -> str:
        """Preload the bundle for the language the user actually generates in."""

        if hasattr(self, "default_language"):
            token = str(self.default_language.currentData() or "")
            if token:
                return token
        return str(self.library.preference(DEFAULT_LANGUAGE_PREFERENCE, "French"))

    def _pocket_install_finished(self, success: bool, message: str) -> None:
        self._hide_model_download_progress()
        if success:
            self.statusBar().showMessage(message, 6000)
        else:
            QMessageBox.warning(
                self, "Installation de Pocket TTS impossible", message
            )
        self._refresh_voice_model_settings()

    def _delete_voice_model(self, profile: ModelProfile) -> None:
        ans = QMessageBox.question(
            self,
            "Supprimer le modèle ?",
            f"Êtes-vous sûr de vouloir supprimer les fichiers du modèle '{profile.key}' ({model_size_str(profile, self.paths)}) de votre disque ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            if delete_model(profile, self.paths):
                self.statusBar().showMessage(f"Modèle {profile.key} supprimé.", 4000)
            else:
                QMessageBox.warning(self, "Erreur", f"Impossible de supprimer le dossier du modèle {profile.key}.")
            self._refresh_voice_model_settings()

    def _updates_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 8, 4, 4)
        self.update_panel = UpdateSettingsPanel(self.paths.audio_cache / "updates")
        self.update_panel.quit_requested.connect(self._quit_for_update)
        layout.addWidget(self.update_panel)
        layout.addStretch(1)
        return tab

    def _quit_for_update(self) -> None:
        """Close fully so the installer can replace the running executable."""

        self.statusBar().showMessage("Fermeture de SoundMaster pour la mise à jour…", 4000)
        self._allow_close = True
        self.close()

    def _audio_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 8, 4, 4)
        audio_group = QGroupBox("Audio et sorties")
        audio_form = QFormLayout(audio_group)
        self.microphone_input = WheelScrollComboBox()
        self.headset_output = WheelScrollComboBox()
        self.virtual_output = WheelScrollComboBox()
        self._populate_audio_devices()
        audio_form.addRow("Microphone / entrée", self.microphone_input)
        audio_form.addRow("Sortie 1 — casque", self.headset_output)
        audio_form.addRow("Sortie 2 — câble virtuel", self.virtual_output)
        # A virtual cable is only needed to route sounds into a game. When none
        # is installed, the app says so and offers the official installer
        # instead of leaving the user to figure out what VB-CABLE is.
        self.virtual_cable_status = QLabel()
        self.virtual_cable_status.setWordWrap(True)
        audio_form.addRow(self.virtual_cable_status)
        cable_actions = QHBoxLayout()
        self.install_cable_button = QPushButton("Installer VB-CABLE (gratuit, officiel)")
        self.install_cable_button.setObjectName("ghostButton")
        self.install_cable_button.clicked.connect(self._open_virtual_cable_download)
        self.refresh_devices_button = QPushButton("Actualiser les périphériques")
        self.refresh_devices_button.setObjectName("ghostButton")
        self.refresh_devices_button.clicked.connect(self._refresh_audio_devices)
        cable_actions.addWidget(self.install_cable_button)
        cable_actions.addWidget(self.refresh_devices_button)
        cable_actions.addStretch(1)
        audio_form.addRow(cable_actions)
        apply_audio = QPushButton("Appliquer et enregistrer")
        apply_audio.clicked.connect(self._apply_audio_devices)
        audio_form.addRow(apply_audio)
        hint = QLabel(
            "La sortie 2 sert à envoyer un son dans un jeu (via VB-CABLE ou équivalent). "
            "Rien n’est requis pour utiliser SoundMaster en local : laissez « Aucun (désactivé) » "
            "si vous n’avez pas besoin d’envoyer de son dans un jeu."
        )
        hint.setWordWrap(True)
        audio_form.addRow(hint)
        layout.addWidget(audio_group)
        self._update_virtual_cable_status()
        gpu_group = QGroupBox("Diagnostic GPU et clonage vocal")
        gpu_group.setObjectName("gpuDiagnostics")
        gpu_layout = QVBoxLayout(gpu_group)
        self.gpu_diagnostics = QLabel(
            "Vérifiez le moteur local, le modèle et l’accélération avant une génération."
        )
        self.gpu_diagnostics.setObjectName("muted")
        self.gpu_diagnostics.setWordWrap(True)
        self.gpu_diagnostics.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        gpu_layout.addWidget(self.gpu_diagnostics)
        self.gpu_diagnostics_button = QPushButton("Analyser l’environnement local")
        self.gpu_diagnostics_button.setObjectName("ghostButton")
        self.gpu_diagnostics_button.clicked.connect(self._run_gpu_diagnostics)
        gpu_layout.addWidget(self.gpu_diagnostics_button)
        layout.addWidget(gpu_group)
        self.tray_preference = QCheckBox(
            "Réduire dans la zone de notification à la fermeture"
        )
        self.tray_preference.setChecked(
            self._preference_bool("minimize_to_tray", self.config.minimize_to_tray)
        )
        self.tray_preference.toggled.connect(
            lambda value: self.library.set_preference("minimize_to_tray", str(value).lower())
        )
        layout.addWidget(self.tray_preference)
        layout.addStretch(1)
        return tab

    # ------------------------------------------------------- cloning consent

    def _voice_cloning_accepted(self) -> bool:
        return self._preference_bool(CONSENT_PREFERENCE_KEY, False)

    def _set_voice_cloning_consent(self, accepted: bool) -> None:
        """Persist the user's decision and lock or unlock the cloning menu."""

        self.library.set_preference(CONSENT_PREFERENCE_KEY, str(bool(accepted)).lower())
        self._apply_voice_lock_state()
        if accepted:
            if self._voice_consent_pending_redirect:
                # The user only came here because the locked menu sent them.
                # Take them back instead of leaving them to guess.
                self.statusBar().showMessage(
                    "Clonage de voix déverrouillé — ouverture du menu…", 6000
                )
                QTimer.singleShot(900, self._return_to_voice_after_consent)
            else:
                self.statusBar().showMessage(
                    "Clonage de voix déverrouillé. Vous restez responsable de son usage.",
                    6000,
                )
            return
        self._voice_consent_pending_redirect = False
        self.voice_consent.clear_redirect_banner()
        self._stop_voice_players()
        self.statusBar().showMessage(
            "Conditions refusées : le clonage de voix est verrouillé.", 6000
        )
        if self.pages.currentIndex() == 1:
            self._select_settings()

    def _return_to_voice_after_consent(self) -> None:
        """Complete the round trip, unless consent was withdrawn meanwhile."""

        self._voice_consent_pending_redirect = False
        self.voice_consent.clear_redirect_banner()
        if not self._voice_cloning_accepted():
            return
        self._select_page(1)
        self.statusBar().showMessage(
            "Clonage de voix déverrouillé. Vous restez responsable de son usage.", 6000
        )

    def _apply_voice_lock_state(self) -> None:
        """Reflect the consent state on the navigation entry and the page."""

        accepted = self._voice_cloning_accepted()
        button = self.nav_buttons[1]
        button.setObjectName("navButton" if accepted else "navButtonLocked")
        if accepted:
            button.setIcon(QIcon())
            button.setText("◉  Clonage de voix")
        else:
            button.setIcon(get_icon("lock"))
            button.setText("Clonage de voix")
        button.setToolTip(
            "Cloner une voix locale"
            if accepted
            else "Verrouillé — acceptez les conditions d’utilisation du clonage de voix"
        )
        style = button.style()
        if style is not None:
            style.unpolish(button)
            style.polish(button)
        if hasattr(self, "voice_stack"):
            self.voice_stack.setCurrentIndex(1 if accepted else 0)
        if hasattr(self, "voice_consent"):
            self.voice_consent.set_accepted(accepted)

    def _open_voice_consent_settings(self) -> None:
        """Send the user straight to the terms that unlock the feature."""

        self._voice_consent_pending_redirect = True
        self._select_settings()
        if hasattr(self, "settings_tabs"):
            self.settings_tabs.setCurrentIndex(0)
        if hasattr(self, "voice_consent"):
            # Explain the jump, then pulse the exact row that unlocks the menu.
            self.voice_consent.flash(redirected=True)
            if hasattr(self, "voice_consent_scroll"):
                QTimer.singleShot(
                    0,
                    lambda: self.voice_consent_scroll.ensureWidgetVisible(
                        self.voice_consent.action_row
                    ),
                )
        self.statusBar().showMessage(
            "Cochez la case surlignée pour déverrouiller le clonage de voix.", 8000
        )

    def _stop_voice_players(self) -> None:
        for attribute in ("voice_sample_player", "voice_result_player"):
            player = getattr(self, attribute, None)
            if player is not None:
                player.stop()

    def _run_gpu_diagnostics(self) -> None:
        self.gpu_diagnostics_button.setEnabled(False)
        self.gpu_diagnostics.setText("Analyse locale en cours…")
        self.repaint()
        try:
            self.gpu_diagnostics.setText(collect_gpu_diagnostics(self.paths))
        except Exception as error:  # noqa: BLE001 - diagnostics must never crash the UI.
            self.gpu_diagnostics.setText(f"Diagnostic indisponible : {error}")
        finally:
            self.gpu_diagnostics_button.setEnabled(True)

    def _build_tray(self) -> None:
        app_icon = get_app_icon()
        icon = app_icon if not app_icon.isNull() else self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("SoundMaster")
        menu = QMenu(self)
        show = QAction("Afficher SoundMaster", self)
        show.triggered.connect(self._restore_from_tray)
        quit_action = QAction("Quitter", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda _reason: self._restore_from_tray())
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    _PAGE_TITLES: ClassVar[tuple[str, ...]] = (
        "Tableau de bord",
        "Clonage de voix",
        "Explorateur Myinstants",
        "Raccourcis",
        "Paramètres",
    )
    _PAGE_SUBTITLES: ClassVar[tuple[str, ...]] = (
        "Un espace calme pour vos sons, vos voix et vos raccourcis.",
        "Trois étapes : choisir une voix, l’écouter, générer.",
        "Cherchez, testez en direct, gardez vos favoris hors ligne.",
        "Déclenchez vos favoris pendant une partie, sans quitter le jeu.",
        "Vos périphériques, vos conditions d’utilisation et la conformité éditeur.",
    )

    def _select_page(self, index: int) -> None:
        if index == 1 and not self._voice_cloning_accepted():
            # The locked entry must stay clickable so it can explain itself.
            self._open_voice_consent_settings()
            return
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self._PAGE_TITLES[index])
        self.page_subtitle.setText(self._PAGE_SUBTITLES[index])
        current_page = self.pages.currentWidget()
        if current_page is not None:
            animate_opacity(current_page, 0.55, 1.0, 260)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index != 1:
            self._stop_voice_players()
        if index == 2 and not self._myinstants_catalog_loaded and self._network_thread is None:
            self._search_myinstants()
        if index == 3:
            self._refresh_keybinds()

    def _select_settings(self) -> None:
        self.pages.setCurrentIndex(4)
        self.page_title.setText(self._PAGE_TITLES[4])
        self.page_subtitle.setText(self._PAGE_SUBTITLES[4])
        current_page = self.pages.currentWidget()
        if current_page is not None:
            animate_opacity(current_page, 0.55, 1.0, 260)
        for button in self.nav_buttons:
            button.setChecked(False)
        self._stop_voice_players()

    def _preference_bool(self, key: str, default: bool) -> bool:
        return self.library.preference(key, str(default).lower()).lower() in {"1", "true", "yes", "on"}

    def _build_sound_card(self, sound: SoundItem, keybind: str = "") -> SoundCard:
        card = SoundCard(sound, keybind=keybind)
        card.play_requested.connect(self._play_sound)
        card.stop_requested.connect(self._stop_sound)
        card.favorite_changed.connect(self._set_favorite)
        card.rename_requested.connect(self._rename_sound)
        card.preview_hovered.connect(self._warm_local_preview)
        card.set_preview_playing(sound.id == self._active_preview_sound_id)
        return card

    def _refresh_dashboard(self) -> None:
        for grid in (self.card_grid, self.recent_grid):
            while grid.count():
                item = grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        query = self.dashboard_search.text() if hasattr(self, "dashboard_search") else ""
        sounds = self.library.sounds(query, True)
        bindings = self.library.keybinds()
        self.dashboard_hint.setText(
            f"{len(sounds)} favori(s) · Tester = casque · Envoyer = sortie 2"
        )
        self._dashboard_cards = [
            self._build_sound_card(sound, keybind=bindings.get(sound.id, ""))
            for sound in sounds
        ]
        self._reflow_grid(
            self.card_grid,
            self._dashboard_cards,
            self._grid_columns(self.card_container.width()),
        )
        # Eagerly preload all favorite sounds so playback is instant on click.
        self._prepare_favorite_players(sounds)
        for sound in sounds:
            if Path(sound.path).is_file():
                self._fast_audio.preload_sound(sound.path)
        # Favorites already have their own grid above; listing them again here
        # would just duplicate every card.
        recent = self.library.recent_sounds()
        if query.strip():
            needle = query.strip().lower()
            recent = [sound for sound in recent if needle in sound.title.lower()]
        self._recent_cards = [self._build_sound_card(sound) for sound in recent]
        self._reflow_grid(
            self.recent_grid,
            self._recent_cards,
            self._grid_columns(self.card_container.width()),
        )
        # Recent cards also expose a "Tester" button: decode them into the
        # zero-latency cache too, so a click never waits for the file I/O.
        for sound in recent:
            if Path(sound.path).is_file():
                self._fast_audio.preload_sound(sound.path)
        has_recent = bool(self._recent_cards)
        self.recent_header.setVisible(has_recent)
        self.recent_hint.setVisible(has_recent)

    def _rename_sound(self, sound_id: int) -> None:
        """Rename a favorite or a recently used sound in place."""

        matches = [item for item in self.library.sounds() if item.id == sound_id]
        if not matches:
            return
        current = matches[0]
        new_title, confirmed = QInputDialog.getText(
            self,
            "Renommer",
            "Nouveau nom :",
            QLineEdit.EchoMode.Normal,
            current.title,
        )
        if not confirmed:
            return
        try:
            self.library.rename_sound(sound_id, new_title)
        except ValueError as error:
            self.statusBar().showMessage(str(error), 5000)
            return
        self._refresh_dashboard()
        if self.pages.currentIndex() == 3:
            self._refresh_keybinds()
        self.statusBar().showMessage(f"Renommé en « {new_title.strip()} »", 4000)

    @staticmethod
    def _grid_columns(available_width: int, card_width: int = 280) -> int:
        """Choose readable 2–4 column layouts as the window width changes."""

        return max(2, min(4, max(1, available_width) // card_width))

    @staticmethod
    def _reflow_grid(grid: QGridLayout, widgets: list[QWidget], columns: int) -> None:
        """Reposition existing cards without destroying their state or signals."""

        while grid.count():
            grid.takeAt(0)
        for index, widget in enumerate(widgets):
            grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            grid.setColumnStretch(column, 1)

    def _relayout_responsive_grids(self) -> None:
        if hasattr(self, "card_grid"):
            columns = self._grid_columns(self.card_container.width())
            self._reflow_grid(self.card_grid, self._dashboard_cards, columns)
            self._reflow_grid(self.recent_grid, self._recent_cards, columns)
        if hasattr(self, "myinstants_grid"):
            self._reflow_grid(
                self.myinstants_grid,
                list(self._myinstant_cards.values()),
                self._grid_columns(self.myinstants_container.width()),
            )

    def _relayout_voice_controls(self) -> None:
        """Reflow voice controls instead of squeezing long labels into buttons."""

        if not hasattr(self, "_voice_setup_layout"):
            return
        compact = self.width() < 1040
        setup_layout = self._voice_setup_layout
        for widget in (
            self.voice_profile_combo,
            self._voice_new_setup_button,
            self._voice_delete_setup_button,
        ):
            setup_layout.removeWidget(widget)
        if compact:
            setup_layout.addWidget(self.voice_profile_combo, 0, 0, 1, 2)
            setup_layout.addWidget(self._voice_new_setup_button, 1, 0)
            setup_layout.addWidget(self._voice_delete_setup_button, 1, 1)
        else:
            setup_layout.addWidget(self.voice_profile_combo, 0, 0)
            setup_layout.addWidget(self._voice_new_setup_button, 0, 1)
            setup_layout.addWidget(self._voice_delete_setup_button, 0, 2)
        setup_layout.setColumnStretch(0, 1)
        setup_layout.setColumnStretch(1, 0)
        setup_layout.setColumnStretch(2, 0)

        record_layout = self._voice_record_layout
        for widget in self._voice_record_widgets:
            record_layout.removeWidget(widget)
        if compact:
            for row, widget in enumerate(self._voice_record_widgets):
                record_layout.addWidget(widget, row, 0)
        else:
            for column, widget in enumerate(self._voice_record_widgets):
                record_layout.addWidget(widget, 0, column)
        record_layout.setColumnStretch(0, 1)
        record_layout.setColumnStretch(1, 1 if not compact else 0)
        record_layout.setColumnStretch(2, 1 if not compact else 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout_voice_controls()
        self._relayout_responsive_grids()

    def _refresh_voice_history(self) -> None:
        if not hasattr(self, "voice_history"):
            return
        self.voice_history.clear()
        query = self.voice_search.text() if hasattr(self, "voice_search") else ""
        for generation in self.library.voice_generations(query):
            item = QListWidgetItem(
                f"{generation.title} · {generation.created_at} · {generation.model}"
            )
            item.setToolTip(
                f"Texte : {generation.text}\nSortie : {generation.output_path}\n"
                "Double-cliquez pour réécouter."
            )
            item.setData(Qt.ItemDataRole.UserRole, generation.output_path)
            self.voice_history.addItem(item)

    def _play_history_item(self, item: QListWidgetItem) -> None:
        """Replay a past generation in the result player."""

        stored = item.data(Qt.ItemDataRole.UserRole)
        path = Path(str(stored)) if stored else None
        if path is None or not path.is_file():
            self.statusBar().showMessage(
                "Ce fichier généré n’existe plus sur le disque.", 5000
            )
            return
        self._set_last_generation(path, item.text().split(" · ")[0])
        self.voice_result_player.play()

    def _populate_audio_devices(self) -> None:
        if QMediaDevices is None:
            self.microphone_input.addItem("QtMultimedia indisponible")
            self.headset_output.addItem("QtMultimedia indisponible")
            self.virtual_output.addItem("QtMultimedia indisponible")
            return
        for device in QMediaDevices.audioInputs():
            self.microphone_input.addItem(device.description(), device)
        if not self.microphone_input.count():
            self.microphone_input.addItem("Aucun microphone détecté")
        outputs = list(QMediaDevices.audioOutputs())
        # The second output is a power-user option: a virtual cable is only
        # needed to route sounds into a game. Beginners must never be forced
        # to install or pick one, so "Aucun" is the default choice.
        self.virtual_output.addItem("Aucun (désactivé)", None)
        for device in outputs:
            self.headset_output.addItem(device.description(), device)
            self.virtual_output.addItem(device.description(), device)
        if not outputs:
            self.headset_output.addItem("Aucune sortie détectée")
            self.virtual_output.addItem("Aucune sortie détectée")
            return
        default = QMediaDevices.defaultAudioOutput().description()
        for combo, key in ((self.headset_output, "headset_device"), (self.virtual_output, "virtual_device")):
            index = combo.findText(self.library.preference(key, default))
            if index < 0:
                index = combo.findText(default)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _detect_virtual_cable(self) -> str | None:
        """Return the description of the first virtual-cable output, if any.

        VB-CABLE (and equivalents) name their devices with the word "Cable"
        or "VB-Audio", so a plain keyword scan over the WASAPI output list is
        enough to know whether the app should offer to install one.
        """

        if QMediaDevices is None:
            return None
        markers = ("cable", "vb-audio", "vb audio", "virtual", "voicemeeter")
        for device in QMediaDevices.audioOutputs():
            description = device.description()
            lowered = description.lower()
            if any(marker in lowered for marker in markers):
                return description
        return None

    def _update_virtual_cable_status(self) -> None:
        """Tell the user whether a virtual cable is installed, and offer the
        official installer when it is not."""

        cable = self._detect_virtual_cable()
        if cable is None:
            self.virtual_cable_status.setText(
                "<b style='color:#b3261e'>Aucun câble virtuel détecté.</b> "
                "Pour envoyer un son directement dans un jeu, installez un câble "
                "virtuel (VB-CABLE, gratuit et officiel) puis cliquez sur "
                "« Actualiser les périphériques » pour le faire apparaître ici."
            )
            self.install_cable_button.setVisible(True)
        else:
            self.virtual_cable_status.setText(
                f"<b style='color:#137333'>Câble virtuel détecté : {cable}.</b> "
                "Choisissez-le en « Sortie 2 » pour envoyer les sons dans un jeu."
            )
            self.install_cable_button.setVisible(False)

    def _refresh_audio_devices(self) -> None:
        """Re-scan the audio inputs/outputs after a driver or cable install."""

        self.microphone_input.clear()
        self.headset_output.clear()
        self.virtual_output.clear()
        self._populate_audio_devices()
        self._update_virtual_cable_status()
        self.statusBar().showMessage("Périphériques audio actualisés", 4000)

    def _open_virtual_cable_download(self) -> None:
        """Open the official VB-CABLE download page (free for personal use)."""

        QDesktopServices.openUrl(QUrl("https://vb-audio.com/Cable/"))

    def _apply_audio_devices(self) -> None:
        if QAudioOutput is None or not self._audio_outputs:
            self.statusBar().showMessage("QtMultimedia indisponible", 5000)
            return
        headset_text = self.headset_output.currentText()
        virtual_device = self.virtual_output.currentData()
        # A second output is optional: "Aucun" or picking the same device
        # simply means every sound plays on the headset output.
        virtual_disabled = virtual_device is None or self.virtual_output.currentText() == headset_text
        for key, virtual, combo in (("headset_device", False, self.headset_output), ("virtual_device", True, self.virtual_output)):
            device = None if (virtual and virtual_disabled) else combo.currentData()
            if device is not None:
                self._audio_outputs[virtual].setDevice(device)
                self.library.set_preference(key, combo.currentText())
                if not virtual:
                    # Voice previews follow the headset, never the virtual cable.
                    for player in (self.voice_sample_player, self.voice_result_player):
                        player.set_device(device)
        self._fast_audio.set_devices(
            self.headset_output.currentData() if headset_text else None,
            None if virtual_disabled else virtual_device,
        )
        self.library.set_preference("microphone_device", self.microphone_input.currentText())
        if self._hotkeys.active:
            self._prepare_hotkey_players()
        self.statusBar().showMessage("Sorties audio enregistrées", 5000)

    def _add_local_file(self) -> None:
        """Add an audio OR video file to the favorites.

        Videos are decoded to WAV first (via PyAV) so the zero-latency engine,
        which reads audio files directly, can play them like any other favorite.
        The converted file lives inside the managed audio-cache folder.
        """

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un audio ou une vidéo",
            "",
            "Audio et vidéo (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus "
            "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv *.flv *.mpg *.mpeg "
            "*.ts *.3gp *.ogv)",
        )
        if not filename:
            return
        source = Path(filename)
        if is_video_file(source):
            destination = self._managed_video_sound_destination(source)
            try:
                extract_audio_from_video(source, destination)
            except VideoAudioExtractionError as error:
                QMessageBox.warning(self, "Import impossible", str(error))
                return
            self._add_sound_to_favorites(destination, source.stem, "local")
            self.statusBar().showMessage(
                f"Vidéo « {source.stem} » convertie en audio et ajoutée aux favoris", 5000
            )
            return
        self._add_sound_to_favorites(source, source.stem, "local")

    def _managed_video_sound_destination(self, source: Path) -> Path:
        """Collision-free WAV path for a converted video inside the audio cache."""

        folder = self.paths.audio_cache / "imported-videos"
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{source.stem}.wav"
        counter = 2
        while destination.exists():
            destination = folder / f"{source.stem}-{counter}.wav"
            counter += 1
        return destination

    def _add_sound_to_favorites(self, path: Path, title: str, source: str) -> None:
        if self._bulk_active and source != "Myinstants":
            self.statusBar().showMessage("Attendez la fin du téléchargement groupé avant d’ajouter un autre favori.", 5000)
            return
        if len(self.library.sounds(favorites_only=True)) >= self.config.favorite_limit:
            QMessageBox.warning(self, "Limite atteinte", f"Limite de {self.config.favorite_limit} favoris atteinte.")
            return
        self.library.add_sound(title, path, source, True)
        self._refresh_dashboard()
        self.statusBar().showMessage(f"{title} ajouté aux favoris", 4000)

    def _play_file(self, path: Path, virtual: bool = False) -> None:
        path_str = str(path)
        player = self._players.get(virtual)
        if player is not None and type(player).__name__ == "_FakePlayer":
            if self._player_sources.get(virtual) != path_str:
                player.setSource(QUrl.fromLocalFile(path_str))
                self._player_sources[virtual] = path_str
            else:
                player.setPosition(0)
            player.play()
            self.statusBar().showMessage("Lecture vers la sortie 2" if virtual else "Lecture locale", 3000)
            return

        # Instant low-latency playback via FastAudioEngine (< 2 ms)
        if Path(path).is_file():
            if self._fast_audio.play(path, virtual):
                self.statusBar().showMessage("Lecture vers la sortie 2" if virtual else "Lecture locale", 3000)
                return

        # Fallback to Qt QMediaPlayer
        preloaded = self._favorite_players.get(path_str + (":v" if virtual else ":h"))
        if preloaded is not None:
            preloaded[0].setPosition(0)
            preloaded[0].play()
            self.statusBar().showMessage("Lecture vers la sortie 2" if virtual else "Lecture locale", 3000)
            return
        if player is None:
            self.statusBar().showMessage("QtMultimedia indisponible", 5000)
            return
        if self._player_sources.get(virtual) != path_str:
            player.setSource(QUrl.fromLocalFile(path_str))
            self._player_sources[virtual] = path_str
        else:
            player.setPosition(0)
        player.play()
        self.statusBar().showMessage("Lecture vers la sortie 2" if virtual else "Lecture locale", 3000)

    def _warm_local_preview(self, sound_id: int) -> None:
        """Preload a favorite on hover so the click starts playback instantly.

        Both the local headset player and the virtual cable player are warmed
        so that either "Tester" or "Envoyer" starts with near-zero latency.
        """

        matches = [item for item in self.library.sounds() if item.id == sound_id]
        if not matches:
            return
        path = str(Path(matches[0].path))
        # Decode into the zero-latency PCM cache while the pointer travels, so
        # the click only queues the buffer instead of decoding the file.
        self._fast_audio.preload_sound(path)
        if QMediaPlayer is None:
            return
        for virtual in (False, True):
            player = self._players.get(virtual)
            if player is None:
                continue
            if player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
                continue
            if self._player_sources.get(virtual) == path:
                continue
            player.setSource(QUrl.fromLocalFile(path))
            self._player_sources[virtual] = path
        self._remote_preview_url = None

    def _local_playback_state_changed(self, state) -> None:
        if QMediaPlayer is None:
            return
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self._set_active_preview(None)
            self._set_active_remote_preview(None)

    def _set_active_remote_preview(self, audio_url: str | None) -> None:
        """Update exactly one Myinstants card to its playing/stopped state."""

        self._active_remote_preview_url = audio_url
        for card_url, card in getattr(self, "_myinstant_cards", {}).items():
            card.set_preview_playing(card_url == audio_url)

    def _set_active_preview(self, sound_id: int | None) -> None:
        self._active_preview_sound_id = sound_id
        for card in getattr(self, "_dashboard_cards", []):
            card.set_preview_playing(card.item.id == sound_id)

    def _on_fast_audio_finished(self) -> None:
        """Release the preview state when the zero-latency engine drains.

        The FastAudioEngine plays through a persistent background stream that
        has no QMediaPlayer state to report: without this, the "Stop" button
        stayed active forever after a sound ended.
        """

        if self._active_preview_sound_id is not None:
            self._set_active_preview(None)

    def _stop_sound(self, sound_id: int) -> None:
        if self._active_preview_sound_id != sound_id:
            return
        self._fast_audio.stop(False)
        player = self._players.get(False)
        if player is not None:
            player.stop()
        self._set_active_preview(None)
        self.statusBar().showMessage("Lecture arrêtée", 2500)

    def _player_error(self, virtual: bool) -> None:
        if virtual:
            self.statusBar().showMessage("Lecture vers la sortie 2 impossible", 5000)
        else:
            self._set_active_preview(None)
            self._set_active_remote_preview(None)
        if not virtual and self._remote_preview_title:
            self.myinstants_status.setText(
                f"Aperçu indisponible pour « {self._remote_preview_title} »"
            )
            self._remote_preview_title = None

    def _warm_remote_preview(self, result: MyInstantResult) -> None:
        """Start a short prebuffer on hover without interrupting active playback."""

        if self._active_remote_preview_url not in (None, result.audio_url):
            return
        if result.audio_url == self._remote_preview_url:
            return
        self._remote_preview_url = result.audio_url
        if self._remote_preview_warm_timer is not None:
            self._remote_preview_warm_timer.stop()
        self._remote_preview_warm_timer = QTimer(self)
        self._remote_preview_warm_timer.setSingleShot(True)
        self._remote_preview_warm_timer.timeout.connect(
            lambda url=result.audio_url: self._prepare_remote_player(url)
        )
        self._remote_preview_warm_timer.start(120)

    def _prepare_remote_player(self, url: str) -> None:
        self._set_active_preview(None)
        player = self._players.get(False)
        if player is None:
            return
        player.setSource(QUrl(url))
        self._player_sources[False] = url
        # Do not play on hover: QMediaPlayer will resolve and buffer the source,
        # while the click below only needs to issue play().

    def _play_remote(self, url: str, virtual: bool = False, title: str | None = None) -> None:
        """Play or stop a Myinstants preview without writing it to disk."""

        player = self._players.get(virtual)
        if player is None:
            self.statusBar().showMessage("QtMultimedia indisponible", 5000)
            return
        if not virtual and self._active_remote_preview_url == url:
            player.stop()
            self._set_active_remote_preview(None)
            self._remote_preview_title = None
            self.statusBar().showMessage("Aperçu arrêté", 2500)
            return
        if not virtual:
            if self._active_remote_preview_url is not None:
                player.stop()
            self._set_active_preview(None)
            self._set_active_remote_preview(None)
        self._remote_preview_title = title
        if virtual or self._remote_preview_url != url:
            self._remote_preview_url = url
            player.setSource(QUrl(url))
            self._player_sources[virtual] = url
        player.play()
        if not virtual:
            self._set_active_remote_preview(url)
        self.statusBar().showMessage("Lecture immédiate — aperçu non téléchargé", 4000)

    def _play_sound(self, sound_id: int, virtual: bool) -> None:
        matches = [item for item in self.library.sounds() if item.id == sound_id]
        if matches:
            if not virtual and self._active_preview_sound_id == sound_id:
                self._stop_sound(sound_id)
                return
            if not virtual and self._active_preview_sound_id is not None:
                old_player = self._players.get(False)
                if old_player is not None:
                    old_player.stop()
            # A shortcut fired mid-game has no hover to warm the player, so it
            # uses the dedicated preloaded one when there is a binding for it.
            preloaded = self._hotkey_players.get(sound_id) if virtual else None
            if preloaded is not None:
                player = preloaded[0]
                player.setPosition(0)
                player.play()
                self.statusBar().showMessage("Lecture vers la sortie 2", 3000)
            else:
                self._play_file(Path(matches[0].path), virtual)
            if not virtual:
                self._set_active_preview(sound_id)
            # Defer the database write so it never delays audio start.
            QTimer.singleShot(0, lambda sid=sound_id: self.library.record_use(sid))

    def _prepare_hotkey_players(self) -> None:
        """Keep one preloaded player per bound favorite for instant shortcuts.

        Bindings are capped by the favorite limit, so this pool stays small.
        """

        self._release_hotkey_players()
        if QMediaPlayer is None or QAudioOutput is None:
            return
        device = self.virtual_output.currentData() if hasattr(self, "virtual_output") else None
        sounds = {item.id: item for item in self.library.sounds("", True)}
        for sound_id in self.library.keybinds():
            sound = sounds.get(sound_id)
            if sound is None or not Path(sound.path).is_file():
                continue
            try:
                output = QAudioOutput(self)
                if device is not None:
                    output.setDevice(device)
                output.setVolume(1.0)
                player = QMediaPlayer(self)
                player.setAudioOutput(output)
                player.setSource(QUrl.fromLocalFile(sound.path))
            except Exception:  # noqa: BLE001 - optional multimedia backend boundary.
                self._release_hotkey_players()
                return
            self._hotkey_players[sound_id] = (player, output)

    def _release_hotkey_players(self) -> None:
        # This also runs from closeEvent, so it must never raise on shutdown.
        for player, output in self._hotkey_players.values():
            for target, method in ((player, "stop"), (player, "deleteLater"), (output, "deleteLater")):
                call = getattr(target, method, None)
                if callable(call):
                    call()
        self._hotkey_players.clear()

    def _prepare_favorite_players(self, sounds: list | None = None) -> None:
        """Preload a dedicated QMediaPlayer per favorite for instant playback.

        Each sound gets two players: one for the headset and one for the virtual
        cable. This bypasses the slow setSource() call on click entirely.
        """

        self._release_favorite_players()
        if QMediaPlayer is None or QAudioOutput is None:
            return
        if sounds is None:
            sounds = self.library.sounds("", True)
        headset_device = self.headset_output.currentData() if hasattr(self, "headset_output") else None
        virtual_device = self.virtual_output.currentData() if hasattr(self, "virtual_output") else None
        for sound in sounds:
            if not Path(sound.path).is_file():
                continue
            for virtual, device in ((False, headset_device), (True, virtual_device)):
                key = sound.path + (":v" if virtual else ":h")
                try:
                    output = QAudioOutput(self)
                    if device is not None:
                        output.setDevice(device)
                    output.setVolume(1.0)
                    player = QMediaPlayer(self)
                    player.setAudioOutput(output)
                    player.setSource(QUrl.fromLocalFile(sound.path))
                except Exception:  # noqa: BLE001 - optional multimedia backend boundary.
                    self._release_favorite_players()
                    return
                self._favorite_players[key] = (player, output)

    def _release_favorite_players(self) -> None:
        for player, output in self._favorite_players.values():
            for target, method in ((player, "stop"), (player, "deleteLater"), (output, "deleteLater")):
                call = getattr(target, method, None)
                if callable(call):
                    call()
        self._favorite_players.clear()

    def _set_favorite(self, sound_id: int, favorite: bool) -> None:
        if favorite and len(self.library.sounds(favorites_only=True)) >= self.config.favorite_limit:
            QMessageBox.warning(
                self,
                "Limite atteinte",
                f"Limite de {self.config.favorite_limit} favoris atteinte.",
            )
            # Redraw so the star returns to the state actually stored.
            self._refresh_dashboard()
            return
        self.library.set_favorite(sound_id, favorite)
        self._refresh_dashboard()

    def _voice_settings(self) -> dict[str, object]:
        """Return generation controls; F5 emotion markers live in the text."""

        return {
            "temperature": self.voice_temperature.value(),
            "speed": self.voice_speed.value(),
            "top_p": self.voice_top_p.value(),
            "repetition_penalty": self.voice_repetition_penalty.value(),
            "pocket_high_quality": self.voice_high_quality.isChecked(),
            "pocket_quantize": self.voice_quantize.isChecked(),
            "pocket_mirror": self.library.preference(MIRROR_PREFERENCE_KEY, DEFAULT_MIRROR_REPO),
            # Kept for compatibility with older workers; the editor now embeds
            # the markers directly into the generation text.
            "emotion_prompt": "",
        }

    def _select_f5_emotion(self, emotion_key: str) -> None:
        """Select an emotion and apply/toggle it when text is already selected."""

        if emotion_key not in F5_EMOTION_BY_KEY:
            return
        self._active_f5_emotion = emotion_key
        for key, button in self.voice_emotion_buttons.items():
            button.setChecked(key == emotion_key)
        self._apply_active_f5_emotion()

    def _char_f5_emotion(self, position: int) -> str | None:
        cursor = QTextCursor(self.voice_text.document())
        cursor.setPosition(position)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        value = cursor.charFormat().property(EMOTION_FORMAT_PROPERTY)
        return value if isinstance(value, str) and value in F5_EMOTION_BY_KEY else None

    def _apply_active_f5_emotion(self) -> None:
        """Apply the selected palette emotion, or remove it when toggled."""

        emotion_key = getattr(self, "_active_f5_emotion", None)
        cursor = self.voice_text.textCursor()
        if not emotion_key or not cursor.hasSelection():
            return
        start, end = sorted((cursor.selectionStart(), cursor.selectionEnd()))
        if start == end:
            return
        spans = self._f5_emotion_spans(self.voice_text.toPlainText())
        remove = all(
            any(span.start <= position < span.end and span.emotion == emotion_key for span in spans)
            for position in range(start, end)
        )
        if remove:
            # ``mergeCharFormat`` cannot remove a property that is absent from
            # the format being merged, so clear the selected format explicitly.
            format_ = cursor.charFormat()
            format_.clearBackground()
            format_.clearForeground()
            format_.clearProperty(EMOTION_FORMAT_PROPERTY)
            cursor.setCharFormat(format_)
        else:
            format_ = QTextCharFormat()
            emotion = F5_EMOTION_BY_KEY[emotion_key]
            format_.setBackground(QColor(emotion.background))
            format_.setForeground(QColor(emotion.foreground))
            format_.setProperty(EMOTION_FORMAT_PROPERTY, emotion_key)
            cursor.mergeCharFormat(format_)
        self.voice_text.setTextCursor(cursor)

    def _f5_emotion_spans(self, text: str) -> list[EmotionSpan]:
        """Read contiguous emotion formatting ranges from the visible editor."""

        spans: list[EmotionSpan] = []
        active: str | None = None
        start = 0
        for position in range(len(text)):
            emotion = self._char_f5_emotion(position)
            if emotion == active:
                continue
            if active is not None and start < position:
                spans.append(EmotionSpan(start, position, active))
            active = emotion
            start = position
        if active is not None and start < len(text):
            spans.append(EmotionSpan(start, len(text), active))
        return spans

    def _f5_generation_text(self) -> str:
        """Convert editor colours into F5 markers for an F5 generation."""

        plain = self.voice_text.toPlainText()
        return render_emotion_tags(plain, self._f5_emotion_spans(plain))

    def _voice_language(self) -> str:
        """Return the canonical engine token, not the translated label."""

        return str(self.voice_language.currentData() or "Auto")

    def _sync_pocket_quality_control(self) -> None:
        """Only offer the quality variant for languages that actually have one."""

        if not hasattr(self, "voice_high_quality"):
            return
        is_pocket = str(self.voice_engine.currentData() or "") == "pocket-tts"
        language = self._voice_language()
        has_variant = pocket_has_quality_variant(language)
        self.voice_high_quality.setEnabled(is_pocket and has_variant)
        if not is_pocket:
            return
        if has_variant:
            self.voice_high_quality.setToolTip(
                "Variante 24 couches de cette langue : meilleure qualité, "
                "génération plus lente."
            )
        elif language == "French":
            self.voice_high_quality.setToolTip(
                "Le français n’existe qu’en modèle 24 couches : il est déjà utilisé."
            )
        else:
            self.voice_high_quality.setToolTip(
                "Cette langue ne publie qu’un seul modèle."
            )

    def _set_voice_advanced_visible(self, visible: bool) -> None:
        """Show the advanced form and make it reachable inside the details scroll area."""

        self.voice_advanced.setVisible(visible)
        if hasattr(self, "voice_page_scroll"):
            inner = self.voice_page_scroll.widget()
            if inner is not None:
                inner.adjustSize()
                inner.updateGeometry()
            self.voice_page_scroll.updateGeometry()

        def reveal_after_layout() -> None:
            """Scroll only after Qt has applied the new layout geometry."""

            if visible and self.voice_advanced.isVisible():
                self.voice_page_scroll.ensureWidgetVisible(self.voice_advanced)

        QTimer.singleShot(0, reveal_after_layout)
        self.voice_profile_status.setText(
            "Réglages avancés ouverts · ils sont sauvegardés avec la voix"
            if visible
            else "Réglages avancés masqués · la voix reste inchangée"
        )

    def _voice_profile_changed(self, index: int) -> None:
        if index < 0:
            self._editing_voice_profile_id = None
            self.voice_profile_name.clear()
            self.voice_profile_status.setText(
                "Créez une voix ou choisissez-en une, puis ajoutez son échantillon à l’étape 2."
            )
            self.delete_voice_button.setEnabled(False)
            return
        profile_id = self.voice_profile_combo.itemData(index)
        profile = next(
            (item for item in self.library.voice_profiles() if item.id == profile_id),
            None,
        )
        if profile is None:
            self._editing_voice_profile_id = None
            self.voice_profile_status.setText("Voix introuvable dans la banque")
            self.delete_voice_button.setEnabled(False)
            return
        self._editing_voice_profile_id = profile.id
        self.voice_profile_name.setText(profile.name)
        self._set_voice_sample(Path(profile.sample_path))
        self.voice_reference_text.setText(profile.ref_text)
        engine_index = self.voice_engine.findData(profile.engine_key)
        if engine_index >= 0:
            self.voice_engine.setCurrentIndex(engine_index)
        language_index = self.voice_language.findData(profile.language)
        if language_index < 0:
            # Voices saved before the labels were translated stored the label.
            language_index = self.voice_language.findText(profile.language)
        if language_index >= 0:
            self.voice_language.setCurrentIndex(language_index)
        settings = profile.settings
        for widget, key in (
            (self.voice_temperature, "temperature"),
            (self.voice_speed, "speed"),
            (self.voice_top_p, "top_p"),
            (self.voice_repetition_penalty, "repetition_penalty"),
        ):
            value = settings.get(key)
            if isinstance(value, (int, float)):
                widget.setValue(float(value))
        for checkbox, key in (
            (self.voice_high_quality, "pocket_high_quality"),
            (self.voice_quantize, "pocket_quantize"),
        ):
            checkbox.setChecked(bool(settings.get(key, False)))
        capture_output = settings.get("capture_output")
        capture_index = self.voice_capture_output.findData(capture_output)
        if capture_index < 0 and isinstance(capture_output, str):
            capture_index = self.voice_capture_output.findText(capture_output)
        if capture_index >= 0:
            self.voice_capture_output.setCurrentIndex(capture_index)
        self.voice_profile_status.setText(
            f"Voix « {profile.name} » chargée · écoutez son échantillon à l’étape 2"
            if self.voice_sample_player.has_source()
            else f"Voix « {profile.name} » chargée, mais son échantillon est introuvable. "
            "Recapturez-le à l'étape 2."
        )
        self.delete_voice_button.setEnabled(True)

    def _refresh_voice_profiles(self) -> None:
        if not hasattr(self, "voice_profile_combo"):
            return
        selected_id = self.voice_profile_combo.currentData()
        profiles = self.library.voice_profiles()
        self.voice_profile_combo.blockSignals(True)
        self.voice_profile_combo.clear()
        for profile in profiles:
            self.voice_profile_combo.addItem(profile.name, profile.id)
        if profiles:
            index = self.voice_profile_combo.findData(
                selected_id if selected_id is not None else profiles[0].id
            )
            self.voice_profile_combo.setCurrentIndex(max(0, index))
        else:
            self.voice_profile_combo.setCurrentIndex(-1)
        self.voice_profile_combo.blockSignals(False)
        self._voice_profile_changed(self.voice_profile_combo.currentIndex())

    def _start_new_voice_profile(self) -> None:
        """Start a blank voice; audio is added at step 2."""

        self._editing_voice_profile_id = None
        self.voice_profile_combo.blockSignals(True)
        self.voice_profile_combo.setCurrentIndex(-1)
        self.voice_profile_combo.blockSignals(False)
        self.voice_profile_name.clear()
        self._set_voice_sample(None)
        self.voice_reference_text.clear()
        default_engine = self.library.preference("default_voice_engine", "pocket-tts")
        default_index = self.voice_engine.findData(default_engine)
        self.voice_engine.setCurrentIndex(max(default_index, 0))
        # The global default language drives the new voice. A French application
        # defaults to the French bundle: leaving it on the engine default would
        # silently clone with the English model.
        self.voice_profile_status.setText(
            "Nouvelle voix : donnez-lui un nom, puis capturez son échantillon à l'étape 2."
        )
        default_lang = self.library.preference(DEFAULT_LANGUAGE_PREFERENCE, "French")
        default_lang_index = self.voice_language.findData(default_lang)
        self.voice_language.setCurrentIndex(max(0, default_lang_index))
        self.voice_high_quality.setChecked(False)
        self.voice_quantize.setChecked(False)
        self.voice_temperature.setValue(0.7)
        self.voice_speed.setValue(1.0)
        self.voice_top_p.setValue(0.9)
        self.voice_repetition_penalty.setValue(1.05)
        self.delete_voice_button.setEnabled(False)
        self.voice_profile_name.setFocus()

    def _set_voice_sample(self, path: Path | None) -> None:
        """Keep the path field and the sample player in sync, always.

        When a sample is loaded, hide record/import buttons to prevent
        accidental overwrites.  Show the red "Retirer" button instead.
        """

        has_sample = path is not None and str(path).strip() != ""
        self.voice_sample.setText(str(path) if has_sample else "")
        self.voice_sample_player.set_source(path if has_sample else None)
        for widget in self._voice_record_widgets:
            widget.setVisible(not has_sample)
        self.voice_remove_sample_button.setVisible(has_sample)

    def _managed_sample_destination(self, source: Path) -> Path:
        """Return a collision-free path inside SoundMaster's managed sample folder.

        Videos are stored as ``.wav`` (they are converted on import), so a
        video and its name never collide with an audio file of the same stem.
        """

        self.paths.voice_samples.mkdir(parents=True, exist_ok=True)
        destination = self.paths.voice_samples / sample_destination(source, self.paths.voice_samples).name
        stem, suffix = destination.stem, destination.suffix
        counter = 2
        while destination.exists() and destination.resolve() != source.resolve():
            destination = self.paths.voice_samples / f"{stem}-{counter}{suffix}"
            counter += 1
        return destination

    def _import_voice_sample(self) -> None:
        """Import an audio OR video sample; videos are converted to audio.

        A video (screen recording, phone capture, …) is decoded to WAV through
        PyAV automatically, so the user never has to convert anything: the rest
        of the app only ever sees a ready-to-use audio clip.
        """

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un échantillon vocal (audio ou vidéo)",
            "",
            "Audio et vidéo (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus "
            "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.wmv *.flv *.mpg *.mpeg "
            "*.ts *.3gp *.ogv)",
        )
        if not filename:
            return
        source = Path(filename)
        destination = self._managed_sample_destination(source)
        if source.resolve() == destination.resolve():
            self._set_voice_sample(destination)
        elif is_video_file(source):
            try:
                extract_audio_from_video(source, destination)
            except VideoAudioExtractionError as error:
                QMessageBox.warning(
                    self,
                    "Import impossible",
                    str(error),
                )
                return
            self.voice_profile_status.setText(
                "Vidéo importée et convertie en audio automatiquement. "
                "Écoutez le résultat ci-dessus, puis testez la voix à l’étape 3."
            )
        else:
            shutil.copy2(source, destination)
            self.voice_profile_status.setText(
                "Échantillon importé. Écoutez-le ci-dessus, puis testez la voix à l’étape 3."
            )
        self._set_voice_sample(destination)

    def _remove_voice_sample(self) -> None:
        """Remove the currently loaded sample and re-show capture/import buttons."""

        self._set_voice_sample(None)
        self.voice_profile_status.setText(
            "Échantillon retiré. Capturez ou importez un nouvel audio ou une vidéo ci-dessus."
        )

    def _cleanup_managed_voice_sample(self, sample_path: Path) -> None:
        """Remove an unused sample only when it belongs to SoundMaster's bank."""

        try:
            managed_root = self.paths.voice_samples.resolve()
            resolved = sample_path.resolve()
            is_managed = resolved.is_relative_to(managed_root)
        except (OSError, ValueError):
            is_managed = False
        if not is_managed or self.library.voice_profile_sample_references(sample_path):
            return
        try:
            sample_path.unlink(missing_ok=True)
        except OSError as error:
            self.statusBar().showMessage(
                f"Ancien échantillon conservé : {error}", 6000
            )

    def _save_voice_profile(self) -> None:
        """Persist the named voice and all advanced controls in one action."""

        name = self.voice_profile_name.text().strip()
        sample = Path(self.voice_sample.text().strip())
        if not name:
            self.statusBar().showMessage("Donnez un nom à cette voix avant de la sauvegarder", 5000)
            self.voice_profile_name.setFocus()
            return
        if not sample.is_file():
            self.statusBar().showMessage(
                "Ajoutez d’abord un échantillon à l’étape 2 : micro, sortie audio ou fichier",
                6000,
            )
            return

        settings = {
            **self._voice_settings(),
            "capture_output": self.voice_capture_output.currentData(),
        }
        engine_key = str(self.voice_engine.currentData() or "pocket-tts")
        language = self._voice_language()
        if self._editing_voice_profile_id is None:
            profile = self.library.add_voice_profile(
                name,
                sample,
                self.voice_reference_text.text(),
                engine_key,
                language,
                settings,
            )
        else:
            previous_profile = next(
                (
                    item
                    for item in self.library.voice_profiles()
                    if item.id == self._editing_voice_profile_id
                ),
                None,
            )
            previous_sample = (
                Path(previous_profile.sample_path) if previous_profile is not None else None
            )
            try:
                profile = self.library.update_voice_profile(
                    self._editing_voice_profile_id,
                    name=name,
                    ref_text=self.voice_reference_text.text(),
                    engine_key=engine_key,
                    language=language,
                    settings=settings,
                    sample_path=sample,
                )
            except ValueError as error:
                self.statusBar().showMessage(str(error), 7000)
                return
            if previous_sample is not None and previous_sample != sample:
                self._cleanup_managed_voice_sample(previous_sample)
        if profile is None:
            self.statusBar().showMessage("Impossible de sauvegarder cette voix", 6000)
            return
        self._editing_voice_profile_id = profile.id
        self._refresh_voice_profiles()
        index = self.voice_profile_combo.findData(profile.id)
        if index >= 0:
            self.voice_profile_combo.setCurrentIndex(index)
        self.voice_profile_status.setText(
            f"Voix « {profile.name} » sauvegardée · réglages et échantillon gardés en local"
        )
        self.statusBar().showMessage(f"Voix « {profile.name} » sauvegardée", 5000)

    def _delete_voice_profile(self) -> None:
        profile_id = self.voice_profile_combo.currentData()
        if profile_id is None:
            return
        profile = next(
            (item for item in self.library.voice_profiles() if item.id == profile_id),
            None,
        )
        if profile is None:
            return
        answer = QMessageBox.question(
            self,
            "Supprimer cette voix ?",
            f"Supprimer « {profile.name} » et son échantillon du dossier SoundMaster ?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        sample_path = self.library.delete_voice_profile(int(profile_id))
        if sample_path is not None:
            self._cleanup_managed_voice_sample(sample_path)
        self._refresh_voice_profiles()
        self.statusBar().showMessage("Voix supprimée de la banque", 5000)

    def _populate_voice_capture_outputs(self) -> None:
        """Populate the capture selector with PortAudio's actual WASAPI indexes."""

        try:
            import sounddevice as sd

            for name, index in wasapi_output_devices(sd):
                self.voice_capture_output.addItem(name, index)
        except Exception as error:  # noqa: BLE001 - optional backend discovery must not break UI startup.
            self.voice_capture_output.setToolTip(
                f"Sorties WASAPI indisponibles : {error}. La sortie système par défaut sera utilisée."
            )
        if self.voice_capture_output.count() == 0:
            self.voice_capture_output.addItem("Sortie système par défaut", None)

    def _register_recorded_sample(self, path: Path, prefix: str) -> None:
        """Attach a completed recording to the current draft, ready to replay."""

        if not (path.is_file() and path.stat().st_size > 0):
            self.statusBar().showMessage("Aucun échantillon audio exploitable n’a été créé", 6000)
            return
        self._set_voice_sample(path)
        # Loaded but never auto-played: the user decides when to listen, which
        # also avoids a surprise burst through the speakers after a take.
        self.voice_profile_status.setText(
            f"{prefix} terminé. Cliquez sur ▶ pour réécouter votre échantillon, "
            "puis testez la voix à l’étape 3."
        )

    def _toggle_micro_recording(self) -> None:
        self._toggle_recording()

    def _toggle_system_recording(self) -> None:
        if self._system_recording_thread is not None and self._system_recording_thread.is_alive():
            if self._system_recorder is not None:
                self._system_recorder.stop()
            self.voice_system_record_button.setText("Arrêt…")
            return
        capability_error = SystemAudioRecorder.capability_error()
        if capability_error is not None:
            self.voice_system_record_button.setToolTip(capability_error)
            self.statusBar().showMessage(capability_error, 9000)
            QMessageBox.warning(self, "Capture de sortie indisponible", capability_error)
            return
        self.paths.voice_samples.mkdir(parents=True, exist_ok=True)
        self._system_recording_path = self.paths.voice_samples / (
            f"discord-output-{datetime.now(UTC):%Y%m%d-%H%M%S%f}.wav"
        )
        device = self.voice_capture_output.currentData()
        self._system_recorder = SystemAudioRecorder(self._system_recording_path, device)
        self._system_recording_error: str | None = None
        self.voice_system_record_button.setToolTip(
            "Capture en cours. Cliquez à nouveau pour arrêter et conserver l’échantillon."
        )

        def record() -> None:
            try:
                assert self._system_recorder is not None
                self._system_recorder.start()
            except Exception as error:  # noqa: BLE001 - optional audio backend boundary.
                self._system_recording_error = str(error)

        self._system_recording_thread = Thread(target=record, daemon=True)
        self._system_recording_thread.start()
        if self._system_record_poll_timer is None:
            self._system_record_poll_timer = QTimer(self)
            self._system_record_poll_timer.setInterval(150)
            self._system_record_poll_timer.timeout.connect(self._poll_system_recording)
        self._system_record_poll_timer.start()
        self.voice_system_record_button.setText("■ Arrêter la sortie")
        self.statusBar().showMessage("Capture de la sortie audio en cours…", 5000)

    def _poll_system_recording(self) -> None:
        thread = self._system_recording_thread
        if thread is None or thread.is_alive():
            return
        if self._system_record_poll_timer is not None:
            self._system_record_poll_timer.stop()
        path = self._system_recording_path
        error = getattr(self, "_system_recording_error", None)
        self._system_recording_thread = None
        self._system_recorder = None
        self._system_recording_path = None
        self.voice_system_record_button.setText(self._SYSTEM_BUTTON_LABEL)
        if error:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            self.voice_system_record_button.setToolTip(
                "Capture indisponible : vérifiez sounddevice, WASAPI et la sortie Windows sélectionnée"
            )
            self.statusBar().showMessage(f"Capture de sortie impossible : {error}", 9000)
            QMessageBox.warning(self, "Capture de sortie impossible", str(error))
        elif path is not None:
            self.voice_system_record_button.setToolTip(
                "Capturer la sortie Windows sélectionnée, par exemple une voix de Discord via WASAPI loopback"
            )
            self._register_recorded_sample(path, "Sortie audio")
            self.statusBar().showMessage("Sortie audio enregistrée dans la banque de voix", 5000)

    def _voice_engine_changed(self, _index: int) -> None:
        engine_key = str(self.voice_engine.currentData() or "pocket-tts")
        self.voice_model.setText(get_profile(engine_key).repository)

        is_pocket = engine_key == "pocket-tts"
        is_f5 = engine_key == "f5-tts"

        if hasattr(self, "voice_emotion_toolbar"):
            self.voice_emotion_toolbar.setVisible(is_f5)

        self.voice_reference_text.setEnabled(not is_pocket and not is_f5)
        if is_pocket:
            self.voice_reference_text.setPlaceholderText(
                "Inutile avec Pocket TTS : le clonage part directement de l’audio"
            )
        elif is_f5:
            self.voice_reference_text.setPlaceholderText(
                "Inutile avec F5-TTS : les émotions sont pilotées par le texte"
            )
        else:
            self.voice_reference_text.setPlaceholderText(
                "Facultatif : transcription exacte de l’échantillon"
            )

        for checkbox in (self.voice_high_quality, self.voice_quantize):
            checkbox.setVisible(is_pocket)
            checkbox.setEnabled(is_pocket)

        self.voice_language.setEnabled(not is_f5)
        self._sync_pocket_quality_control()

    def _setup_recording(self) -> None:
        if QMediaCaptureSession is None or QMediaRecorder is None or QAudioInput is None:
            return
        self._capture_session = QMediaCaptureSession(self)
        self._audio_input = QAudioInput(self)
        self._recorder = QMediaRecorder(self)
        self._capture_session.setAudioInput(self._audio_input)
        self._capture_session.setRecorder(self._recorder)
        # Some Windows multimedia backends expose enum-typed signals that PyQt6
        # cannot bind reliably to Python callables. Polling keeps recording UI
        # portable while retaining the same state/error handling.
        self._recording_poll_timer = QTimer(self)
        self._recording_poll_timer.setInterval(120)
        self._recording_poll_timer.timeout.connect(self._poll_recording_state)

    def _toggle_recording(self) -> None:
        if self._recorder is None:
            self.statusBar().showMessage("Enregistrement microphone indisponible", 5000)
            return
        if self._recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            self._recorder.stop()
            return
        if QMediaFormat is None:
            self.statusBar().showMessage("Format audio indisponible", 5000)
            return
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
        if not media_format.isSupported(QMediaFormat.ConversionMode.Encode):
            QMessageBox.warning(
                self,
                "Enregistrement indisponible",
                "Le backend audio de Windows ne prend pas en charge l’enregistrement WAV.",
            )
            return
        self.paths.voice_samples.mkdir(parents=True, exist_ok=True)
        self._recording_path = self.paths.voice_samples / f"sample-{datetime.now(UTC):%Y%m%d-%H%M%S%f}.wav"
        self._recorder.setMediaFormat(media_format)
        self._recorder.setOutputLocation(QUrl.fromLocalFile(str(self._recording_path)))
        self._recorder.record()
        if self._recording_poll_timer is not None:
            self._recording_poll_timer.start()
        self.voice_record_button.setText("■ Arrêter")
        self.voice_record_button.setToolTip("Arrêter l’enregistrement")
        self.statusBar().showMessage("Enregistrement en cours — gardez 3 à 10 secondes…")

    def _poll_recording_state(self) -> None:
        if self._recorder is None:
            return
        if self._recorder.recorderState() != QMediaRecorder.RecorderState.StoppedState:
            return
        recorder_error = self._recorder.error()
        if recorder_error != QMediaRecorder.Error.NoError:
            message = self._recorder.errorString() or "Erreur multimedia"
            self._recording_error(recorder_error, message)
            return
        self._recording_state_changed(QMediaRecorder.RecorderState.StoppedState)

    def _recording_state_changed(self, state) -> None:
        if state != QMediaRecorder.RecorderState.StoppedState:
            return
        path = self._recording_path
        recording_poll_timer = self.__dict__.get("_recording_poll_timer")
        if recording_poll_timer is not None:
            recording_poll_timer.stop()
        self.voice_record_button.setText(self._MIC_BUTTON_LABEL)
        self.voice_record_button.setToolTip(self._MIC_BUTTON_HINT)
        self._recording_path = None
        if path is not None and path.is_file() and path.stat().st_size > 0:
            self._register_recorded_sample(path, "Voix microphone")
            self.statusBar().showMessage("Échantillon microphone ajouté à la banque de voix", 5000)

    def _recording_error(self, _error, message: str) -> None:
        recording_poll_timer = self.__dict__.get("_recording_poll_timer")
        if recording_poll_timer is not None:
            recording_poll_timer.stop()
        self._recording_path = None
        self.voice_record_button.setText(MainWindow._MIC_BUTTON_LABEL)
        self.voice_record_button.setToolTip(MainWindow._MIC_BUTTON_HINT)
        self.statusBar().showMessage(f"Enregistrement impossible : {message}", 7000)

    def _generate_voice(self) -> None:
        """Generate the full text with the current voice."""

        self._start_voice_generation()

    def _start_voice_generation(self) -> None:
        sample = Path(self.voice_sample.text().strip())
        ref_text = self.voice_reference_text.text().strip()
        if not sample.is_file():
            QMessageBox.warning(
                self,
                "Échantillon manquant",
                "Ajoutez d’abord un échantillon à l’étape 2 : enregistrez au micro, "
                "capturez la sortie audio ou importez un fichier.",
            )
            return
        text = self.voice_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(
                self,
                "Texte manquant",
                "Écrivez à l’étape 3 ce que la voix doit dire.",
            )
            self.voice_text.setFocus()
            return
        if self._voice_thread is not None:
            return
        stamp = f"{datetime.now(UTC):%Y%m%d-%H%M%S}"
        output = self.paths.audio_cache / "generated-voices" / f"voice-{stamp}.wav"
        requested_engine = str(self.voice_engine.currentData() or "pocket-tts")
        if not is_engine_runtime_installed(requested_engine):
            # Never fall back to an engine whose runtime is missing too: that is
            # how the packaged app ended up asking for the OmniVoice model while
            # the user had Pocket TTS selected. Only switch to an engine that can
            # actually run, in the same priority order as the combo box.
            fallback_engine = next(
                (
                    candidate
                    for candidate in (
                        "pocket-tts",
                        "qwen3-tts",
                        "qwen3-tts-0.6b",
                        "omnivoice",
                        "f5-tts",
                    )
                    if candidate != requested_engine
                    and is_engine_runtime_installed(candidate)
                ),
                "",
            )
            if not fallback_engine:
                QMessageBox.warning(
                    self,
                    "Moteur vocal indisponible",
                    f"Le moteur « {requested_engine} » n’est pas installé dans cette "
                    "application. Réinstallez-la avec l’extra correspondant "
                    "(Pocket TTS, Qwen3-TTS, OmniVoice ou F5-TTS) puis réessayez.",
                )
                return
            self.statusBar().showMessage(
                f"Runtime {requested_engine} indisponible — bascule automatique sur {fallback_engine}.",
                7000,
            )
            idx = self.voice_engine.findData(fallback_engine)
            if idx >= 0:
                self.voice_engine.setCurrentIndex(idx)
            requested_engine = fallback_engine

        self._voice_thread = QThread(self)
        if requested_engine == "f5-tts":
            text = self._f5_generation_text()
        self._active_voice_engine = requested_engine
        settings = self._voice_settings()
        self._voice_worker = VoiceWorker(
            self._voice_service,
            text,
            sample,
            ref_text,
            output,
            self._voice_language(),
            self._active_voice_engine,
            self.voice_model.text(),
            settings,
        )
        self._voice_worker.moveToThread(self._voice_thread)
        self._voice_thread.started.connect(self._voice_worker.run)
        self._voice_worker.finished.connect(self._voice_finished)
        self._voice_worker.failed.connect(self._voice_failed)
        self._voice_worker.finished.connect(
            self._voice_thread.quit, Qt.ConnectionType.DirectConnection
        )
        self._voice_worker.failed.connect(
            self._voice_thread.quit, Qt.ConnectionType.DirectConnection
        )
        self._voice_thread.finished.connect(self._voice_worker.deleteLater)
        self._voice_thread.finished.connect(self._voice_thread.deleteLater)
        self._voice_thread.finished.connect(self._voice_thread_done)
        self.voice_generate_button.setEnabled(False)
        self.voice_advanced_button.setEnabled(False)
        self.voice_generate_button.setText("Génération en cours…")
        self._voice_generation_ok = False
        self._voice_ui_generation += 1
        self.voice_progress.setRange(0, 0)
        self.voice_progress.setVisible(True)
        self.voice_status.setText("Le moteur prépare la voix…")
        self._voice_wait_messages = (
            "Le moteur prépare la voix…",
            "Analyse de l’échantillon local…",
            "Génération en cours — vous pouvez patienter ici…",
        )
        self._voice_wait_index = 0
        self._voice_wait_timer = QTimer(self)
        self._voice_wait_timer.timeout.connect(self._voice_wait_tick)
        self._voice_wait_timer.start(1100)
        self._voice_thread.start()

    def _voice_wait_tick(self) -> None:
        if not self._voice_thread or not self._voice_thread.isRunning():
            return
        self._voice_wait_index = (self._voice_wait_index + 1) % len(self._voice_wait_messages)
        self.voice_status.setText(self._voice_wait_messages[self._voice_wait_index])

    def _set_last_generation(self, path: Path | None, title: str = "") -> None:
        """Load a generated file into the result player and its actions."""

        usable = path is not None and path.is_file()
        self._last_generation_path = path if usable else None
        self._last_generation_title = title if usable else ""
        self.voice_result_player.set_source(path if usable else None, title or None)
        self.voice_result_favorite_button.setEnabled(usable)
        self.voice_result_folder_button.setEnabled(usable)

    def _favorite_last_generation(self) -> None:
        if self._last_generation_path is None:
            return
        self._add_sound_to_favorites(
            self._last_generation_path,
            self._last_generation_title or self._last_generation_path.stem,
            self._active_voice_engine,
        )

    def _open_last_generation_folder(self) -> None:
        if self._last_generation_path is None:
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._last_generation_path.parent))
        )

    def _voice_finished(
        self,
        output: str,
        engine_key: str,
        model_name: str,
        text: str,
        sample: str,
        duration_seconds: float = 0.0,
    ) -> None:
        path = Path(output)
        generation = self.library.add_voice_generation(
            path.stem,
            text,
            Path(sample),
            path,
            engine_key,
            duration_seconds=duration_seconds,
        )
        if self.voice_favorite.isChecked():
            self._add_sound_to_favorites(path, generation.title, engine_key)
        self._set_last_generation(path, generation.title)
        self._voice_generation_ok = True
        self._refresh_voice_history()
        self._refresh_voice_model_settings()

    def _voice_failed(self, message: str) -> None:
        self._voice_generation_ok = False
        self.voice_progress.setRange(0, 100)
        self.voice_progress.setValue(0)
        # Multi-line guidance belongs in the dialog; the inline status stays short.
        summary = message.strip().splitlines()[0] if message.strip() else "erreur inconnue"
        self.voice_status.setText(f"Échec — {summary}")
        QMessageBox.warning(self, "Génération impossible", message)

    def _voice_thread_done(self) -> None:
        if hasattr(self, "_voice_wait_timer"):
            self._voice_wait_timer.stop()
            self._voice_wait_timer.deleteLater()
        self._voice_thread = None
        self._voice_worker = None
        self.voice_generate_button.setEnabled(True)
        self.voice_advanced_button.setEnabled(True)
        self.voice_generate_button.setText("Générer")
        if self._voice_generation_ok:
            self.voice_progress.setRange(0, 100)
            self.voice_progress.setValue(100)
            self.voice_status.setText(
                "Génération terminée — cliquez sur ▶ dans « Résultat » pour l’écouter."
            )
        if self._voice_generation_ok:
            QTimer.singleShot(
                2200,
                lambda generation=self._voice_ui_generation: self._hide_voice_progress(generation),
            )

    def _hide_voice_progress(self, generation: int) -> None:
        if generation == self._voice_ui_generation and self._voice_thread is None:
            self.voice_progress.setVisible(False)

    def _clear_myinstants_grid(self) -> None:
        if self._active_remote_preview_url is not None:
            player = self._players.get(False)
            if player is not None:
                player.stop()
            self._set_active_remote_preview(None)
            self._remote_preview_title = None
        while self.myinstants_grid.count():
            item = self.myinstants_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._myinstant_cards.clear()
        self._clear_myinstants_selection()

    def _selected_myinstant_changed(self, result: MyInstantResult, selected: bool) -> None:
        if selected:
            self._selected_myinstants[result.audio_url] = result
        else:
            self._selected_myinstants.pop(result.audio_url, None)
        count = len(self._selected_myinstants)
        label = "son sélectionné" if count == 1 else "sons sélectionnés"
        self.myinstants_selection_status.setText(f"{count} {label}")
        self.favorite_selected_myinstants.setEnabled(count > 0)

    def _select_all_myinstants(self) -> None:
        for card in self._myinstant_cards.values():
            card.set_selected(True)

    def _clear_myinstants_selection(self) -> None:
        self._selected_myinstants.clear()
        for card in self._myinstant_cards.values():
            card.set_selected(False)
        if hasattr(self, "myinstants_selection_status"):
            self.myinstants_selection_status.setText("0 son sélectionné")
        if hasattr(self, "favorite_selected_myinstants"):
            self.favorite_selected_myinstants.setEnabled(False)

    def _favorite_selected_myinstants(self) -> None:
        if self._bulk_active:
            self.myinstants_status.setText("Un téléchargement groupé est déjà en cours.")
            return
        if not self._selected_myinstants:
            return
        selected = list(self._selected_myinstants.values())
        active_selected = [result for result in selected if result.audio_url in self._active_downloads]
        if active_selected:
            self.myinstants_status.setText(
                f"« {active_selected[0].title} » est encore en téléchargement. Réessayez après sa fin."
            )
            return
        # A completed preview remains in the UI briefly so its row can show the
        # result. Remove that transient job before starting the persistent favorite
        # transfer; active previews/favorites remain protected from duplicate work.
        for result in selected:
            job = self._download_jobs.get(result.audio_url)
            if job is not None and not job[4] and result.audio_url not in self._active_downloads:
                self._remove_download_job(result.audio_url)
        launchable = [result for result in selected if result.audio_url not in self._download_jobs]
        candidates = launchable
        if not candidates:
            self._clear_myinstants_selection()
            self.myinstants_status.setText("Les sons sélectionnés sont déjà en téléchargement.")
            return
        existing = len(self.library.sounds(favorites_only=True))
        reserved = sum(
            1
            for key, job in self._download_jobs.items()
            if key in self._active_downloads and job[4]
        )
        available = self.config.favorite_limit - existing - reserved
        if len(candidates) > available:
            QMessageBox.warning(
                self,
                "Limite de favoris",
                f"Il reste {max(0, available)} emplacement(s), mais {len(candidates)} son(s) sont sélectionnés.",
            )
            return
        self._bulk_completed = 0
        self._bulk_failed = 0
        self._bulk_active = True
        self._bulk_job_ids = {result.audio_url for result in candidates}
        self._bulk_total = len(candidates)
        self._set_myinstants_cards_enabled(False)
        self.bulk_download_progress.setValue(0)
        self.bulk_download_progress.setVisible(True)
        self.favorite_selected_myinstants.setEnabled(False)
        for result in launchable:
            if not self._download_myinstant(result, True):
                self._bulk_job_ids.discard(result.audio_url)
                self._bulk_total -= 1
        if not self._bulk_total:
            self._bulk_active = False
            self._set_myinstants_cards_enabled(True)
            self.bulk_download_progress.setVisible(False)
            self.myinstants_status.setText("Aucun nouveau téléchargement à lancer.")
        else:
            self.myinstants_status.setText(
                f"Téléchargement groupé lancé : 0/{self._bulk_total} terminé(s)."
            )
        self._clear_myinstants_selection()

    def _set_myinstants_cards_enabled(self, enabled: bool) -> None:
        for card in self._myinstant_cards.values():
            card.set_download_actions_enabled(enabled)
            card.set_selection_enabled(enabled)
        self.select_all_myinstants.setEnabled(enabled)
        self.clear_myinstants_selection.setEnabled(enabled)

    def _bulk_download_finished(self, job_id: str, success: bool = True) -> None:
        if job_id not in self._bulk_job_ids:
            return
        self._bulk_completed += 1
        if not success:
            self._bulk_failed += 1
        self.bulk_download_progress.setValue(
            int(self._bulk_completed * 100 / max(1, self._bulk_total))
        )
        self.myinstants_status.setText(
            f"Téléchargement groupé : {self._bulk_completed}/{self._bulk_total} terminé(s)."
        )
        if self._bulk_completed >= self._bulk_total:
            self._bulk_active = False
            self._bulk_job_ids.clear()
            self._set_myinstants_cards_enabled(True)
            self.bulk_download_progress.setVisible(False)
            if self._bulk_failed:
                self.myinstants_status.setText(
                    f"Téléchargement groupé terminé : {self._bulk_failed} échec(s)."
                )
            else:
                self.myinstants_status.setText(
                    "Téléchargement groupé terminé — sons disponibles hors ligne."
                )

    def _search_myinstants(self) -> None:
        query = self.myinstants_search.text().strip()
        if self._network_thread is not None:
            return
        self.myinstants_search_button.setEnabled(False)
        self.search_progress.setVisible(True)
        self.myinstants_status.setText("Recherche en cours dans Myinstants…")
        thread = QThread(self)
        worker = SearchWorker(query)
        self._network_thread, self._network_worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._search_finished)
        worker.failed.connect(self._network_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._network_done)
        thread.start()

    def _search_finished(self, results: object) -> None:
        self._myinstants_catalog_loaded = True
        self._myinstants_results = list(results)
        self._clear_myinstants_grid()
        if not self._myinstants_results:
            self.myinstants_status.setText("Aucun résultat trouvé.")
            return
        self.myinstants_status.setText(f"{len(self._myinstants_results)} résultat(s) — utilisez Tester ou Ajouter aux favoris.")
        for index, result in enumerate(self._myinstants_results):
            card = MyInstantCard(result)
            card.selection_changed.connect(self._selected_myinstant_changed)
            card.preview_hovered.connect(self._warm_remote_preview)
            card.preview_requested.connect(lambda selected: self._download_myinstant(selected, False))
            card.favorite_requested.connect(lambda selected: self._download_myinstant(selected, True))
            self._myinstant_cards[result.audio_url] = card
        self._reflow_grid(
            self.myinstants_grid,
            list(self._myinstant_cards.values()),
            self._grid_columns(self.myinstants_container.width()),
        )
        self._set_myinstants_cards_enabled(not self._bulk_active)
        self.favorite_selected_myinstants.setEnabled(False)

    def _download_myinstant(self, result: MyInstantResult, favorite: bool) -> bool:
        if not favorite:
            self._play_remote(result.audio_url, title=result.title)
            self.myinstants_status.setText(f"Aperçu en direct de « {result.title} »")
            return True
        reserved_favorites = sum(
            1 for key, job in self._download_jobs.items() if key in self._active_downloads and job[4]
        )
        if favorite and (
            len(self.library.sounds(favorites_only=True)) + reserved_favorites
            >= self.config.favorite_limit
        ):
            QMessageBox.warning(
                self,
                "Limite atteinte",
                f"Limite de {self.config.favorite_limit} favoris atteinte.",
            )
            return False
        job_id = result.audio_url
        if job_id in self._download_jobs:
            self.myinstants_status.setText(f"« {result.title} » est déjà en téléchargement.")
            return False

        cache_dir = self.paths.audio_cache
        row = DownloadProgressRow(result.title)
        self.download_rows.addWidget(row)
        self.download_group.setVisible(True)
        self._update_download_summary()
        thread = QThread(self)
        worker = DownloadWorker(result, cache_dir)
        self._download_jobs[job_id] = (thread, worker, row, result, favorite)
        self._active_downloads.add(job_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(row.set_progress)
        worker.finished.connect(lambda path, key=job_id: self._download_job_finished(key, path))
        worker.failed.connect(lambda message, key=job_id: self._download_job_failed(key, message))
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        self.myinstants_status.setText(
            f"Téléchargement de « {result.title} » lancé — vous pouvez en lancer d’autres."
        )
        return True

    def _download_job_finished(self, job_id: str, path_text: str) -> None:
        job = self._download_jobs.get(job_id)
        if job is None:
            return
        _thread, _worker, row, result, favorite = job
        path = Path(path_text)
        row.set_finished()
        self._active_downloads.discard(job_id)
        if favorite:
            is_bulk = job_id in self._bulk_job_ids
            self._add_sound_to_favorites(path, result.title, "Myinstants")
            self._bulk_download_finished(job_id)
            if not is_bulk:
                self.myinstants_status.setText(f"« {result.title} » est disponible hors ligne.")
        else:
            self.myinstants_status.setText(f"Aperçu en direct de « {result.title} »")
        self._update_download_summary()
        QTimer.singleShot(2200, lambda key=job_id: self._remove_download_job(key))

    def _download_job_failed(self, job_id: str, message: str) -> None:
        job = self._download_jobs.get(job_id)
        if job is None:
            return
        _thread, _worker, row, result, _favorite = job
        row.set_failed()
        self._active_downloads.discard(job_id)
        is_bulk = job_id in self._bulk_job_ids
        if is_bulk:
            self._bulk_download_finished(job_id, False)
        if not is_bulk:
            self.myinstants_status.setText(f"Téléchargement impossible pour « {result.title} ».")
        QMessageBox.warning(self, "Myinstants", message)
        self._update_download_summary()
        QTimer.singleShot(3200, lambda key=job_id: self._remove_download_job(key))

    def _remove_download_job(self, job_id: str) -> None:
        job = self._download_jobs.pop(job_id, None)
        if job is None:
            return
        _thread, _worker, row, _result, _favorite = job
        row.deleteLater()
        self._update_download_summary()

    def _update_download_summary(self) -> None:
        active = len(self._active_downloads)
        self.download_group.setVisible(active > 0)
        self.download_summary.setText(
            f"{active} téléchargement(s) actif(s) — chaque son est mis en cache localement."
            if active
            else "Aucun téléchargement actif"
        )

    def _network_failed(self, message: str) -> None:
        self._myinstants_catalog_loaded = False
        self.myinstants_status.setText("Catalogue Myinstants indisponible — réessayez")
        QMessageBox.warning(self, "Myinstants", message)

    def _network_done(self) -> None:
        self._network_thread = None
        self._network_worker = None
        if hasattr(self, "myinstants_search_button"):
            self.myinstants_search_button.setEnabled(True)
            self.search_progress.setVisible(False)

    def _refresh_keybinds(self) -> None:
        sounds = self.library.sounds("", True)
        self.keybind_table.setRowCount(len(sounds))
        bindings = self.library.keybinds()
        self._keybind_capture_buttons: dict[int, ShortcutCaptureButton] = {}
        for row, sound in enumerate(sounds):
            self.keybind_table.setItem(row, 0, QTableWidgetItem(sound.title))
            self.keybind_table.setItem(row, 1, QTableWidgetItem(sound.source))
            capture = ShortcutCaptureButton(bindings.get(sound.id, ""), self.keybind_table)
            capture.shortcut_recorded.connect(
                lambda sequence, sound_id=sound.id, button=capture: self._assign_keybind(
                    sound_id, sequence, button
                )
            )
            self._keybind_capture_buttons[sound.id] = capture
            self.keybind_table.setCellWidget(row, 2, capture)
            clear = QPushButton("Effacer")
            clear.setObjectName("tableGhostButton")
            clear.setToolTip("Effacer le raccourci clavier assigné à ce favori")
            clear.clicked.connect(
                lambda _checked=False, sound_id=sound.id: self._clear_keybind(sound_id)
            )
            self.keybind_table.setCellWidget(row, 3, clear)

    @staticmethod
    def _binding_key(sequence: str) -> str:
        return "+".join(part.strip().casefold() for part in sequence.split("+") if part.strip())

    def _assign_keybind(
        self, sound_id: int, sequence: str, button: ShortcutCaptureButton
    ) -> None:
        candidate = self._binding_key(sequence)
        bindings = self.library.keybinds()
        conflict = next(
            (
                other_id
                for other_id, other_sequence in bindings.items()
                if other_id != sound_id and self._binding_key(other_sequence) == candidate
            ),
            None,
        )
        if conflict is not None:
            button.sequence = bindings.get(sound_id, "")
            button._update_text()
            self.statusBar().showMessage(
                "Cette combinaison est déjà utilisée par un autre favori.", 5000
            )
            return
        self.library.set_keybind(sound_id, sequence)
        if self._hotkeys.active:
            self._restart_hotkeys()
        self.statusBar().showMessage(f"Raccourci {sequence} enregistré", 4000)

    def _clear_keybind(self, sound_id: int) -> None:
        self.library.clear_keybind(sound_id)
        button = getattr(self, "_keybind_capture_buttons", {}).get(sound_id)
        if button is not None:
            button.sequence = ""
            button._update_text()
        if self._hotkeys.active:
            self._restart_hotkeys()
        self.statusBar().showMessage("Raccourci effacé", 3000)

    def _restart_hotkeys(self) -> None:
        """Re-register the active global hooks after a shortcut change."""

        self._hotkeys.stop()
        bindings = self.library.keybinds()
        if not bindings:
            self.hotkey_toggle.setText("Activer les raccourcis")
            self.statusBar().showMessage("Tous les raccourcis ont été effacés", 3000)
            return
        sounds = {item.id: item for item in self.library.sounds("", True)}
        try:
            self._hotkeys.start(bindings, self.hotkey_play_requested.emit, sounds)
            self._prepare_hotkey_players()
            self.hotkey_toggle.setText("Désactiver les raccourcis")
        except RuntimeError as error:
            self.hotkey_toggle.setText("Activer les raccourcis")
            QMessageBox.warning(self, "Raccourcis indisponibles", str(error))

    def _toggle_hotkeys(self) -> None:
        try:
            if self._hotkeys.active:
                self._hotkeys.stop()
                self._release_hotkey_players()
                self.hotkey_toggle.setText("Activer les raccourcis")
                return
            sounds = {item.id: item for item in self.library.sounds("", True)}
            self._hotkeys.start(self.library.keybinds(), self.hotkey_play_requested.emit, sounds)
            self._prepare_hotkey_players()
            self.hotkey_toggle.setText("Désactiver les raccourcis")
        except RuntimeError as error:
            QMessageBox.warning(self, "Raccourcis indisponibles", str(error))

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:
        if not getattr(self, "_allow_close", False) and self.tray_preference.isChecked() and self.tray.isVisible():
            self.hide()
            self.tray.showMessage("SoundMaster", "L’application continue dans la zone de notification.")
            event.ignore()
            return
        self._hotkeys.stop()
        self._release_hotkey_players()
        self._release_favorite_players()
        self._stop_voice_players()
        if hasattr(self, "_fast_audio"):
            self._fast_audio.close()
        if hasattr(self, "update_panel"):
            self.update_panel.stop()
        if self._system_recorder is not None:
            self._system_recorder.stop()
        if self._system_recording_thread is not None and self._system_recording_thread.is_alive():
            self._system_recording_thread.join(timeout=5)
        if self._recorder is not None and self._recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            self._recorder.stop()
        if self._voice_thread is not None and self._voice_thread.isRunning():
            # QThread.quit() cannot interrupt blocking model inference. Wait for the
            # worker to return before closing SQLite and destroying its QObject tree.
            self._voice_thread.quit()
            self._voice_thread.wait()
        if self._network_thread is not None and self._network_thread.isRunning():
            self._network_thread.quit()
            self._network_thread.wait(25000)
        for job_id in list(self._active_downloads):
            job = self._download_jobs.get(job_id)
            if job is None:
                continue
            thread, _worker, _row, _result, _favorite = job
            if thread.isRunning():
                thread.quit()
                thread.wait(25000)
        self.library.set_preference("minimize_to_tray", str(self.tray_preference.isChecked()).lower())
        self.library.close()
        event.accept()
