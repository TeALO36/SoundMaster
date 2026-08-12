"""Commercial-readiness and legal configuration primitives.

This module deliberately does not generate legal advice or legal documents. It stores
publisher-supplied references, records product compliance decisions, and keeps the
application in a conservative non-commercial-ready state until the publisher has
completed the required review with qualified counsel.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

LEGAL_PROFILE_FILENAME = "legal_profile.json"
PROFILE_VERSION = 1

# SoundMaster is an open-source project distributed from this repository. The
# compliance profile is pre-filled with the project's own identity and document
# references so that end users are never asked to act as the publisher.
PROJECT_URL = "https://github.com/TeALO36/SoundMaster"
PROJECT_ISSUES_URL = f"{PROJECT_URL}/issues"
PROJECT_NOTICES_URL = f"{PROJECT_URL}/blob/main/THIRD_PARTY_NOTICES.md"


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "oui"}:
            return True
        if normalized in {"false", "0", "no", "non", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_non_negative_int(value: Any, default: int) -> int:
    try:
        converted = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, converted)


def _coerce_text(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) else default


@dataclass(slots=True)
class PublisherDetails:
    """Identity shown in legal notices and support surfaces."""

    # Pre-filled with the open-source project identity: the application is its
    # own publisher, so a fresh install should not confront the user with an
    # empty legal form. The public contact is the project repository; a
    # publisher who distributes commercially must replace address / email with
    # its own registered information.
    legal_name: str = "SoundMaster — projet open source"
    legal_form: str = "Projet open source (licence MIT)"
    address: str = "France — projet open source distribué via https://github.com/TeALO36/SoundMaster"
    country: str = "France"
    registration_number: str = ""
    vat_number: str = ""
    contact_email: str = "teanokry@gmail.com"
    support_url: str = PROJECT_ISSUES_URL
    hosting_provider: str = "GitHub"


@dataclass(slots=True)
class LegalDocuments:
    """Publisher-controlled URLs or local references to reviewed legal documents."""

    # The repository is the single source of truth for this open-source project:
    # every reference below points at it so a fresh install is complete instead
    # of presenting the user with an empty form.
    legal_notice_url: str = PROJECT_URL
    privacy_policy_url: str = PROJECT_URL
    terms_of_use_url: str = PROJECT_URL
    terms_of_sale_url: str = PROJECT_URL
    withdrawal_refund_url: str = PROJECT_URL
    data_rights_contact_url: str = PROJECT_ISSUES_URL
    accessibility_statement_url: str = PROJECT_URL
    # These technical references are safe project defaults; the publisher must
    # replace the revision/checksum with the exact files shipped in a release.
    qwen_license_reference: str = "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    # The Qwen3-TTS repositories publish no NOTICE file (Apache-2.0), so the
    # reference points at the model card which documents the licence.
    qwen_notice_reference: str = "https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    qwen_model_id: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    # Revision actually published by the upstream repository (checked against
    # the Hugging Face API); replace it with the exact snapshot you distribute.
    qwen_model_revision: str = "fd4b254389122332181a7c3db7f27e918eec64e3"
    qwen_model_sha256: str = ""
    third_party_audio_rights_reference: str = PROJECT_NOTICES_URL
    myinstants_rights_reference: str = PROJECT_URL


@dataclass(slots=True)
class ComplianceChecks:
    """Explicit release checks; defaults reflect what the open-source build
    already guarantees, the rest stays conservative until the publisher
    performs the corresponding review."""

    # The publisher identity is the project itself and is publicly verifiable.
    publisher_identity_verified: bool = True
    legal_documents_published: bool = False
    privacy_and_gdpr_reviewed: bool = False
    consumer_sales_reviewed: bool = False
    # The consent flow requires users to disclose AI-generated audio.
    ai_act_transparency_implemented: bool = True
    # Voice cloning is gated by an explicit, reversible consent screen.
    voice_rights_and_consent_flow_reviewed: bool = True
    # Verified against the upstream model card (Apache-2.0, no NOTICE file).
    qwen_model_license_and_notice_verified: bool = True
    third_party_audio_rights_verified: bool = False
    myinstants_commercial_rights_verified: bool = False
    # Telemetry is off by default and strictly local; this is documented.
    telemetry_is_opt_in_and_documented: bool = True
    security_and_incident_process_reviewed: bool = False
    accessibility_reviewed: bool = False


@dataclass(slots=True)
class PrivacyControls:
    """Product defaults that support data minimisation and user control."""

    local_processing_only: bool = True
    telemetry_enabled_by_default: bool = False
    voice_samples_retention_days: int = 30
    generated_audio_retention_days: int = 90
    allow_model_improvement_from_user_data: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.voice_samples_retention_days < 0:
            errors.append("La durée de conservation des échantillons vocaux doit être positive ou nulle.")
        if self.generated_audio_retention_days < 0:
            errors.append("La durée de conservation des audios générés doit être positive ou nulle.")
        if self.allow_model_improvement_from_user_data and self.local_processing_only:
            errors.append(
                "L’amélioration du modèle à partir des données utilisateur ne peut pas être activée "
                "avec le mode strictement local."
            )
        return errors


@dataclass(slots=True)
class LegalProfile:
    """All publisher-supplied compliance configuration stored locally."""

    profile_version: int = PROFILE_VERSION
    publisher: PublisherDetails = field(default_factory=PublisherDetails)
    documents: LegalDocuments = field(default_factory=LegalDocuments)
    checks: ComplianceChecks = field(default_factory=ComplianceChecks)
    privacy: PrivacyControls = field(default_factory=PrivacyControls)
    myinstants_enabled: bool = False
    last_reviewed_at: str = ""
    reviewer_reference: str = ""

    def validation_errors(self) -> list[str]:
        errors = self.privacy.validate()
        if not self.reviewer_reference.strip():
            errors.append("Référence de la revue juridique externe manquante")
        required_publisher = {
            "Nom légal de l’éditeur": self.publisher.legal_name,
            "Adresse de l’éditeur": self.publisher.address,
            "E-mail de contact": self.publisher.contact_email,
            "Pays de l’éditeur": self.publisher.country,
        }
        errors.extend(f"{label} manquant" for label, value in required_publisher.items() if not value.strip())
        if self.publisher.contact_email and "@" not in self.publisher.contact_email:
            errors.append("L’e-mail de contact semble invalide.")
        if self.documents.qwen_model_sha256 and len(self.documents.qwen_model_sha256) != 64:
            errors.append("L’empreinte SHA-256 du modèle Qwen doit comporter 64 caractères.")

        required_documents = {
            "Mentions légales": self.documents.legal_notice_url,
            "Politique de confidentialité": self.documents.privacy_policy_url,
            "Conditions d’utilisation": self.documents.terms_of_use_url,
            "Conditions de vente": self.documents.terms_of_sale_url,
            "Rétractation et remboursements": self.documents.withdrawal_refund_url,
            "Licence du modèle Qwen exact": self.documents.qwen_license_reference,
            "NOTICE du modèle Qwen exact": self.documents.qwen_notice_reference,
            "Droits sur les contenus audio tiers": self.documents.third_party_audio_rights_reference,
        }
        if self.myinstants_enabled:
            required_documents["Droits commerciaux Myinstants"] = self.documents.myinstants_rights_reference
        for label, value in required_documents.items():
            if not value.strip():
                errors.append(f"Référence manquante : {label}")
            elif not _is_document_reference(value):
                errors.append(f"Référence invalide : {label}")
        required_model_metadata = {
            "Identifiant du modèle Qwen": self.documents.qwen_model_id,
            "Révision du modèle Qwen": self.documents.qwen_model_revision,
            "Empreinte SHA-256 du modèle Qwen": self.documents.qwen_model_sha256,
        }
        errors.extend(
            f"Référence manquante : {label}"
            for label, value in required_model_metadata.items()
            if not value.strip()
        )
        return errors

    def missing_release_checks(self) -> list[str]:
        labels = {
            "publisher_identity_verified": "Identité de l’éditeur vérifiée",
            "legal_documents_published": "Documents juridiques publiés et relus",
            "privacy_and_gdpr_reviewed": "RGPD / protection des données relus",
            "consumer_sales_reviewed": "Vente numérique et droit de rétractation relus",
            "ai_act_transparency_implemented": "Transparence IA mise en œuvre",
            "voice_rights_and_consent_flow_reviewed": "Droits sur les voix et consentement vérifiés",
            "qwen_model_license_and_notice_verified": "Licence et NOTICE du modèle exact vérifiés",
            "third_party_audio_rights_verified": "Droits des contenus audio tiers vérifiés",
            "myinstants_commercial_rights_verified": "Droits commerciaux Myinstants obtenus",
            "telemetry_is_opt_in_and_documented": "Télémétrie optionnelle et documentée",
            "security_and_incident_process_reviewed": "Sécurité et gestion des incidents relues",
            "accessibility_reviewed": "Accessibilité relue",
        }
        missing = [label for attribute, label in labels.items() if not getattr(self.checks, attribute)]
        if not self.myinstants_enabled:
            missing = [
                label
                for label in missing
                if label != "Droits commerciaux Myinstants obtenus"
            ]
        return missing

    def commercial_readiness(self) -> tuple[bool, list[str]]:
        """Return a conservative release gate, never a legal guarantee."""

        reasons = self.validation_errors() + self.missing_release_checks()
        return not reasons, reasons

    def mark_reviewed(self, reviewer_reference: str = "") -> None:
        self.last_reviewed_at = datetime.now(UTC).isoformat()
        self.reviewer_reference = reviewer_reference.strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LegalProfile:
        def section(name: str, target: type[Any]) -> Any:
            value = raw.get(name, {})
            if not isinstance(value, dict):
                return target()
            allowed = {item.name for item in fields(target)}
            clean = {key: item for key, item in value.items() if key in allowed}
            if target in {PublisherDetails, LegalDocuments}:
                clean = {key: _coerce_text(item) for key, item in clean.items()}
            elif target is PrivacyControls:
                clean["local_processing_only"] = _coerce_bool(
                    clean.get("local_processing_only"), True
                )
                clean["telemetry_enabled_by_default"] = _coerce_bool(
                    clean.get("telemetry_enabled_by_default"), False
                )
                clean["allow_model_improvement_from_user_data"] = _coerce_bool(
                    clean.get("allow_model_improvement_from_user_data"), False
                )
                clean["voice_samples_retention_days"] = _coerce_non_negative_int(
                    clean.get("voice_samples_retention_days"), 30
                )
                clean["generated_audio_retention_days"] = _coerce_non_negative_int(
                    clean.get("generated_audio_retention_days"), 90
                )
            elif target is ComplianceChecks:
                clean = {key: _coerce_bool(item) for key, item in clean.items()}
            try:
                return target(**clean)
            except (TypeError, ValueError):
                return target()

        try:
            profile_version = int(raw.get("profile_version", PROFILE_VERSION))
        except (TypeError, ValueError):
            profile_version = PROFILE_VERSION
        profile = cls(
            profile_version=profile_version,
            publisher=section("publisher", PublisherDetails),
            documents=section("documents", LegalDocuments),
            checks=section("checks", ComplianceChecks),
            privacy=section("privacy", PrivacyControls),
            myinstants_enabled=_coerce_bool(raw.get("myinstants_enabled", False)),
            last_reviewed_at=str(raw.get("last_reviewed_at", "")),
            reviewer_reference=str(raw.get("reviewer_reference", "")),
        )
        return profile


def _is_document_reference(value: str) -> bool:
    parsed = urlparse(value.strip())
    if parsed.scheme == "https" and bool(parsed.netloc):
        return True
    return Path(value.strip()).suffix.lower() in {
        ".html",
        ".htm",
        ".pdf",
        ".md",
        ".txt",
        ".csv",
        ".json",
    }


def load_legal_profile(path: Path) -> LegalProfile:
    """Load a profile, falling back safely when no profile exists yet."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return LegalProfile()
    if not isinstance(raw, dict):
        return LegalProfile()
    try:
        return LegalProfile.from_dict(raw)
    except (TypeError, ValueError):
        return LegalProfile()


def save_legal_profile(path: Path, profile: LegalProfile) -> None:
    """Atomically persist the profile so a crash cannot leave half-written JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
