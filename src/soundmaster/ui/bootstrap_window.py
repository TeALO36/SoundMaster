"""Minimal UI used to verify the Step 1 installation."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from soundmaster.core.legal import LegalProfile
from soundmaster.ui.legal_settings import LegalSettingsWidget, SettingsWindow


class BootstrapWindow(QMainWindow):
    """Small validation window with the legal/compliance settings entry point."""

    def __init__(self, legal_profile: LegalProfile, legal_profile_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("SoundMaster — Initialisation")
        self.resize(560, 320)
        self._legal_profile = legal_profile
        self._legal_profile_path = legal_profile_path
        self._settings_window: SettingsWindow | None = None

        root = QWidget(self)
        layout = QVBoxLayout(root)
        message = QLabel(
            "<h2>SoundMaster</h2>"
            "<p>La structure de l’application est prête.</p>"
            "<p>Le routage audio, les onglets et le moteur vocal seront ajoutés dans les prochaines étapes.</p>"
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setMargin(32)
        message.setWordWrap(True)
        layout.addWidget(message, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        settings_button = QPushButton("⚙ Paramètres")
        settings_button.setToolTip("Ouvrir la conformité, les licences et les paramètres de l’application")
        settings_button.clicked.connect(self._open_settings)
        actions.addWidget(settings_button)
        layout.addLayout(actions)
        self.setCentralWidget(root)

    def _open_settings(self) -> None:
        legal_widget = LegalSettingsWidget(self._legal_profile, self._legal_profile_path)
        legal_widget.saved.connect(self._on_legal_profile_saved)
        self._settings_window = SettingsWindow(legal_widget, self)
        self._settings_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_legal_profile_saved(self) -> None:
        self.statusBar().showMessage("Configuration de conformité enregistrée", 5000)
