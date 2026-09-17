from __future__ import annotations

import pytest

from app.extensions import db
from app.core.exceptions import ValidationError
from app.modules.chat.services.chat_content_validation_service import (
    ChatContentValidationService,
)
from app.modules.settings.models.clinic_settings import ClinicSettings


def _get_or_create_settings(clinic):
    settings = db.session.execute(
        db.select(ClinicSettings).where(
            ClinicSettings.clinic_id == clinic.id,
        )
    ).scalar_one_or_none()

    if settings is None:
        settings = ClinicSettings(
            clinic_id=clinic.id,
        )
        db.session.add(settings)
        db.session.flush()

    return settings


def _set_chat_security_preferences(
    clinic,
    **values,
):
    settings = _get_or_create_settings(clinic)

    current = dict(
        settings.security_preferences or {}
    )

    chat = dict(
        current.get("chat", {})
    )

    chat.update(values)
    current["chat"] = chat

    settings.security_preferences = current

    db.session.flush()

    return settings


def _set_chat_feature_flag(
    clinic,
    key,
    value,
):
    settings = _get_or_create_settings(clinic)

    current = dict(
        settings.feature_flags or {}
    )

    current[key] = value

    settings.feature_flags = current

    db.session.flush()

    return settings


def test_normalize_text_strips_whitespace(
    clinic,
):
    result = ChatContentValidationService.normalize_text(
        "   Hello clinical team   ",
    )

    assert result == "Hello clinical team"


def test_normalize_text_rejects_non_string(
    clinic,
):
    with pytest.raises(ValidationError):
        ChatContentValidationService.normalize_text(
            123,
        )


def test_normalize_text_rejects_empty_content(
    clinic,
):
    with pytest.raises(ValidationError):
        ChatContentValidationService.normalize_text(
            "   ",
        )


def test_normalize_text_rejects_content_over_hard_limit(
    clinic,
):
    with pytest.raises(ValidationError):
        ChatContentValidationService.normalize_text(
            "x" * 10001,
        )


def test_validate_text_allows_normal_content(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Please review the patient's blood results.",
    )

    assert result["allowed"] is True
    assert result["category"] is None
    assert result["reason"] is None
    assert (
        result["normalized_content"]
        == "Please review the patient's blood results."
    )


def test_validate_text_blocks_sexual_solicitation(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Send me your nudes",
    )

    assert result["allowed"] is False
    assert result["category"] == "sexual_solicitation"
    assert result["reason"] is not None


def test_validate_text_blocks_pornographic_content(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Send me the porn video",
    )

    assert result["allowed"] is False
    assert result["category"] == "pornographic_content"
    assert result["reason"] is not None


def test_hard_sexual_content_cannot_be_disabled(
    clinic,
):
    _set_chat_feature_flag(
        clinic,
        "chat_content_moderation_enabled",
        False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Send me your nudes",
    )

    assert result["allowed"] is False
    assert result["category"] == "sexual_solicitation"


def test_clinical_sensitive_content_is_allowed_by_default(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Patient reports vaginal bleeding.",
    )

    assert result["allowed"] is True
    assert result["category"] == "clinical_sensitive"
    assert (
        result["reason"]
        == "Clinical sensitive content allowed"
    )


def test_clinical_sensitive_content_with_medical_context_is_allowed(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Clinical examination found a penile lesion.",
    )

    assert result["allowed"] is True
    assert result["category"] == "clinical_sensitive"


def test_sensitive_clinical_content_can_be_disabled(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        clinical_sensitive_content_allowed=False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Patient reports vaginal bleeding.",
    )

    assert result["allowed"] is False
    assert result["category"] == "clinical_sensitive"


def test_profanity_is_disabled_by_default(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "This is fucking frustrating.",
    )

    assert result["allowed"] is True


def test_profanity_can_be_enabled(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        profanity_filter_enabled=True,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "This is fucking frustrating.",
    )

    assert result["allowed"] is False
    assert result["category"] == "profanity"


def test_abusive_content_is_blocked_by_default(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "I will kill you.",
    )

    assert result["allowed"] is False
    assert result["category"] == "abusive"


def test_abusive_content_can_be_disabled_by_clinic_policy(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        abusive_content_blocked=False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "I will kill you.",
    )

    assert result["allowed"] is True


def test_spam_content_is_blocked_by_default(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "hello hello hello hello hello",
    )

    assert result["allowed"] is False
    assert result["category"] == "spam"


def test_repeated_character_spam_is_blocked(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "aaaaaaaaaaaaaaaaaaaa",
    )

    assert result["allowed"] is False
    assert result["category"] == "spam"


def test_spam_can_be_disabled_by_clinic_policy(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        spam_content_blocked=False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "hello hello hello hello hello",
    )

    assert result["allowed"] is True


