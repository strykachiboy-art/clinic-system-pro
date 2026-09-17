from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums.chat_enums import AttachmentType
from app.core.exceptions import ValidationError
from app.modules.chat.rule.rule_engine import ChatRule, ChatRuleEngine
from app.modules.chat.services.chat_policy_service import ChatPolicyService


def test_ensure_chat_enabled_passes_for_active_clinic(
    clinic,
):
    ChatPolicyService.ensure_chat_enabled(
        clinic.id,
    )


def test_ensure_chat_enabled_rejects_disabled_chat(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
    clinic,
    feature_flags={
        "chat_enabled": False,
     },
    
   )

    with pytest.raises(
        ValidationError,
        match="Chat is disabled for this clinic",
    ):
        ChatPolicyService.ensure_chat_enabled(
            clinic.id,
        )


def test_ensure_conversation_creation_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_conversation_creation_allowed(
        clinic.id,
    )


def test_ensure_conversation_creation_allowed_rejects_disabled_feature(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_conversation_creation_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Conversation creation is disabled",
    ):
        ChatPolicyService.ensure_conversation_creation_allowed(
            clinic.id,
        )


def test_ensure_direct_conversation_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_direct_conversation_allowed(
        clinic.id,
    )


def test_ensure_direct_conversation_allowed_rejects_disabled_direct_messaging(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "direct_chat_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Direct messaging is disabled",
    ):
        ChatPolicyService.ensure_direct_conversation_allowed(
            clinic.id,
        )


def test_ensure_direct_conversation_allowed_rejects_disabled_conversation_creation(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_conversation_creation_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Conversation creation is disabled",
    ):
        ChatPolicyService.ensure_direct_conversation_allowed(
            clinic.id,
        )


def test_ensure_group_conversation_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_group_conversation_allowed(
        clinic.id,
        5,
    )


def test_ensure_group_conversation_allowed_respects_configured_limit(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_group_participants": 10,
            }
        },
    )

    ChatPolicyService.ensure_group_conversation_allowed(
        clinic.id,
        10,
    )

    with pytest.raises(
        ValidationError,
        match="Conversation cannot have more than 10 participants",
    ):
        ChatPolicyService.ensure_group_conversation_allowed(
            clinic.id,
            11,
        )


def test_ensure_group_conversation_allowed_rejects_disabled_creation(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_conversation_creation_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Conversation creation is disabled",
    ):
        ChatPolicyService.ensure_group_conversation_allowed(
            clinic.id,
            5,
        )


def test_ensure_group_conversation_allowed_respects_hard_limit(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_group_participants": 1000,
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Conversation cannot have more than 500 participants",
    ):
        ChatPolicyService.ensure_group_conversation_allowed(
            clinic.id,
            501,
        )


def test_ensure_department_conversation_allowed_passes_without_restrictions(
    clinic,
):
    ChatPolicyService.ensure_department_conversation_allowed(
        clinic.id,
        None,
        5,
    )


def test_ensure_department_conversation_allowed_respects_department_policy(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        security_preferences={
            "chat": {
                "department_restrictions": {
                    "enabled": True,
                    "allowed_department_ids": [10, 20],
                }
            }
        },
    )

    ChatPolicyService.ensure_department_conversation_allowed(
        clinic.id,
        10,
        5,
    )

    with pytest.raises(
        ValidationError,
        match="This department is not permitted by the clinic chat policy",
    ):
        ChatPolicyService.ensure_department_conversation_allowed(
            clinic.id,
            30,
            5,
        )


