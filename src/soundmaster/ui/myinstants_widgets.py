"""Widgets used by the embedded Myinstants browser."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from soundmaster.core.myinstants import MyInstantResult
from soundmaster.ui.theme import animate_opacity


class MyInstantCard(QWidget):
    """A result card that never leaves the app for normal search/download actions."""

    preview_requested = pyqtSignal(object)
    favorite_requested = pyqtSignal(object)
    selection_changed = pyqtSignal(object, bool)

    def __init__(self, result: MyInstantResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result = result
        layout = QVBoxLayout(self)
        title = QLabel(f"<b>{result.title}</b>")
        title.setWordWrap(True)
        layout.addWidget(title)
        source = QLabel("Myinstants · téléchargement local à la demande")
        source.setObjectName("muted")
        layout.addWidget(source)
        self.select_check = QCheckBox("Sélectionner")
        self.select_check.toggled.connect(
            lambda checked: self.selection_changed.emit(self.result, checked)
        )
        layout.addWidget(self.select_check)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("▶ Tester")
        self.preview_button.setToolTip("Télécharger temporairement puis lire dans votre casque")
        self.preview_button.clicked.connect(lambda: self.preview_requested.emit(self.result))
        self.favorite_button = QPushButton("★ Ajouter aux favoris")
        self.favorite_button.setToolTip("Télécharger hors ligne et ajouter au tableau de bord")
        self.favorite_button.clicked.connect(lambda: self.favorite_requested.emit(self.result))
        actions.addWidget(self.preview_button)
        actions.addWidget(self.favorite_button, 1)
        layout.addLayout(actions)
        self.setObjectName("myInstantCard")

    def set_download_actions_enabled(self, enabled: bool) -> None:
        self.preview_button.setEnabled(enabled)
        self.favorite_button.setEnabled(enabled)

    def set_selection_enabled(self, enabled: bool) -> None:
        self.select_check.setEnabled(enabled)

    def set_selected(self, selected: bool) -> None:
        self.select_check.setChecked(selected)

    def is_selected(self) -> bool:
        return self.select_check.isChecked()

    def enterEvent(self, event) -> None:
        animate_opacity(self, 0.88, 1.0, 180)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        animate_opacity(self, 1.0, 0.94, 220)
        super().leaveEvent(event)
