"""French legal/compliance settings panel.

The panel is a release checklist and configuration surface. It does not certify that
SoundMaster is legally compliant; it makes missing publisher decisions visible and
keeps the commercial-readiness gate conservative.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from soundmaster.core.legal import LegalProfile


class LegalSettingsWidget(QWidget):
    """Read-only view of the publisher profile, privacy defaults and checklist.

    This page describes decisions made by the *publisher* of the application,
    not preferences of the person using it. Letting an end user edit it would
    let them rewrite the legal statements the build ships with, so every field
    is displayed and selectable but never editable.
    """

    saved = pyqtSignal()

    _PUBLISHER_FIELDS: tuple[tuple[str, str], ...] = (
        ("legal_name", "Nom légal de l’éditeur *"),
        ("legal_form", "Forme juridique"),
        ("address", "Adresse complète *"),
        ("country", "Pays *"),
        ("registration_number", "SIREN / registre"),
        ("vat_number", "N° TVA intracommunautaire"),
        ("contact_email", "E-mail légal (facultatif)"),
        ("support_url", "Canal de contact *"),
        ("hosting_provider", "Hébergeur du site / service"),
    )
    _DOCUMENT_FIELDS: tuple[tuple[str, str], ...] = (
        ("legal_notice_url", "Mentions légales *"),
        ("privacy_policy_url", "Politique de confidentialité *"),
        ("terms_of_use_url", "CGU / conditions d’utilisation *"),
        ("terms_of_sale_url", "CGV / conditions de vente *"),
        ("withdrawal_refund_url", "Rétractation et remboursements *"),
        ("data_rights_contact_url", "Exercer ses droits"),
        ("accessibility_statement_url", "Déclaration d’accessibilité"),
        ("qwen_license_reference", "Licence du modèle Qwen exact *"),
        ("qwen_notice_reference", "NOTICE du modèle Qwen exact *"),
        ("qwen_model_id", "Identifiant du modèle Qwen *"),
        ("qwen_model_revision", "Révision du modèle Qwen *"),
        ("qwen_model_sha256", "SHA-256 du modèle Qwen *"),
        ("third_party_audio_rights_reference", "Droits des audios tiers *"),
        ("myinstants_rights_reference", "Droits Myinstants (si utilisé)"),
    )
    _CHECK_FIELDS: tuple[tuple[str, str], ...] = (
        ("publisher_identity_verified", "Identité de l’éditeur vérifiée (mentions légales)"),
        ("legal_documents_published", "CGU, CGV, confidentialité et remboursements publiés et relus"),
        ("privacy_and_gdpr_reviewed", "RGPD : finalités, bases légales, conservation et droits relus"),
        ("consumer_sales_reviewed", "Vente numérique, TVA, garanties et rétractation relues"),
        ("ai_act_transparency_implemented", "Sorties IA signalées et transparence implémentée"),
        ("voice_rights_and_consent_flow_reviewed", "Droits sur les voix et consentement à l’imitation vérifiés"),
        ("qwen_model_license_and_notice_verified", "Licence et NOTICE du modèle Qwen installé vérifiés"),
        ("third_party_audio_rights_verified", "Chaque audio tiers possède une autorisation commerciale"),
        (
            "myinstants_commercial_rights_verified",
            "Droits commerciaux Myinstants obtenus ou intégration désactivée",
        ),
        ("telemetry_is_opt_in_and_documented", "Télémétrie strictement optionnelle et documentée"),
        ("security_and_incident_process_reviewed", "Sécurité, sauvegardes et gestion des incidents relues"),
        ("accessibility_reviewed", "Accessibilité Windows et clavier relue"),
    )

    def __init__(
        self,
        profile: LegalProfile,
        profile_path: Path,
        parent: QWidget | None = None,
        open_url: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.profile_path = profile_path
        self._open_url = open_url or self._open_reference
        self._publisher_inputs: dict[str, QLineEdit] = {}
        self._document_inputs: dict[str, QLineEdit] = {}
        self._check_inputs: dict[str, QCheckBox] = {}
        self._reviewer_reference = QLineEdit()
        self._build_ui()
        self._refresh_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        intro = QLabel(
            "<h2>Conformité & commercialisation</h2>"
            "<p>Cette page est <b>informative et en lecture seule</b>. Elle décrit les "
            "engagements de l’<b>éditeur</b> du logiciel et ne se modifie pas depuis "
            "l’application : rien n’est à remplir pour s’en servir.</p>"
            "<p><b>Vos données restent chez vous.</b> SoundMaster fonctionne entièrement en "
            "local : aucun compte, aucune télémétrie, aucun envoi de vos échantillons, de vos "
            "textes ou de vos audios générés. Rien n’est collecté ni conservé par l’éditeur. "
            "Les seuls accès réseau sont ceux que vous déclenchez : téléchargement des modèles, "
            "recherche Myinstants et vérification des mises à jour.</p>"
            "<p>Cette page ne constitue pas une certification juridique.</p>"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        # Keep the compliance page compact: the previous single long column
        # created a scrollbar even when the user only needed one section. Tabs
        # keep every section reachable without a nested scroll area.
        tabs = QTabWidget()
        for title, section, scrollable in (
            ("Éditeur", self._publisher_group(), False),
            ("Documents", self._documents_group(), True),
            ("Données", self._privacy_group(), False),
            ("Checklist", self._checks_group(), True),
            ("À vérifier", self._sources_group(), False),
        ):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(0, 0, 0, 0)
            if scrollable:
                area = QScrollArea()
                area.setWidgetResizable(True)
                area.setFrameShape(QScrollArea.Shape.NoFrame)
                area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                area.setWidget(section)
                tab_layout.addWidget(area, 1)
            else:
                tab_layout.addWidget(section)
                tab_layout.addStretch(1)
            tabs.addTab(tab, title)
        self.section_tabs = tabs
        root.addWidget(tabs, 1)

        footer = QLabel(
            "Ces informations sont fixées par l’éditeur et livrées avec l’application. "
            "Elles ne peuvent pas être modifiées ici."
        )
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        root.addWidget(footer)

    def _publisher_group(self) -> QGroupBox:
        group = QGroupBox("1. Identité de l’éditeur")
        form = QFormLayout(group)
        for attribute, label in self._PUBLISHER_FIELDS:
            field = QLineEdit(str(getattr(self.profile.publisher, attribute)))
            self._make_read_only(field, "Non renseigné")
            self._publisher_inputs[attribute] = field
            form.addRow(label, field)
        return group

    def _documents_group(self) -> QGroupBox:
        group = QGroupBox("2. Documents et licences à publier")
        layout = QVBoxLayout(group)
        hint = QLabel(
            "Utilisez une URL HTTPS ou un chemin vers un document distribué avec l’application. "
            "Les références Qwen doivent correspondre exactement au modèle installé."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        for attribute, label in self._DOCUMENT_FIELDS:
            field = QLineEdit(str(getattr(self.profile.documents, attribute)))
            self._make_read_only(field, "Non renseigné")
            self._document_inputs[attribute] = field
            row = QHBoxLayout()
            row.addWidget(field, 1)
            open_button = QPushButton("Ouvrir")
            open_button.setEnabled(bool(field.text().strip()))
            open_button.clicked.connect(
                lambda _checked=False, current_field=field: self._open_url(current_field.text().strip())
            )
            row.addWidget(open_button)
            form.addRow(label, row)
        layout.addLayout(form)

        self.myinstants_enabled = QCheckBox(
            "Myinstants est activé dans cette édition (droits commerciaux écrits obligatoires)"
        )
        self.myinstants_enabled.setChecked(self.profile.myinstants_enabled)
        self._make_indicator(self.myinstants_enabled)
        layout.addWidget(self.myinstants_enabled)
        return group

    def _privacy_group(self) -> QGroupBox:
        group = QGroupBox("3. Données personnelles et paramètres par défaut")
        layout = QVBoxLayout(group)
        privacy = self.profile.privacy

        summary = QLabel(
            "Aucune donnée n’est collectée ni transmise : tout le traitement a lieu sur "
            "votre ordinateur. Les durées ci-dessous concernent uniquement les fichiers "
            "conservés <b>localement</b>, que vous pouvez supprimer à tout moment."
        )
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(summary)

        self.local_only = QCheckBox("Traitement local uniquement")
        self.local_only.setChecked(privacy.local_processing_only)
        self._make_indicator(self.local_only)
        layout.addWidget(self.local_only)

        self.telemetry = QCheckBox("Télémétrie (aucune n’est collectée)")
        self.telemetry.setChecked(privacy.telemetry_enabled_by_default)
        self._make_indicator(self.telemetry)
        layout.addWidget(self.telemetry)

        self.model_improvement = QCheckBox(
            "Utilisation de données utilisateur pour améliorer le modèle"
        )
        self.model_improvement.setChecked(privacy.allow_model_improvement_from_user_data)
        self._make_indicator(self.model_improvement)
        layout.addWidget(self.model_improvement)

        form = QFormLayout()
        self.voice_retention = QSpinBox()
        self.voice_retention.setRange(0, 3650)
        self.voice_retention.setSuffix(" jours")
        self.voice_retention.setValue(privacy.voice_samples_retention_days)
        self._make_read_only_number(self.voice_retention)
        form.addRow("Conservation locale des échantillons vocaux", self.voice_retention)

        self.audio_retention = QSpinBox()
        self.audio_retention.setRange(0, 3650)
        self.audio_retention.setSuffix(" jours")
        self.audio_retention.setValue(privacy.generated_audio_retention_days)
        self._make_read_only_number(self.audio_retention)
        form.addRow("Conservation locale des audios générés", self.audio_retention)
        layout.addLayout(form)
        return group

    def _checks_group(self) -> QGroupBox:
        group = QGroupBox("4. Checklist de mise sur le marché")
        layout = QVBoxLayout(group)
        warning = QLabel(
            "Ces cases sont une déclaration de l’éditeur, pas une preuve automatique, et "
            "s’affichent en lecture seule. L’application bloque volontairement l’état "
            "« prêt à commercialiser » tant qu’une ligne manque."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self._reviewer_reference.setText(self.profile.reviewer_reference)
        self._make_read_only(self._reviewer_reference, "Revue juridique externe non effectuée")
        layout.addWidget(QLabel("Référence de la revue juridique externe *"))
        layout.addWidget(self._reviewer_reference)
        for attribute, label in self._CHECK_FIELDS:
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(getattr(self.profile.checks, attribute)))
            self._make_indicator(checkbox)
            self._check_inputs[attribute] = checkbox
            layout.addWidget(checkbox)
        return group

    def _sources_group(self) -> QGroupBox:
        group = QGroupBox("5. Points d’attention obligatoires")
        layout = QVBoxLayout(group)
        notes = QLabel(
            "<b>Voix :</b> autorisation, consentement et procédure de retrait.<br>"
            "<b>Myinstants :</b> usage commercial interdit sans autorisation écrite et droits des œuvres.<br>"
            "<b>Qwen3-TTS :</b> licence, NOTICE, révision et checksum doivent correspondre au build.<br>"
            "<b>Vente :</b> faites valider prix, TVA, CGV, garanties et rétractation pour chaque marché.<br>"
            "<b>Mentions légales :</b> identité, adresse, contact et hébergeur doivent être exacts."
        )
        notes.setWordWrap(True)
        notes.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(notes)
        return group

    @staticmethod
    def _make_read_only(field: QLineEdit, empty_text: str) -> None:
        """Show a value that can be read and copied, but never edited."""

        field.setReadOnly(True)
        field.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        field.setPlaceholderText(empty_text)
        field.setObjectName("readOnlyField")

    @staticmethod
    def _make_indicator(checkbox: QCheckBox) -> None:
        """Turn a checkbox into a state indicator the user cannot toggle."""

        checkbox.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    @staticmethod
    def _make_read_only_number(spin: QSpinBox) -> None:
        spin.setReadOnly(True)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _refresh_status(self) -> None:
        # The widgets only display the profile, so nothing is ever written back.
        ready, reasons = self.profile.commercial_readiness()
        if ready:
            self.status_label.setText(
                "<b style='color:#137333'>Checklist technique complétée.</b> "
                "La validation juridique externe de l’éditeur reste obligatoire."
            )
        else:
            displayed = reasons[:4]
            suffix = " …" if len(reasons) > len(displayed) else ""
            self.status_label.setText(
                "<b style='color:#b3261e'>Non prêt à commercialiser.</b> "
                f"{len(reasons)} élément(s) restent à vérifier : "
                + "; ".join(displayed)
                + suffix
            )

    @staticmethod
    def _open_reference(reference: str) -> None:
        parsed = QUrl.fromUserInput(reference)
        if parsed.isValid():
            QDesktopServices.openUrl(parsed)


class SettingsWindow(QWidget):
    """Settings container ready to host audio and application settings later."""

    def __init__(self, legal_widget: LegalSettingsWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SoundMaster — Paramètres")
        self.resize(900, 760)
        tabs = QTabWidget(self)
        tabs.addTab(legal_widget, "Conformité & légal")
        placeholder = QLabel(
            "Les réglages audio, raccourcis et préférences générales seront ajoutés dans les prochaines étapes."
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        tabs.addTab(placeholder, "Autres paramètres")
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
