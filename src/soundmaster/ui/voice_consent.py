"""User-facing terms for the voice-cloning feature.

This panel is the user's own decision, not the publisher checklist in
:mod:`soundmaster.ui.legal_settings`. Unticking it locks the cloning workspace
immediately, which is the behaviour the feature gate in the main window relies on.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

CONSENT_PREFERENCE_KEY = "voice_cloning_terms_accepted"

TERMS_HTML = """
<b>Avant de cloner une voix, vous acceptez les règles suivantes :</b>
<ul>
<li>Vous n’utilisez que des voix pour lesquelles vous avez <b>l’accord explicite</b>
de la personne concernée, ou votre propre voix.</li>
<li>Vous n’usurpez l’identité de personne et vous ne produisez aucun contenu
trompeur, frauduleux, diffamatoire ou harcelant.</li>
<li>Vous signalez qu’un audio est généré par IA lorsque vous le diffusez.</li>
<li>Vous respectez les lois de votre pays sur l’image, la voix et les données
personnelles, ainsi que les droits des œuvres utilisées.</li>
<li>Les échantillons et les générations restent sur votre ordinateur : c’est vous
qui les conservez, les partagez ou les supprimez.</li>
</ul>
"""

LIABILITY_HTML = """
<b>Responsabilité</b><br>
SoundMaster fournit un outil technique fonctionnant localement. L’éditeur de
SoundMaster <b>n’est pas responsable</b> de l’usage que vous faites du clonage de
voix, des voix que vous enregistrez, des textes que vous générez, ni des
conséquences de leur diffusion. <b>Vous en êtes seul responsable.</b>
"""


class VoiceConsentPanel(QWidget):
    """Explicit, reversible opt-in gate for the voice-cloning workspace."""

    changed = pyqtSignal(bool)

    def __init__(self, accepted: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consentPanel")
        # A QWidget subclass only paints its stylesheet surface with this set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._flash_timer: QTimer | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("Conditions d’utilisation du clonage de voix")
        title.setObjectName("consentTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        terms = QLabel(TERMS_HTML)
        terms.setWordWrap(True)
        terms.setTextFormat(Qt.TextFormat.RichText)
        terms.setObjectName("consentBody")
        layout.addWidget(terms)

        liability = QLabel(LIABILITY_HTML)
        liability.setWordWrap(True)
        liability.setTextFormat(Qt.TextFormat.RichText)
        liability.setObjectName("dangerNote")
        layout.addWidget(liability)

        self.accept_box = QCheckBox(
            "J’ai lu et j’accepte ces conditions. J’assume l’entière responsabilité "
            "des voix que je clone."
        )
        self.accept_box.setObjectName("consentCheck")
        self.accept_box.setChecked(accepted)
        self.accept_box.toggled.connect(self.changed.emit)
        layout.addWidget(self.accept_box)

        footer = QLabel(
            "Vous pouvez décocher cette case à tout moment : le menu "
            "« Clonage de voix » est alors immédiatement verrouillé."
        )
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        layout.addWidget(footer)

    def is_accepted(self) -> bool:
        return self.accept_box.isChecked()

    def set_accepted(self, accepted: bool) -> None:
        if self.accept_box.isChecked() == accepted:
            return
        self.accept_box.setChecked(accepted)

    def flash(self) -> None:
        """Draw the eye here after a redirect from the locked cloning menu."""

        self.setObjectName("consentPanelHighlight")
        self._repolish()
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_flash)
        self._flash_timer.start(2600)

    def _clear_flash(self) -> None:
        self.setObjectName("consentPanel")
        self._repolish()

    def _repolish(self) -> None:
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()
