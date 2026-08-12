from pathlib import Path

from soundmaster.core.legal import (
    ComplianceChecks,
    LegalProfile,
    load_legal_profile,
    save_legal_profile,
)


def _completed_profile() -> LegalProfile:
    profile = LegalProfile()
    profile.publisher.legal_name = "SoundMaster SAS"
    profile.publisher.address = "1 rue de Paris, 75001 Paris"
    profile.publisher.contact_email = "legal@example.com"
    profile.documents.legal_notice_url = "https://example.com/legal"
    profile.documents.privacy_policy_url = "https://example.com/privacy"
    profile.documents.terms_of_use_url = "https://example.com/terms"
    profile.documents.terms_of_sale_url = "https://example.com/sales"
    profile.documents.withdrawal_refund_url = "https://example.com/refunds"
    profile.documents.qwen_license_reference = "licenses/QWEN-LICENSE.txt"
    profile.documents.qwen_notice_reference = "licenses/QWEN-NOTICE.txt"
    profile.documents.qwen_model_id = "Qwen/Qwen3-TTS-VoiceDesign"
    profile.documents.qwen_model_revision = "revision-2026-01"
    profile.documents.qwen_model_sha256 = "a" * 64
    profile.documents.third_party_audio_rights_reference = "licenses/audio-rights.csv"
    profile.reviewer_reference = "Dossier juridique interne 2026-01"
    profile.checks = ComplianceChecks(**{field: True for field in ComplianceChecks.__dataclass_fields__})
    return profile


def test_new_profile_is_prefilled_for_the_end_user_but_not_commercially_ready() -> None:
    profile = LegalProfile()
    # The profile ships pre-filled with the open-source project identity so a
    # fresh install never confronts the user with an empty publisher form.
    assert profile.publisher.country == "France"
    assert profile.publisher.legal_name == "SoundMaster — projet open source"
    assert profile.publisher.support_url == "https://github.com/TeALO36/SoundMaster/issues"
    assert profile.publisher.address != ""
    assert "@" in profile.publisher.contact_email
    assert profile.documents.qwen_model_id == "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    assert profile.documents.qwen_notice_reference != ""
    # The upstream revision is filled from the published repository snapshot.
    assert profile.documents.qwen_model_revision == "fd4b254389122332181a7c3db7f27e918eec64e3"
    # The SHA-256 depends on the exact file actually distributed: only the
    # publisher can fill it for its own build, so it stays empty.
    assert profile.documents.qwen_model_sha256 == ""

    # Product facts that the open-source build genuinely guarantees are pre-checked.
    assert profile.checks.publisher_identity_verified is True
    assert profile.checks.voice_rights_and_consent_flow_reviewed is True
    assert profile.checks.telemetry_is_opt_in_and_documented is True
    assert profile.checks.qwen_model_license_and_notice_verified is True

    ready, reasons = profile.commercial_readiness()

    assert ready is False
    # The pre-filled fields no longer trigger a missing-publisher error; the
    # gate still blocks on the publisher-only review steps.
    assert "Nom légal de l’éditeur manquant" not in reasons
    assert "Adresse de l’éditeur manquant" not in reasons
    assert "E-mail de contact manquant" not in reasons
    assert "Identité de l’éditeur vérifiée" not in reasons
    assert "Télémétrie optionnelle et documentée" not in reasons
    # Legal review, the exact build checksum and RGPD review remain the
    # publisher's responsibility.
    assert "Référence de la revue juridique externe manquante" in reasons
    assert "Référence manquante : Empreinte SHA-256 du modèle Qwen" in reasons
    assert "RGPD / protection des données relus" in reasons


def test_completed_profile_can_pass_the_technical_gate() -> None:
    ready, reasons = _completed_profile().commercial_readiness()

    assert ready is True
    assert reasons == []


def test_profile_round_trip_is_local_and_json_backed(tmp_path: Path) -> None:
    path = tmp_path / "legal_profile.json"
    profile = _completed_profile()
    save_legal_profile(path, profile)

    loaded = load_legal_profile(path)

    assert loaded.publisher.legal_name == "SoundMaster SAS"
    assert loaded.documents.legal_notice_url == "https://example.com/legal"
    assert loaded.documents.qwen_license_reference == "licenses/QWEN-LICENSE.txt"
    assert loaded.documents.qwen_model_id == "Qwen/Qwen3-TTS-VoiceDesign"
    assert loaded.checks.myinstants_commercial_rights_verified is True


def test_deserialization_is_tolerant_of_legacy_or_malformed_values() -> None:
    profile = LegalProfile.from_dict(
        {
            "profile_version": "not-a-number",
            "publisher": {"legal_name": 42, "unknown": "ignored"},
            "privacy": {
                "local_processing_only": "false",
                "voice_samples_retention_days": "invalid",
            },
            "checks": {"publisher_identity_verified": "true"},
        }
    )

    assert profile.profile_version == 1
    assert profile.publisher.legal_name == ""
    assert profile.privacy.local_processing_only is False
    assert profile.privacy.voice_samples_retention_days == 30
    assert profile.checks.publisher_identity_verified is True


def test_myinstants_rights_are_required_only_when_enabled() -> None:
    profile = _completed_profile()
    assert profile.commercial_readiness()[0] is True

    # The pre-filled default points at the project repository; simulate a
    # publisher without written rights to verify the gate still blocks.
    profile.myinstants_enabled = True
    profile.documents.myinstants_rights_reference = ""
    ready, reasons = profile.commercial_readiness()

    assert ready is False
    assert "Référence manquante : Droits commerciaux Myinstants" in reasons
