"""Main SoundMaster desktop shell and embedded local-first feature UI."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
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
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from soundmaster.core.config import AppConfig, AppPaths
from soundmaster.core.legal import LegalProfile
from soundmaster.core.models import MODEL_PROFILES, get_profile, is_downloaded
from soundmaster.core.myinstants import (
    MyInstantResult,
    MyInstantsError,
    cache_audio,
    search_myinstants,
)
from soundmaster.core.tts import QwenVoiceService, VoiceGenerationError
from soundmaster.data.library import SoundItem, SoundLibrary
from soundmaster.hotkeys import HotkeyManager
from soundmaster.ui.legal_settings import LegalSettingsWidget
from soundmaster.ui.myinstants_widgets import MyInstantCard
from soundmaster.ui.theme import APP_STYLE, animate_opacity

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


def _module_available(module_name: str) -> bool:
    """Check an optional module without allowing broken import metadata to escape."""

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def collect_gpu_diagnostics(paths: AppPaths) -> str:
    """Return actionable local TTS/GPU diagnostics without importing torch at startup."""

    qwen_runtime = _module_available("qwen_tts")
    soundfile_runtime = _module_available("soundfile")
    model_ready = is_downloaded(get_profile("qwen3-tts"), paths)
    runtime_state = (
        "installé" if qwen_runtime and soundfile_runtime else "incomplet"
    )
    lines = [
        f"Runtime Qwen3-TTS : {runtime_state}",
        f"Modèle local : {'prêt' if model_ready else 'absent'}",
    ]
    try:
        import torch
    except ImportError:
        lines.append("PyTorch : absent — lancez setup_gpu.bat pour NVIDIA ou installez l’extra CPU.")
        return "\n".join(lines)

    lines.append(f"PyTorch : {torch.__version__}")
    if not torch.cuda.is_available():
        lines.append("Accélération : CPU — CUDA indisponible, génération plus lente.")
        lines.append("Action : installez les pilotes NVIDIA puis lancez setup_gpu.bat.")
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


class SoundCard(QWidget):
    """Local sound card with separate headset and virtual-output actions."""

    play_requested = pyqtSignal(int, bool)
    favorite_changed = pyqtSignal(int, bool)

    def __init__(self, item: SoundItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        layout = QVBoxLayout(self)
        title = QLabel(f"<b>{item.title}</b>")
        title.setWordWrap(True)
        layout.addWidget(title)
        metadata = QLabel(f"{item.source} · {Path(item.path).name}")
        metadata.setObjectName("muted")
        metadata.setWordWrap(True)
        layout.addWidget(metadata)
        actions = QHBoxLayout()
        preview = QPushButton("Tester")
        preview.clicked.connect(lambda: self.play_requested.emit(item.id, False))
        send = QPushButton("Envoyer")
        send.setToolTip("Lire vers la sortie 2 sélectionnée")
        send.clicked.connect(lambda: self.play_requested.emit(item.id, True))
        star = QPushButton("★" if item.favorite else "☆")
        star.setCheckable(True)
        star.setChecked(item.favorite)
        star.clicked.connect(lambda checked: self.favorite_changed.emit(item.id, checked))
        actions.addWidget(preview)
        actions.addWidget(send)
        actions.addWidget(star)
        layout.addLayout(actions)
        self.setObjectName("soundCard")

    def enterEvent(self, event) -> None:
        animate_opacity(self, 0.88, 1.0, 180)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        animate_opacity(self, 1.0, 0.94, 220)
        super().leaveEvent(event)


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


class VoiceWorker(QObject):
    finished = pyqtSignal(str, str, str, str, str)
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

    def run(self) -> None:
        try:
            result = self.service.generate_clone(
                self.text,
                self.sample,
                self.ref_text,
                self.output,
                self.language,
                self.engine_key,
            )
        except VoiceGenerationError as error:
            self.failed.emit(str(error))
        except Exception as error:  # noqa: BLE001 - optional third-party boundary.
            self.failed.emit(f"Erreur inattendue du moteur vocal : {error}")
        else:
            self.finished.emit(
                str(result),
                self.engine_key,
                self.model_name,
                self.text,
                str(self.sample),
            )


class MainWindow(QMainWindow):
    """Full French application shell with embedded local workflows."""

    hotkey_play_requested = pyqtSignal(int)

    def __init__(self, legal_profile: LegalProfile, legal_profile_path: Path, paths: AppPaths, config: AppConfig) -> None:
        super().__init__()
        self.paths, self.config = paths, config
        self.library = SoundLibrary(paths.database)
        self.legal_profile, self.legal_profile_path = legal_profile, legal_profile_path
        self._players: dict[bool, object] = {}
        self._audio_outputs: dict[bool, object] = {}
        self._network_thread: QThread | None = None
        self._network_worker: QObject | None = None
        self._voice_thread: QThread | None = None
        self._voice_worker: VoiceWorker | None = None
        self._voice_service = QwenVoiceService(paths)
        self._active_voice_engine = "qwen3-tts"
        self._capture_session = None
        self._audio_input = None
        self._recorder = None
        self._recording_path: Path | None = None
        self._recording_poll_timer: QTimer | None = None
        self._download_jobs: dict[
            str, tuple[QThread, DownloadWorker, DownloadProgressRow, MyInstantResult, bool]
        ] = {}
        self._active_downloads: set[str] = set()
        self._myinstants_results: list[MyInstantResult] = []
        self._myinstant_cards: dict[str, MyInstantCard] = {}
        self._selected_myinstants: dict[str, MyInstantResult] = {}
        self._bulk_job_ids: set[str] = set()
        self._bulk_total = 0
        self._bulk_completed = 0
        self._bulk_failed = 0
        self._bulk_active = False
        self._voice_generation_ok = False
        self._voice_ui_generation = 0
        self._hotkeys = HotkeyManager()
        self.hotkey_play_requested.connect(lambda sound_id: self._play_sound(sound_id, True))
        if QMediaPlayer is not None and QAudioOutput is not None:
            for virtual in (False, True):
                output = QAudioOutput(self)
                output.setVolume(1.0)
                player = QMediaPlayer(self)
                player.setAudioOutput(output)
                self._audio_outputs[virtual] = output
                self._players[virtual] = player
        self.setWindowTitle("SoundMaster — Soundboard local")
        self.setStyleSheet(APP_STYLE)
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self._build_shell()
        self._setup_recording()
        self._build_tray()
        self._refresh_dashboard()
        self._refresh_voice_history()

    def _build_shell(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
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
        settings = QPushButton("⚙  Paramètres")
        settings.setObjectName("settingsButton")
        settings.clicked.connect(self._select_settings)
        side_layout.addWidget(settings)
        root_layout.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
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
        add.clicked.connect(self._add_local_file)
        toolbar.addWidget(add)
        layout.addLayout(toolbar)
        self.dashboard_hint = QLabel()
        self.dashboard_hint.setObjectName("muted")
        layout.addWidget(self.dashboard_hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.card_container = QWidget()
        self.card_grid = QGridLayout(self.card_container)
        self.card_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll, 1)
        layout.addWidget(QLabel("Récemment utilisés"))
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(110)
        layout.addWidget(self.recent_list)
        return page

    def _voice_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "<h3>Génération vocale locale</h3>"
            "<p>Choisissez un échantillon autorisé et écrivez votre texte. "
            "SoundMaster prépare automatiquement la voix en local.</p>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.voice_text = QTextEdit()
        self.voice_text.setPlaceholderText("Texte à générer…")
        self.voice_text.setMinimumHeight(100)
        form.addRow("Texte", self.voice_text)
        sample_row = QHBoxLayout()
        self.voice_sample = QLineEdit()
        self.voice_sample.setPlaceholderText("Échantillon vocal WAV/MP3")
        browse = QPushButton("Parcourir")
        browse.clicked.connect(self._choose_voice_sample)
        self.voice_record_button = QPushButton("● Enregistrer")
        self.voice_record_button.setToolTip("Enregistrer un échantillon de 3 à 10 secondes avec le microphone")
        self.voice_record_button.clicked.connect(self._toggle_recording)
        if QMediaRecorder is None or QMediaCaptureSession is None or QAudioInput is None:
            self.voice_record_button.setEnabled(False)
            self.voice_record_button.setToolTip("Enregistrement QtMultimedia indisponible sur cette installation")
        sample_row.addWidget(self.voice_sample, 1)
        sample_row.addWidget(browse)
        sample_row.addWidget(self.voice_record_button)
        form.addRow("Voix cible", sample_row)
        layout.addLayout(form)

        self.voice_advanced_button = QToolButton()
        self.voice_advanced_button.setText("⚙ Options avancées")
        self.voice_advanced_button.setCheckable(True)
        self.voice_advanced_button.setChecked(False)
        self.voice_advanced_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.voice_advanced_button.setObjectName("advancedButton")
        layout.addWidget(self.voice_advanced_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.voice_advanced = QWidget()
        advanced_form = QFormLayout(self.voice_advanced)
        advanced_form.setContentsMargins(12, 4, 12, 8)
        self.voice_engine = QComboBox()
        self.voice_engine.addItem("Qwen3-TTS — recommandé", "qwen3-tts")
        self.voice_engine.addItem("OmniVoice — multilingue", "omnivoice")
        self.voice_engine.currentIndexChanged.connect(self._voice_engine_changed)
        advanced_form.addRow("Moteur vocal", self.voice_engine)
        self.voice_reference_text = QLineEdit()
        self.voice_reference_text.setPlaceholderText(
            "Facultatif : transcription exacte de l’échantillon"
        )
        advanced_form.addRow("Transcription manuelle", self.voice_reference_text)
        self.voice_model = QLineEdit(MODEL_PROFILES[0].repository)
        self.voice_model.setReadOnly(True)
        advanced_form.addRow("Modèle local", self.voice_model)
        self.voice_language = QComboBox()
        self.voice_language.addItems(("Auto", "French", "English", "German", "Spanish", "Italian"))
        advanced_form.addRow("Langue", self.voice_language)
        self.voice_advanced.setVisible(False)
        self.voice_advanced.setObjectName("voiceAdvanced")
        self.voice_advanced_button.toggled.connect(self.voice_advanced.setVisible)
        layout.addWidget(self.voice_advanced)
        self.voice_favorite = QCheckBox("Ajouter la génération aux favoris")
        self.voice_favorite.setChecked(True)
        layout.addWidget(self.voice_favorite)
        self.voice_generate_button = QPushButton("Générer localement")
        self.voice_generate_button.setObjectName("primaryButton")
        self.voice_generate_button.clicked.connect(self._generate_voice)
        layout.addWidget(self.voice_generate_button)
        self.voice_progress = QProgressBar()
        self.voice_progress.setRange(0, 100)
        self.voice_progress.setValue(0)
        self.voice_progress.setTextVisible(False)
        self.voice_progress.setVisible(False)
        layout.addWidget(self.voice_progress)
        self.voice_status = QLabel("Prêt — l’inférence reste locale")
        self.voice_status.setObjectName("muted")
        layout.addWidget(self.voice_status)
        self.voice_search = QLineEdit()
        self.voice_search.setPlaceholderText("Rechercher dans l’historique vocal…")
        self.voice_search.textChanged.connect(self._refresh_voice_history)
        layout.addWidget(self.voice_search)
        layout.addWidget(QLabel("Historique des générations"))
        self.voice_history = QListWidget()
        layout.addWidget(self.voice_history, 1)
        return page

    def _myinstants_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("<h3>Explorateur Myinstants intégré</h3>"))
        layout.addWidget(QLabel("Recherchez, testez et ajoutez un son aux favoris sans quitter SoundMaster."))
        row = QHBoxLayout()
        self.myinstants_search = QLineEdit()
        self.myinstants_search.setPlaceholderText("airhorn, meme, applause…")
        self.myinstants_search.returnPressed.connect(self._search_myinstants)
        row.addWidget(self.myinstants_search, 1)
        self.myinstants_search_button = QPushButton("Rechercher dans l’app")
        self.myinstants_search_button.setObjectName("primaryButton")
        self.myinstants_search_button.clicked.connect(self._search_myinstants)
        row.addWidget(self.myinstants_search_button)
        layout.addLayout(row)
        rights = QCheckBox("Je confirme avoir les droits nécessaires pour télécharger et utiliser le son sélectionné")
        self.myinstants_rights = rights
        layout.addWidget(rights)
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
        layout.addWidget(QLabel("<h3>Raccourcis globaux</h3><p>Associez une combinaison à un favori pour l’envoyer vers la sortie 2 en jeu.</p>"))
        self.keybind_table = QTableWidget(0, 3)
        self.keybind_table.setHorizontalHeaderLabels(("Son", "Source", "Combinaison"))
        self.keybind_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.keybind_table, 1)
        actions = QHBoxLayout()
        save = QPushButton("Enregistrer les raccourcis")
        save.clicked.connect(self._save_keybinds)
        actions.addWidget(save)
        self.hotkey_toggle = QPushButton("Activer dans Windows")
        self.hotkey_toggle.clicked.connect(self._toggle_hotkeys)
        actions.addWidget(self.hotkey_toggle)
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        audio_group = QGroupBox("Audio et sorties")
        audio_form = QFormLayout(audio_group)
        self.microphone_input = QComboBox()
        self.headset_output = QComboBox()
        self.virtual_output = QComboBox()
        self._populate_audio_devices()
        audio_form.addRow("Microphone / entrée", self.microphone_input)
        audio_form.addRow("Sortie 1 — casque", self.headset_output)
        audio_form.addRow("Sortie 2 — câble virtuel", self.virtual_output)
        apply_audio = QPushButton("Appliquer et enregistrer")
        apply_audio.clicked.connect(self._apply_audio_devices)
        audio_form.addRow(apply_audio)
        hint = QLabel("SoundMaster ne fournit pas de câble virtuel. Installez VB-CABLE ou un équivalent, puis sélectionnez-le ici.")
        hint.setWordWrap(True)
        audio_form.addRow(hint)
        layout.addWidget(audio_group)
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
        self.tray_preference = QCheckBox("Réduire dans la zone de notification à la fermeture")
        self.tray_preference.setChecked(self._preference_bool("minimize_to_tray", self.config.minimize_to_tray))
        self.tray_preference.toggled.connect(lambda value: self.library.set_preference("minimize_to_tray", str(value).lower()))
        layout.addWidget(self.tray_preference)
        legal = LegalSettingsWidget(self.legal_profile, self.legal_profile_path, page)
        legal.saved.connect(lambda: self.statusBar().showMessage("Paramètres enregistrés", 5000))
        layout.addWidget(legal, 1)
        return page

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
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
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

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        titles = ("Tableau de bord", "Clonage de voix", "Explorateur Myinstants", "Raccourcis", "Paramètres")
        self.page_title.setText(titles[index])
        current_page = self.pages.currentWidget()
        if current_page is not None:
            animate_opacity(current_page, 0.55, 1.0, 260)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index == 3:
            self._refresh_keybinds()

    def _select_settings(self) -> None:
        self.pages.setCurrentIndex(4)
        self.page_title.setText("Paramètres")
        current_page = self.pages.currentWidget()
        if current_page is not None:
            animate_opacity(current_page, 0.55, 1.0, 260)
        for button in self.nav_buttons:
            button.setChecked(False)

    def _preference_bool(self, key: str, default: bool) -> bool:
        return self.library.preference(key, str(default).lower()).lower() in {"1", "true", "yes", "on"}

    def _refresh_dashboard(self) -> None:
        while self.card_grid.count():
            item = self.card_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self.dashboard_search.text() if hasattr(self, "dashboard_search") else ""
        sounds = self.library.sounds(query, True)
        self.dashboard_hint.setText(f"{len(sounds)} favori(s) · Tester = casque · Envoyer = sortie 2")
        for index, sound in enumerate(sounds):
            card = SoundCard(sound)
            card.play_requested.connect(self._play_sound)
            card.favorite_changed.connect(self._set_favorite)
            self.card_grid.addWidget(card, index // 3, index % 3)
        self.recent_list.clear()
        for sound in self.library.sounds()[:5]:
            if sound.last_used_at:
                self.recent_list.addItem(sound.title)

    def _refresh_voice_history(self) -> None:
        if not hasattr(self, "voice_history"):
            return
        self.voice_history.clear()
        query = self.voice_search.text() if hasattr(self, "voice_search") else ""
        for generation in self.library.voice_generations(query):
            item = QListWidgetItem(f"{generation.title} · {generation.created_at} · {generation.model}")
            item.setToolTip(f"Texte : {generation.text}\nSortie : {generation.output_path}")
            self.voice_history.addItem(item)

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

    def _apply_audio_devices(self) -> None:
        if QAudioOutput is None or not self._audio_outputs:
            self.statusBar().showMessage("QtMultimedia indisponible", 5000)
            return
        if self.headset_output.currentText() == self.virtual_output.currentText():
            QMessageBox.warning(self, "Sorties identiques", "Sélectionnez deux périphériques distincts.")
            return
        for key, virtual, combo in (("headset_device", False, self.headset_output), ("virtual_device", True, self.virtual_output)):
            device = combo.currentData()
            if device is not None:
                self._audio_outputs[virtual].setDevice(device)
                self.library.set_preference(key, combo.currentText())
        self.library.set_preference("microphone_device", self.microphone_input.currentText())
        self.statusBar().showMessage("Sorties audio enregistrées", 5000)

    def _add_local_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Choisir un audio", "", "Audio (*.wav *.mp3 *.ogg *.flac)")
        if filename:
            self._add_sound_to_favorites(Path(filename), Path(filename).stem, "local")

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
        player = self._players.get(virtual)
        if player is None:
            self.statusBar().showMessage("QtMultimedia indisponible", 5000)
            return
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.play()
        self.statusBar().showMessage("Lecture vers la sortie 2" if virtual else "Lecture locale", 3000)

    def _play_sound(self, sound_id: int, virtual: bool) -> None:
        matches = [item for item in self.library.sounds() if item.id == sound_id]
        if matches:
            self.library.record_use(sound_id)
            self._play_file(Path(matches[0].path), virtual)
            self._refresh_dashboard()

    def _set_favorite(self, sound_id: int, favorite: bool) -> None:
        self.library.set_favorite(sound_id, favorite)
        self._refresh_dashboard()

    def _choose_voice_sample(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un échantillon",
            "",
            "Audio (*.wav *.mp3 *.flac)",
        )
        if filename:
            self.voice_sample.setText(filename)

    def _voice_engine_changed(self, _index: int) -> None:
        engine_key = str(self.voice_engine.currentData() or "qwen3-tts")
        profile = next(profile for profile in MODEL_PROFILES if profile.key == engine_key)
        self.voice_model.setText(profile.repository)

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
        self.voice_record_button.setText("● Enregistrer")
        self.voice_record_button.setToolTip("Enregistrer un échantillon de 3 à 10 secondes avec le microphone")
        self._recording_path = None
        if path is not None and path.is_file() and path.stat().st_size > 0:
            self.voice_sample.setText(str(path))
            self.statusBar().showMessage("Échantillon enregistré et prêt à être utilisé", 5000)

    def _recording_error(self, _error, message: str) -> None:
        recording_poll_timer = self.__dict__.get("_recording_poll_timer")
        if recording_poll_timer is not None:
            recording_poll_timer.stop()
        self._recording_path = None
        self.voice_record_button.setText("● Enregistrer")
        self.voice_record_button.setToolTip(
            "Enregistrer un échantillon de 3 à 10 secondes avec le microphone"
        )
        self.statusBar().showMessage(f"Enregistrement impossible : {message}", 7000)

    def _generate_voice(self) -> None:
        text = self.voice_text.toPlainText().strip()
        sample = Path(self.voice_sample.text().strip())
        ref_text = self.voice_reference_text.text().strip()
        if not text or not sample.is_file():
            QMessageBox.warning(
                self,
                "Informations manquantes",
                "Saisissez un texte et choisissez un fichier audio existant.",
            )
            return
        if self._voice_thread is not None:
            return
        output = self.paths.audio_cache / "generated-voices" / f"voice-{datetime.now(UTC):%Y%m%d-%H%M%S}.wav"
        self._voice_thread = QThread(self)
        self._active_voice_engine = str(self.voice_engine.currentData() or "qwen3-tts")
        self._voice_worker = VoiceWorker(
            self._voice_service,
            text,
            sample,
            ref_text,
            output,
            self.voice_language.currentText(),
            self._active_voice_engine,
            self.voice_model.text(),
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

    def _voice_finished(
        self,
        output: str,
        engine_key: str,
        model_name: str,
        text: str,
        sample: str,
    ) -> None:
        path = Path(output)
        generation = self.library.add_voice_generation(
            path.stem,
            text,
            Path(sample),
            path,
            model_name,
        )
        if self.voice_favorite.isChecked():
            self._add_sound_to_favorites(path, generation.title, engine_key)
        self._voice_generation_ok = True
        self._refresh_voice_history()

    def _voice_failed(self, message: str) -> None:
        self._voice_generation_ok = False
        self.voice_progress.setRange(0, 100)
        self.voice_progress.setValue(0)
        self.voice_status.setText(f"Échec — {message}")
        QMessageBox.warning(self, "Génération impossible", message)

    def _voice_thread_done(self) -> None:
        if hasattr(self, "_voice_wait_timer"):
            self._voice_wait_timer.stop()
            self._voice_wait_timer.deleteLater()
        self._voice_thread = None
        self._voice_worker = None
        self.voice_generate_button.setEnabled(True)
        self.voice_advanced_button.setEnabled(True)
        self.voice_generate_button.setText("Générer localement")
        if self._voice_generation_ok:
            self.voice_progress.setRange(0, 100)
            self.voice_progress.setValue(100)
            self.voice_status.setText("Génération terminée — votre voix est prête")
        if self._voice_generation_ok:
            QTimer.singleShot(
                2200,
                lambda generation=self._voice_ui_generation: self._hide_voice_progress(generation),
            )

    def _hide_voice_progress(self, generation: int) -> None:
        if generation == self._voice_ui_generation and self._voice_thread is None:
            self.voice_progress.setVisible(False)

    def _clear_myinstants_grid(self) -> None:
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
        if not self.myinstants_rights.isChecked():
            QMessageBox.warning(
                self,
                "Droits requis",
                "Cochez la confirmation de droits avant tout téléchargement.",
            )
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
        if not query or self._network_thread is not None:
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
        self._myinstants_results = list(results)
        self._clear_myinstants_grid()
        if not self._myinstants_results:
            self.myinstants_status.setText("Aucun résultat trouvé.")
            return
        self.myinstants_status.setText(f"{len(self._myinstants_results)} résultat(s) — utilisez Tester ou Ajouter aux favoris.")
        for index, result in enumerate(self._myinstants_results):
            card = MyInstantCard(result)
            card.selection_changed.connect(self._selected_myinstant_changed)
            card.preview_requested.connect(lambda selected: self._download_myinstant(selected, False))
            card.favorite_requested.connect(lambda selected: self._download_myinstant(selected, True))
            self._myinstant_cards[result.audio_url] = card
            self.myinstants_grid.addWidget(card, index // 2, index % 2)
        self._set_myinstants_cards_enabled(not self._bulk_active)
        self.favorite_selected_myinstants.setEnabled(False)

    def _download_myinstant(self, result: MyInstantResult, favorite: bool) -> bool:
        if not self.myinstants_rights.isChecked():
            QMessageBox.warning(
                self,
                "Droits requis",
                "Cochez la confirmation de droits avant tout téléchargement.",
            )
            return False
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

        cache_dir = self.paths.audio_cache if favorite else self.paths.data_dir / "preview-cache"
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
            self._play_file(path, False)
            self.myinstants_status.setText(f"Lecture de « {result.title} »")
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
        self.myinstants_status.setText("Recherche impossible")
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
        for row, sound in enumerate(sounds):
            self.keybind_table.setItem(row, 0, QTableWidgetItem(sound.title))
            self.keybind_table.setItem(row, 1, QTableWidgetItem(sound.source))
            editor = QLineEdit(bindings.get(sound.id, ""))
            editor.setPlaceholderText("Alt+1")
            self.keybind_table.setCellWidget(row, 2, editor)

    def _save_keybinds(self) -> None:
        for row, sound in enumerate(self.library.sounds("", True)):
            editor = self.keybind_table.cellWidget(row, 2)
            if isinstance(editor, QLineEdit) and editor.text().strip():
                self.library.set_keybind(sound.id, editor.text())
        self.statusBar().showMessage("Raccourcis enregistrés localement", 4000)

    def _toggle_hotkeys(self) -> None:
        try:
            if self._hotkeys.active:
                self._hotkeys.stop()
                self.hotkey_toggle.setText("Activer dans Windows")
                return
            sounds = {item.id: item for item in self.library.sounds("", True)}
            self._hotkeys.start(self.library.keybinds(), self.hotkey_play_requested.emit, sounds)
            self.hotkey_toggle.setText("Désactiver dans Windows")
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