def test_ensure_department_conversation_allowed_respects_group_limit(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        security_preferences={
            "chat": {
                "department_restrictions": {
                    "enabled": True,
                    "allowed_department_ids": [10],
                }
            }
        },
        operational_preferences={
            "chat": {
                "max_group_participants": 5,
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Conversation cannot have more than 5 participants",
    ):
        ChatPolicyService.ensure_department_conversation_allowed(
            clinic.id,
            10,
            6,
        )


def test_ensure_department_conversation_allowed_rejects_disabled_creation(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_conversation_creation_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Conversation creation is disabled",
    ):
        ChatPolicyService.ensure_department_conversation_allowed(
            clinic.id,
            10,
            5,
        )


def test_ensure_department_conversation_allowed_requires_department_when_restricted(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        security_preferences={
            "chat": {
                "department_restrictions": {
                    "enabled": True,
                    "allowed_department_ids": [10],
                }
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="A department is required by the clinic chat policy",
    ):
        ChatPolicyService.ensure_department_conversation_allowed(
            clinic.id,
            None,
            5,
        )


def test_ensure_message_content_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_message_content_allowed(
        clinic.id,
        "Hello clinical team",
    )


def test_ensure_message_content_allowed_respects_configured_limit(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_message_length": 10,
            }
        },
    )

    ChatPolicyService.ensure_message_content_allowed(
        clinic.id,
        "1234567890",
    )

    with pytest.raises(
        ValidationError,
        match="Message exceeds the maximum length of 10 characters",
    ):
        ChatPolicyService.ensure_message_content_allowed(
            clinic.id,
            "12345678901",
        )


def test_ensure_message_content_allowed_respects_hard_limit(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_message_length": 20_000,
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Message exceeds the maximum length of 10000 characters",
    ):
        ChatPolicyService.ensure_message_content_allowed(
            clinic.id,
            "x" * 10_001,
        )


def test_ensure_attachment_allowed_passes(
    clinic,
):
    attachment_type = next(iter(AttachmentType))

    ChatPolicyService.ensure_attachment_allowed(
        clinic.id,
        1024,
        attachment_type,
    )


def test_ensure_attachment_allowed_respects_size_limit(
    clinic,
    make_clinic_settings,
):
    attachment_type = next(iter(AttachmentType))

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_attachment_size": 1024,
            }
        },
    )

    ChatPolicyService.ensure_attachment_allowed(
        clinic.id,
        1024,
        attachment_type,
    )

    with pytest.raises(
        ValidationError,
        match="Attachment exceeds the maximum size of 1024 bytes",
    ):
        ChatPolicyService.ensure_attachment_allowed(
            clinic.id,
            1025,
            attachment_type,
        )


def test_ensure_attachment_allowed_respects_hard_size_limit(
    clinic,
    make_clinic_settings,
):
    attachment_type = next(iter(AttachmentType))

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_attachment_size": 50 * 1024 * 1024,
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Attachment exceeds the maximum size of 26214400 bytes",
    ):
        ChatPolicyService.ensure_attachment_allowed(
            clinic.id,
            25 * 1024 * 1024 + 1,
            attachment_type,
        )


def test_ensure_attachment_allowed_rejects_disallowed_type(
    clinic,
    make_clinic_settings,
):
    attachment_type = next(iter(AttachmentType))

    remaining_types = [
        member.value
        for member in AttachmentType
        if member.value != attachment_type.value
    ]

    if not remaining_types:
        pytest.skip("AttachmentType enum contains only one value")

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "allowed_attachment_types": remaining_types,
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="is not allowed",
    ):
        ChatPolicyService.ensure_attachment_allowed(
            clinic.id,
            1024,
            attachment_type,
        )


def test_ensure_reactions_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_reactions_allowed(
        clinic.id,
    )


def test_ensure_reactions_allowed_rejects_disabled_feature(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_reactions_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Message reactions are disabled",
    ):
        ChatPolicyService.ensure_reactions_allowed(
            clinic.id,
        )


def test_ensure_mentions_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_mentions_allowed(
        clinic.id,
    )


def test_ensure_mentions_allowed_rejects_disabled_feature(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_mentions_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Message mentions are disabled",
    ):
        ChatPolicyService.ensure_mentions_allowed(
            clinic.id,
        )