def test_external_links_are_allowed_by_default(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Please review https://example.com",
    )

    assert result["allowed"] is True


def test_external_links_can_be_blocked(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        external_links_allowed=False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Please review https://example.com",
    )

    assert result["allowed"] is False
    assert result["category"] == "external_link"


def test_moderation_can_be_disabled_for_configurable_categories(
    clinic,
):
    _set_chat_feature_flag(
        clinic,
        "chat_content_moderation_enabled",
        False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "This is fucking frustrating.",
    )

    assert result["allowed"] is True


def test_moderation_disabled_still_allows_normal_content(
    clinic,
):
    _set_chat_feature_flag(
        clinic,
        "chat_content_moderation_enabled",
        False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Please review the patient's medication list.",
    )

    assert result["allowed"] is True


def test_ensure_text_allowed_returns_normalized_content(
    clinic,
):
    result = ChatContentValidationService.ensure_text_allowed(
        clinic.id,
        "   Clinical update   ",
    )

    assert result == "Clinical update"


def test_ensure_text_allowed_rejects_blocked_content(
    clinic,
):
    with pytest.raises(ValidationError):
        ChatContentValidationService.ensure_text_allowed(
            clinic.id,
            "Send me your nudes",
        )


def test_is_text_allowed_returns_true(
    clinic,
):
    assert (
        ChatContentValidationService.is_text_allowed(
            clinic.id,
            "Patient is stable.",
        )
        is True
    )


def test_is_text_allowed_returns_false_for_blocked_content(
    clinic,
):
    assert (
        ChatContentValidationService.is_text_allowed(
            clinic.id,
            "Send me your nudes",
        )
        is False
    )


def test_invalid_clinic_id_is_rejected(
):
    with pytest.raises(ValidationError):
        ChatContentValidationService.validate_text(
            0,
            "Clinical message",
        )


def test_invalid_feature_flag_type_is_rejected(
    clinic,
):
    _set_chat_feature_flag(
        clinic,
        "chat_content_moderation_enabled",
        "true",
    )

    with pytest.raises(ValidationError):
        ChatContentValidationService.validate_text(
            clinic.id,
            "Clinical message",
        )


def test_invalid_security_preference_type_is_rejected(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        profanity_filter_enabled="true",
    )

    with pytest.raises(ValidationError):
        ChatContentValidationService.validate_text(
            clinic.id,
            "Clinical message",
        )


def test_invalid_security_preferences_container_is_rejected(
    clinic,
):
    settings = _get_or_create_settings(
        clinic,
    )

    settings.security_preferences = "invalid"
    db.session.flush()

    with pytest.raises(ValidationError):
        ChatContentValidationService.validate_text(
            clinic.id,
            "Clinical message",
        )


def test_invalid_feature_flags_container_is_rejected(
    clinic,
):
    settings = _get_or_create_settings(
        clinic,
    )

    settings.feature_flags = "invalid"
    db.session.flush()

    with pytest.raises(ValidationError):
        ChatContentValidationService.validate_text(
            clinic.id,
            "Clinical message",
        )


def test_content_policy_is_clinic_scoped(
    clinic,
    make_clinic,
):
    other_clinic = make_clinic()

    _set_chat_security_preferences(
        clinic,
        profanity_filter_enabled=True,
    )

    clinic_result = (
        ChatContentValidationService.validate_text(
            clinic.id,
            "This is fucking frustrating.",
        )
    )

    other_clinic_result = (
        ChatContentValidationService.validate_text(
            other_clinic.id,
            "This is fucking frustrating.",
        )
    )

    assert clinic_result["allowed"] is False
    assert clinic_result["category"] == "profanity"

    assert other_clinic_result["allowed"] is True


def test_clinical_sensitive_content_is_not_equivalent_to_explicit_content(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Patient has a sexual health history and requires clinical examination.",
    )

    assert result["allowed"] is True
    assert result["category"] == "clinical_sensitive"


def test_sexual_solicitation_with_clinical_word_does_not_bypass_hard_rule(
    clinic,
):
    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Clinical team, send me your nudes.",
    )

    assert result["allowed"] is False
    assert result["category"] == "sexual_solicitation"


def test_hard_explicit_rule_has_precedence_over_moderation_settings(
    clinic,
):
    _set_chat_security_preferences(
        clinic,
        profanity_filter_enabled=False,
        abusive_content_blocked=False,
        spam_content_blocked=False,
        external_links_allowed=True,
        clinical_sensitive_content_allowed=True,
    )

    _set_chat_feature_flag(
        clinic,
        "chat_content_moderation_enabled",
        False,
    )

    result = ChatContentValidationService.validate_text(
        clinic.id,
        "Send me your nudes",
    )

    assert result["allowed"] is False
    assert result["category"] == "sexual_solicitation"