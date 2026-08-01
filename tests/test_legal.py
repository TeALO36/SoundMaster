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


def test_new_profile_has_safe_technical_defaults_but_is_not_ready() -> None:
    profile = LegalProfile()
    assert profile.publisher.country == "France"
    assert profile.documents.qwen_model_id == "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    assert profile.documents.qwen_notice_reference == ""
    assert profile.documents.qwen_model_revision == ""
    assert profile.documents.qwen_model_sha256 == ""

    ready, reasons = profile.commercial_readiness()

    assert ready is False
    assert "Nom légal de l’éditeur manquant" in reasons
    assert "Identité de l’éditeur vérifiée" in reasons


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

    profile.myinstants_enabled = True
    ready, reasons = profile.commercial_readiness()

    assert ready is False
    assert "Référence manquante : Droits commerciaux Myinstants" in reasons