def test_ensure_voice_messages_allowed_passes(
    clinic,
):
    ChatPolicyService.ensure_voice_messages_allowed(
        clinic.id,
    )


def test_ensure_voice_messages_allowed_rejects_disabled_feature(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_voice_messages_enabled": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="Voice messages are disabled",
    ):
        ChatPolicyService.ensure_voice_messages_allowed(
            clinic.id,
        )


def test_ensure_feature_available_passes_for_enabled_feature(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": {
                    "rust_service_enabled": True,
                }
            }
        },
    )

    ChatPolicyService.ensure_feature_available(
        clinic.id,
        "rust_service_enabled",
    )


def test_ensure_feature_available_passes_for_unconfigured_feature(
    clinic,
):
    ChatPolicyService.ensure_feature_available(
        clinic.id,
        "some_future_chat_feature",
    )


def test_ensure_feature_available_rejects_disabled_feature(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": {
                    "rust_service_enabled": False,
                }
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Chat feature 'rust_service_enabled' is unavailable",
    ):
        ChatPolicyService.ensure_feature_available(
            clinic.id,
            "rust_service_enabled",
        )


@pytest.mark.parametrize(
    "feature",
    ["", "   ", None, 123],
)
def test_ensure_feature_available_rejects_invalid_feature_name(
    clinic,
    feature,
):
    with pytest.raises(
        ValidationError,
        match="Feature name must be a non-empty string",
    ):
        ChatPolicyService.ensure_feature_available(
            clinic.id,
            feature,
        )


def test_ensure_feature_available_rejects_numeric_feature_name(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Feature name must be a non-empty string",
    ):
        ChatPolicyService.ensure_feature_available(
            clinic.id,
            "123",
        )


def test_ensure_message_edit_allowed_passes_within_window(
    clinic,
    make_clinic_settings,
):
    now = datetime.now(timezone.utc)

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "message_edit_window_seconds": 600,
            }
        },
    )

    created_at = now - timedelta(seconds=599)

    ChatPolicyService.ensure_message_edit_allowed(
        clinic.id,
        created_at,
        now,
    )


def test_ensure_message_edit_allowed_rejects_expired_window(
    clinic,
    make_clinic_settings,
):
    now = datetime.now(timezone.utc)

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "message_edit_window_seconds": 600,
            }
        },
    )

    created_at = now - timedelta(seconds=601)

    with pytest.raises(
        ValidationError,
        match="The message editing window has expired",
    ):
        ChatPolicyService.ensure_message_edit_allowed(
            clinic.id,
            created_at,
            now,
        )


def test_ensure_message_delete_allowed_passes_within_window(
    clinic,
    make_clinic_settings,
):
    now = datetime.now(timezone.utc)

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "message_delete_window_seconds": 600,
            }
        },
    )

    created_at = now - timedelta(seconds=599)

    ChatPolicyService.ensure_message_delete_allowed(
        clinic.id,
        created_at,
        now,
    )


def test_ensure_message_delete_allowed_rejects_expired_window(
    clinic,
    make_clinic_settings,
):
    now = datetime.now(timezone.utc)

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "message_delete_window_seconds": 600,
            }
        },
    )

    created_at = now - timedelta(seconds=601)

    with pytest.raises(
        ValidationError,
        match="The message deletion window has expired",
    ):
        ChatPolicyService.ensure_message_delete_allowed(
            clinic.id,
            created_at,
            now,
        )


def test_get_retention_cutoff_uses_configured_retention(
    clinic,
    make_clinic_settings,
):
    now = datetime(
        2026,
        9,
        17,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "retention_days": 30,
            }
        },
    )

    cutoff = ChatPolicyService.get_retention_cutoff(
        clinic.id,
        now,
    )

    assert cutoff == now - timedelta(days=30)


