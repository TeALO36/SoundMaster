"""Widgets used by the embedded Myinstants browser."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from soundmaster.core.myinstants import MyInstantResult


class MyInstantCard(QWidget):
    """A result card that never leaves the app for normal search/download actions."""

    preview_requested = pyqtSignal(object)
    preview_hovered = pyqtSignal(object)
    favorite_requested = pyqtSignal(object)
    remove_favorite_requested = pyqtSignal(object)
    selection_changed = pyqtSignal(object, bool)

    def __init__(self, result: MyInstantResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result = result
        self._preview_playing = False
        self._is_favorite = False
        layout = QVBoxLayout(self)
        title = QLabel(f"<b>{result.title}</b>")
        title.setWordWrap(True)
        layout.addWidget(title)
        source = QLabel("Myinstants · aperçu en direct · favori = hors ligne")
        source.setObjectName("muted")
        layout.addWidget(source)
        self.select_check = QCheckBox("Sélectionner")
        self.select_check.toggled.connect(
            lambda checked: self.selection_changed.emit(self.result, checked)
        )
        layout.addWidget(self.select_check)
        actions = QHBoxLayout()
        self.preview_button = QPushButton("▶ Tester")
        self.preview_button.setToolTip("Lire en direct comme sur Myinstants, sans conserver le fichier")
        self.preview_button.installEventFilter(self)
        self.preview_button.clicked.connect(self._toggle_preview)
        self.favorite_button = QPushButton("★ Ajouter aux favoris")
        self.favorite_button.setToolTip("Télécharger hors ligne et ajouter au tableau de bord")
        self.favorite_button.clicked.connect(self._favorite_clicked)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.favorite_button, 1)
        layout.addLayout(actions)
        self.setObjectName("myInstantCard")

    def _favorite_clicked(self) -> None:
        if self._is_favorite:
            self.remove_favorite_requested.emit(self.result)
        else:
            self.favorite_requested.emit(self.result)

    def set_is_favorite(self, favorite: bool) -> None:
        self._is_favorite = favorite
        if favorite:
            self.favorite_button.setText("★ Supprimer des favoris")
            self.favorite_button.setObjectName("ghostButton")
            self.favorite_button.setToolTip("Retirer ce son de vos favoris du tableau de bord")
        else:
            self.favorite_button.setText("★ Ajouter aux favoris")
            self.favorite_button.setObjectName("secondaryButton")
            self.favorite_button.setToolTip("Télécharger hors ligne et ajouter au tableau de bord")
        style = self.favorite_button.style()
        if style is not None:
            style.unpolish(self.favorite_button)
            style.polish(self.favorite_button)

    def _toggle_preview(self) -> None:
        """Ask the window to start or stop this card's active preview."""

        self.preview_requested.emit(self.result)

    def set_preview_playing(self, playing: bool) -> None:
        """Reflect whether this card owns the currently playing preview."""

        self._preview_playing = playing
        self.preview_button.setText("■ Stop" if playing else "▶ Tester")
        self.preview_button.setToolTip(
            "Arrêter la lecture" if playing else "Lire en direct sans télécharger"
        )

    def eventFilter(self, watched, event) -> bool:
        if watched is self.preview_button and event.type() == QEvent.Type.Enter:
            # Warm the player while the pointer is over Tester, so the click only
            # starts an already-negotiated stream instead of restarting the URL.
            self.preview_hovered.emit(self.result)
        return super().eventFilter(watched, event)

    def set_download_actions_enabled(self, enabled: bool) -> None:
        self.preview_button.setEnabled(enabled)
        self.favorite_button.setEnabled(enabled)

    def set_selection_enabled(self, enabled: bool) -> None:
        self.select_check.setEnabled(enabled)

    def set_selected(self, selected: bool) -> None:
        self.select_check.setChecked(selected)

    def is_selected(self) -> bool:
        return self.select_check.isChecked()
