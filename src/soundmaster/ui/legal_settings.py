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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from soundmaster.core.legal import LegalProfile, save_legal_profile


class LegalSettingsWidget(QWidget):
    """Editable publisher profile, privacy defaults, and release checklist."""

    saved = pyqtSignal()

    _PUBLISHER_FIELDS: tuple[tuple[str, str], ...] = (
        ("legal_name", "Nom légal de l’éditeur *"),
        ("legal_form", "Forme juridique"),
        ("address", "Adresse complète *"),
        ("country", "Pays *"),
        ("registration_number", "SIREN / registre"),
        ("vat_number", "N° TVA intracommunautaire"),
        ("contact_email", "E-mail légal / support *"),
        ("support_url", "URL du support"),
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
            "<p>Cette page est destinée à l’<b>éditeur</b> du logiciel, pas à l’utilisateur final. "
            "SoundMaster étant un projet open source, elle est déjà pré-remplie avec l’identité "
            "du projet et ses références (dépôt GitHub, licences des modèles). "
            "Rien n’est à remplir pour simplement utiliser l’application. Elle ne constitue pas "
            "une certification juridique : faites relire les documents par un professionnel "
            "compétent avant toute vente ou redistribution.</p>"
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

        actions = QHBoxLayout()
        self.save_button = QPushButton("Enregistrer la configuration")
        self.save_button.clicked.connect(self._save)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        root.addLayout(actions)

    def _publisher_group(self) -> QGroupBox:
        group = QGroupBox("1. Identité de l’éditeur")
        form = QFormLayout(group)
        for attribute, label in self._PUBLISHER_FIELDS:
            field = QLineEdit(str(getattr(self.profile.publisher, attribute)))
            field.setPlaceholderText(
                "Ex. SoundMaster SAS — remplacez par les informations officielles"
            )
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
            placeholder = (
                "À remplacer par la référence exacte vérifiée"
                if attribute in {
                    "qwen_license_reference",
                    "qwen_notice_reference",
                    "qwen_model_revision",
                    "qwen_model_sha256",
                    "third_party_audio_rights_reference",
                }
                else "https://… ou chemin local vers le document exact"
            )
            field.setPlaceholderText(placeholder)
            self._document_inputs[attribute] = field
            row = QHBoxLayout()
            row.addWidget(field, 1)
            open_button = QPushButton("Ouvrir")
            open_button.setEnabled(bool(field.text().strip()))
            field.textChanged.connect(
                lambda text, button=open_button: button.setEnabled(bool(text.strip()))
            )
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
        self.myinstants_enabled.toggled.connect(lambda _checked: self._refresh_status())
        layout.addWidget(self.myinstants_enabled)
        return group

    def _privacy_group(self) -> QGroupBox:
        group = QGroupBox("3. Données personnelles et paramètres par défaut")
        layout = QVBoxLayout(group)
        privacy = self.profile.privacy

        self.local_only = QCheckBox("Traitement local uniquement (recommandé)")
        self.local_only.setChecked(privacy.local_processing_only)
        self.local_only.setToolTip("Aucun échantillon vocal ni prompt n’est envoyé par défaut.")
        self.local_only.toggled.connect(lambda _checked: self._refresh_status())

        layout.addWidget(self.local_only)

        self.telemetry = QCheckBox("Autoriser la télémétrie (désactivée par défaut)")
        self.telemetry.setChecked(privacy.telemetry_enabled_by_default)
        layout.addWidget(self.telemetry)

        self.model_improvement = QCheckBox(
            "Autoriser l’utilisation de données utilisateur pour améliorer le modèle"
        )
        self.model_improvement.setChecked(privacy.allow_model_improvement_from_user_data)
        layout.addWidget(self.model_improvement)

        form = QFormLayout()
        self.voice_retention = QSpinBox()
        self.voice_retention.setRange(0, 3650)
        self.voice_retention.setSuffix(" jours")
        self.voice_retention.setValue(privacy.voice_samples_retention_days)
        form.addRow("Conservation des échantillons vocaux", self.voice_retention)

        self.audio_retention = QSpinBox()
        self.audio_retention.setRange(0, 3650)
        self.audio_retention.setSuffix(" jours")
        self.audio_retention.setValue(privacy.generated_audio_retention_days)
        form.addRow("Conservation des audios générés", self.audio_retention)
        layout.addLayout(form)
        return group

    def _checks_group(self) -> QGroupBox:
        group = QGroupBox("4. Checklist de mise sur le marché")
        layout = QVBoxLayout(group)
        warning = QLabel(
            "Ne cochez une ligne qu’après avoir vérifié les pièces correspondantes. "
            "Ces cases sont une déclaration de l’éditeur, pas une preuve automatique. "
            "L’application bloque volontairement l’état « prêt à commercialiser » tant qu’une "
            "ligne manque."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self._reviewer_reference.setText(self.profile.reviewer_reference)
        self._reviewer_reference.setPlaceholderText("Référence du dossier, cabinet ou responsable interne")
        layout.addWidget(QLabel("Référence de la revue juridique externe *"))
        layout.addWidget(self._reviewer_reference)
        for attribute, label in self._CHECK_FIELDS:
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(getattr(self.profile.checks, attribute)))
            checkbox.toggled.connect(lambda _checked: self._refresh_status())
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

    def _profile_from_ui(self) -> None:
        for attribute, field in self._publisher_inputs.items():
            setattr(self.profile.publisher, attribute, field.text().strip())
        for attribute, field in self._document_inputs.items():
            setattr(self.profile.documents, attribute, field.text().strip())
        for attribute, checkbox in self._check_inputs.items():
            setattr(self.profile.checks, attribute, checkbox.isChecked())
        self.profile.myinstants_enabled = self.myinstants_enabled.isChecked()
        self.profile.reviewer_reference = self._reviewer_reference.text().strip()
        self.profile.privacy.local_processing_only = self.local_only.isChecked()
        self.profile.privacy.telemetry_enabled_by_default = self.telemetry.isChecked()
        self.profile.privacy.allow_model_improvement_from_user_data = self.model_improvement.isChecked()
        self.profile.privacy.voice_samples_retention_days = self.voice_retention.value()
        self.profile.privacy.generated_audio_retention_days = self.audio_retention.value()

    def _refresh_status(self) -> None:
        self._profile_from_ui() if self._publisher_inputs else None
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

    def _save(self) -> None:
        self._profile_from_ui()
        self.profile.mark_reviewed(self._reviewer_reference.text())
        try:
            save_legal_profile(self.profile_path, self.profile)
        except OSError as error:
            QMessageBox.critical(self, "Enregistrement impossible", str(error))
            return
        self._refresh_status()
        self.saved.emit()
        QMessageBox.information(
            self,
            "Configuration enregistrée",
            "La configuration de conformité a été enregistrée localement. "
            "Elle ne constitue pas une certification juridique.",
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