def test_get_retention_cutoff_respects_hard_limit(
    clinic,
    make_clinic_settings,
):
    now = datetime(
        2026,
        9,
        17,
        12,
        0,
        0,
        tzinfo=timezone.utc,
    )

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "retention_days": 5000,
            }
        },
    )

    cutoff = ChatPolicyService.get_retention_cutoff(
        clinic.id,
        now,
    )

    assert cutoff == now - timedelta(days=3650)


def test_get_effective_policy_returns_all_rules(
    clinic,
):
    policy = ChatPolicyService.get_effective_policy(
        clinic.id,
    )

    expected_rules = {
        ChatRule.MAX_MESSAGE_LENGTH,
        ChatRule.MAX_GROUP_PARTICIPANTS,
        ChatRule.MAX_ATTACHMENT_SIZE,
        ChatRule.ALLOWED_ATTACHMENT_TYPES,
        ChatRule.DIRECT_MESSAGING_ENABLED,
        ChatRule.MESSAGE_EDIT_WINDOW,
        ChatRule.MESSAGE_DELETE_WINDOW,
        ChatRule.RETENTION_DAYS,
        ChatRule.REACTIONS_ENABLED,
        ChatRule.MENTIONS_ENABLED,
        ChatRule.VOICE_MESSAGES_ENABLED,
        ChatRule.CONVERSATION_CREATION_ENABLED,
        ChatRule.DEPARTMENT_RESTRICTIONS,
        ChatRule.FEATURE_AVAILABILITY,
    }

    assert set(policy) == expected_rules


def test_get_effective_policy_reflects_clinic_configuration(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "direct_chat_enabled": False,
            "chat_reactions_enabled": False,
        },
        operational_preferences={
            "chat": {
                "max_message_length": 1000,
                "max_group_participants": 25,
                "retention_days": 60,
            }
        },
    )

    policy = ChatPolicyService.get_effective_policy(
        clinic.id,
    )

    assert policy[ChatRule.MAX_MESSAGE_LENGTH] == 1000
    assert policy[ChatRule.MAX_GROUP_PARTICIPANTS] == 25
    assert policy[ChatRule.RETENTION_DAYS] == 60
    assert policy[ChatRule.DIRECT_MESSAGING_ENABLED] is False
    assert policy[ChatRule.REACTIONS_ENABLED] is False


def test_get_rule_returns_requested_rule(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_message_length": 1200,
            }
        },
    )

    value = ChatPolicyService.get_rule(
        clinic.id,
        ChatRule.MAX_MESSAGE_LENGTH,
    )

    assert value == 1200


@pytest.mark.parametrize(
    "rule",
    ["", "   ", None, 123],
)
def test_get_rule_rejects_invalid_rule_name(
    clinic,
    rule,
):
    with pytest.raises(
        ValidationError,
        match="Chat rule name must be a non-empty string",
    ):
        ChatPolicyService.get_rule(
            clinic.id,
            rule,
        )


def test_get_rule_rejects_unknown_rule(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Unknown chat rule",
    ):
        ChatPolicyService.get_rule(
            clinic.id,
            "unknown_chat_rule",
        )


def test_policy_service_uses_rule_engine_for_effective_policy(
    clinic,
    monkeypatch,
):
    expected = {
        "test_rule": True,
    }

    def fake_get_all_rules(clinic_id):
        assert clinic_id == clinic.id
        return expected

    monkeypatch.setattr(
        ChatRuleEngine,
        "get_all_rules",
        fake_get_all_rules,
    )

    result = ChatPolicyService.get_effective_policy(
        clinic.id,
    )

    assert result == expected


def test_policy_service_uses_rule_engine_for_get_rule(
    clinic,
    monkeypatch,
):
    def fake_resolve(clinic_id, rule):
        assert clinic_id == clinic.id
        assert rule == "test_rule"
        return "resolved"

    monkeypatch.setattr(
        ChatRuleEngine,
        "resolve",
        fake_resolve,
    )

    result = ChatPolicyService.get_rule(
        clinic.id,
        "test_rule",
    )

    assert result == "resolved"