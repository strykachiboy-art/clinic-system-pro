from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums.chat_enums import AttachmentType
from app.core.exceptions import ValidationError
from app.modules.chat.rule.rule_engine import (
    ChatRule,
    ChatRuleEngine,
)


# ============================================================================
# Defaults / Resolution
# ============================================================================


def test_resolve_uses_defaults_when_settings_do_not_exist(clinic):
    assert (
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.MAX_MESSAGE_LENGTH,
        )
        == 5000
    )

    assert (
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.MAX_GROUP_PARTICIPANTS,
        )
        == 50
    )

    assert (
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.MAX_ATTACHMENT_SIZE,
        )
        == 10 * 1024 * 1024
    )

    assert (
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.RETENTION_DAYS,
        )
        == 90
    )


def test_resolve_boolean_defaults(clinic):
    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.DIRECT_MESSAGING_ENABLED,
    ) is True

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.REACTIONS_ENABLED,
    ) is True

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.MENTIONS_ENABLED,
    ) is True

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.VOICE_MESSAGES_ENABLED,
    ) is True

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.CONVERSATION_CREATION_ENABLED,
    ) is True


def test_resolve_default_department_restrictions(clinic):
    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.DEPARTMENT_RESTRICTIONS,
    ) == {
        "enabled": False,
        "allowed_department_ids": [],
    }


def test_resolve_default_feature_availability(clinic):
    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.FEATURE_AVAILABILITY,
    ) == {}


def test_resolve_rejects_invalid_clinic_id():
    with pytest.raises(
        ValidationError,
        match="Clinic ID must be greater than zero",
    ):
        ChatRuleEngine.resolve(
            0,
            ChatRule.MAX_MESSAGE_LENGTH,
        )


def test_resolve_rejects_unknown_rule(clinic):
    with pytest.raises(
        ValidationError,
        match="Unknown chat rule",
    ):
        ChatRuleEngine.resolve(
            clinic.id,
            "unknown_rule",
        )


# ============================================================================
# Settings Overrides
# ============================================================================


def test_resolve_uses_operational_chat_settings(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_message_length": 2500,
                "max_group_participants": 25,
                "max_attachment_size": 5 * 1024 * 1024,
                "message_edit_window_seconds": 600,
                "message_delete_window_seconds": 700,
                "retention_days": 30,
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.MAX_MESSAGE_LENGTH,
    ) == 2500

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.MAX_GROUP_PARTICIPANTS,
    ) == 25

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.MAX_ATTACHMENT_SIZE,
    ) == 5 * 1024 * 1024

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.MESSAGE_EDIT_WINDOW,
    ) == 600

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.MESSAGE_DELETE_WINDOW,
    ) == 700

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.RETENTION_DAYS,
    ) == 30


def test_resolve_uses_security_chat_settings(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        security_preferences={
            "chat": {
                "department_restrictions": {
                    "enabled": True,
                    "allowed_department_ids": [1, 2],
                }
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.DEPARTMENT_RESTRICTIONS,
    ) == {
        "enabled": True,
        "allowed_department_ids": [1, 2],
    }


def test_resolve_uses_system_chat_settings(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": {
                    "voice": True,
                    "advanced_search": False,
                }
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.FEATURE_AVAILABILITY,
    ) == {
        "voice": True,
        "advanced_search": False,
    }


# ============================================================================
# Hard Limits
# ============================================================================


@pytest.mark.parametrize(
    ("rule", "configured_value", "expected"),
    [
        (
            ChatRule.MAX_MESSAGE_LENGTH,
            20_000,
            10_000,
        ),
        (
            ChatRule.MAX_GROUP_PARTICIPANTS,
            1_000,
            500,
        ),
        (
            ChatRule.MAX_ATTACHMENT_SIZE,
            50 * 1024 * 1024,
            25 * 1024 * 1024,
        ),
        (
            ChatRule.MESSAGE_EDIT_WINDOW,
            48 * 60 * 60,
            24 * 60 * 60,
        ),
        (
            ChatRule.MESSAGE_DELETE_WINDOW,
            48 * 60 * 60,
            24 * 60 * 60,
        ),
        (
            ChatRule.RETENTION_DAYS,
            5000,
            3650,
        ),
    ],
)
def test_hard_limits_cannot_be_exceeded(
    clinic,
    make_clinic_settings,
    rule,
    configured_value,
    expected,
):
    key_map = {
        ChatRule.MAX_MESSAGE_LENGTH: "max_message_length",
        ChatRule.MAX_GROUP_PARTICIPANTS: "max_group_participants",
        ChatRule.MAX_ATTACHMENT_SIZE: "max_attachment_size",
        ChatRule.MESSAGE_EDIT_WINDOW: "message_edit_window_seconds",
        ChatRule.MESSAGE_DELETE_WINDOW: "message_delete_window_seconds",
        ChatRule.RETENTION_DAYS: "retention_days",
    }

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                key_map[rule]: configured_value,
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        rule,
    ) == expected


def test_hard_limit_does_not_change_boolean_values():
    assert ChatRuleEngine._apply_hard_limit(
        ChatRule.DIRECT_MESSAGING_ENABLED,
        True,
    ) is True

    assert ChatRuleEngine._apply_hard_limit(
        ChatRule.DIRECT_MESSAGING_ENABLED,
        False,
    ) is False


# ============================================================================
# Attachment Types
# ============================================================================


def test_allowed_attachment_types_are_normalized(
    clinic,
    make_clinic_settings,
):
    attachment_type = next(iter(AttachmentType))

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "allowed_attachment_types": [
                    attachment_type.value,
                    attachment_type.value,
                ]
            }
        },
    )

    result = ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.ALLOWED_ATTACHMENT_TYPES,
    )

    assert result == [attachment_type.value]


def test_allowed_attachment_types_accept_enum_values(
    clinic,
    make_clinic_settings,
):
    attachment_type = next(iter(AttachmentType))

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "allowed_attachment_types": [
                    attachment_type,
                ]
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.ALLOWED_ATTACHMENT_TYPES,
    ) == [attachment_type.value]


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        "image",
        [123],
        ["invalid_attachment_type"],
        [],
    ],
)
def test_invalid_attachment_types_are_rejected(
    clinic,
    make_clinic_settings,
    value,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "allowed_attachment_types": value,
            }
        },
    )

    with pytest.raises(ValidationError):
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.ALLOWED_ATTACHMENT_TYPES,
        )


# ============================================================================
# Boolean Rule Validation
# ============================================================================


@pytest.mark.parametrize(
    "rule",
    [
        ChatRule.DIRECT_MESSAGING_ENABLED,
        ChatRule.REACTIONS_ENABLED,
        ChatRule.MENTIONS_ENABLED,
        ChatRule.VOICE_MESSAGES_ENABLED,
        ChatRule.CONVERSATION_CREATION_ENABLED,
    ],
)
def test_boolean_rules_reject_non_boolean_values(
    clinic,
    make_clinic_settings,
    rule,
):
    feature_flag = ChatRuleEngine.FEATURE_FLAGS[rule]

    make_clinic_settings(
        clinic,
        feature_flags={
            feature_flag: "false",
        },
    )

    with pytest.raises(ValidationError):
        ChatRuleEngine.resolve(
            clinic.id,
            rule,
        )


# ============================================================================
# Positive Integer Validation
# ============================================================================


@pytest.mark.parametrize(
    "rule",
    [
        ChatRule.MAX_MESSAGE_LENGTH,
        ChatRule.MAX_GROUP_PARTICIPANTS,
        ChatRule.MAX_ATTACHMENT_SIZE,
        ChatRule.MESSAGE_EDIT_WINDOW,
        ChatRule.MESSAGE_DELETE_WINDOW,
        ChatRule.RETENTION_DAYS,
    ],
)
@pytest.mark.parametrize("value", [0, -1, False, "100"])
def test_positive_integer_rules_reject_invalid_values(
    clinic,
    make_clinic_settings,
    rule,
    value,
):
    key = (
        ChatRuleEngine.OPERATIONAL_KEYS.get(rule)
        or ChatRuleEngine.FEATURE_FLAGS.get(rule)
    )

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                key: value,
            }
        },
    )

    with pytest.raises(ValidationError):
        ChatRuleEngine.resolve(
            clinic.id,
            rule,
        )


# ============================================================================
# Department Restrictions
# ============================================================================


def test_department_restrictions_remove_duplicate_ids(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        security_preferences={
            "chat": {
                "department_restrictions": {
                    "enabled": True,
                    "allowed_department_ids": [1, 2, 1, 2],
                }
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.DEPARTMENT_RESTRICTIONS,
    ) == {
        "enabled": True,
        "allowed_department_ids": [1, 2],
    }


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"enabled": "true"},
        {
            "enabled": True,
            "allowed_department_ids": [],
        },
        {
            "enabled": True,
            "allowed_department_ids": [0],
        },
        {
            "enabled": True,
            "allowed_department_ids": [-1],
        },
        {
            "enabled": True,
            "allowed_department_ids": [True],
        },
    ],
)
def test_invalid_department_restrictions_are_rejected(
    clinic,
    make_clinic_settings,
    value,
):
    make_clinic_settings(
        clinic,
        security_preferences={
            "chat": {
                "department_restrictions": value,
            }
        },
    )

    with pytest.raises(ValidationError):
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.DEPARTMENT_RESTRICTIONS,
        )


# ============================================================================
# Feature Availability
# ============================================================================


def test_feature_availability_accepts_boolean_mapping(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": {
                    "voice_messages": True,
                    "message_search": False,
                }
            }
        },
    )

    assert ChatRuleEngine.resolve(
        clinic.id,
        ChatRule.FEATURE_AVAILABILITY,
    ) == {
        "voice_messages": True,
        "message_search": False,
    }


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"": True},
        {"voice": "true"},
        {1: True},
    ],
)
def test_invalid_feature_availability_is_rejected(
    clinic,
    make_clinic_settings,
    value,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": value,
            }
        },
    )

    with pytest.raises(ValidationError):
        ChatRuleEngine.resolve(
            clinic.id,
            ChatRule.FEATURE_AVAILABILITY,
        )


# ============================================================================
# get_all_rules
# ============================================================================


def test_get_all_rules_returns_all_chat_rules(clinic):
    rules = ChatRuleEngine.get_all_rules(clinic.id)

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

    assert set(rules) == expected_rules


# ============================================================================
# Chat Availability
# ============================================================================


def test_chat_is_enabled_by_default(clinic):
    assert ChatRuleEngine.ensure_chat_enabled(clinic.id) is None


def test_disabled_clinic_chat_settings_are_rejected(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        is_enabled=False,
    )

    with pytest.raises(
        ValidationError,
        match="Chat settings are disabled for this clinic",
    ):
        ChatRuleEngine.ensure_chat_enabled(clinic.id)


def test_chat_feature_flag_can_disable_chat(
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
        ChatRuleEngine.ensure_chat_enabled(clinic.id)


def test_chat_feature_flag_must_be_boolean(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_enabled": "false",
        },
    )

    with pytest.raises(
        ValidationError,
        match="Feature flag 'chat_enabled' must be boolean",
    ):
        ChatRuleEngine.ensure_chat_enabled(clinic.id)


# ============================================================================
# Direct Messaging
# ============================================================================


def test_direct_messaging_is_allowed_by_default(clinic):
    assert (
        ChatRuleEngine.ensure_direct_messaging_allowed(
            clinic.id
        )
        is None
    )


def test_direct_messaging_can_be_disabled(
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
        ChatRuleEngine.ensure_direct_messaging_allowed(
            clinic.id
        )


# ============================================================================
# Group Size
# ============================================================================


def test_group_size_accepts_valid_count(clinic):
    assert (
        ChatRuleEngine.ensure_group_size_allowed(
            clinic.id,
            50,
        )
        is None
    )


def test_group_size_rejects_zero(clinic):
    with pytest.raises(
        ValidationError,
        match="Participant count must be a positive integer",
    ):
        ChatRuleEngine.ensure_group_size_allowed(
            clinic.id,
            0,
        )


def test_group_size_rejects_boolean(clinic):
    with pytest.raises(
        ValidationError,
        match="Participant count must be a positive integer",
    ):
        ChatRuleEngine.ensure_group_size_allowed(
            clinic.id,
            True,
        )


def test_group_size_rejects_excessive_count(clinic):
    with pytest.raises(
        ValidationError,
        match="Conversation cannot have more than 50 participants",
    ):
        ChatRuleEngine.ensure_group_size_allowed(
            clinic.id,
            51,
        )


def test_group_size_respects_clinic_limit(
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

    with pytest.raises(
        ValidationError,
        match="Conversation cannot have more than 10 participants",
    ):
        ChatRuleEngine.ensure_group_size_allowed(
            clinic.id,
            11,
        )


# ============================================================================
# Message Length
# ============================================================================


def test_message_length_accepts_valid_message(clinic):
    assert (
        ChatRuleEngine.ensure_message_length_allowed(
            clinic.id,
            "hello",
        )
        is None
    )


def test_message_length_rejects_non_string(clinic):
    with pytest.raises(
        ValidationError,
        match="Message content must be a string",
    ):
        ChatRuleEngine.ensure_message_length_allowed(
            clinic.id,
            123,
        )


def test_message_length_rejects_excessive_message(clinic):
    with pytest.raises(
        ValidationError,
        match="Message exceeds the maximum length of 5000 characters",
    ):
        ChatRuleEngine.ensure_message_length_allowed(
            clinic.id,
            "x" * 5001,
        )


def test_message_length_respects_clinic_limit(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "max_message_length": 100,
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Message exceeds the maximum length of 100 characters",
    ):
        ChatRuleEngine.ensure_message_length_allowed(
            clinic.id,
            "x" * 101,
        )


# ============================================================================
# Attachments
# ============================================================================


def test_attachment_is_allowed(
    clinic,
):
    attachment_type = next(iter(AttachmentType))

    assert (
        ChatRuleEngine.ensure_attachment_allowed(
            clinic.id,
            1024,
            attachment_type,
        )
        is None
    )


def test_attachment_accepts_string_type(
    clinic,
):
    attachment_type = next(iter(AttachmentType))

    assert (
        ChatRuleEngine.ensure_attachment_allowed(
            clinic.id,
            1024,
            attachment_type.value,
        )
        is None
    )


@pytest.mark.parametrize(
    "file_size",
    [-1, True, False, "100"],
)
def test_attachment_rejects_invalid_size(
    clinic,
    file_size,
):
    attachment_type = next(iter(AttachmentType))

    with pytest.raises(
        ValidationError,
        match="Attachment size must be a non-negative integer",
    ):
        ChatRuleEngine.ensure_attachment_allowed(
            clinic.id,
            file_size,
            attachment_type,
        )


def test_attachment_rejects_invalid_type(
    clinic,
):
    with pytest.raises(
        ValidationError,
        match="Attachment type must be a string",
    ):
        ChatRuleEngine.ensure_attachment_allowed(
            clinic.id,
            1024,
            123,
        )


def test_attachment_rejects_disallowed_type(
    clinic,
    make_clinic_settings,
):
    attachment_types = list(AttachmentType)

    if len(attachment_types) < 2:
        pytest.skip("AttachmentType requires at least two values")

    allowed = attachment_types[0]
    disallowed = attachment_types[1]

    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "allowed_attachment_types": [
                    allowed.value,
                ]
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Attachment type",
    ):
        ChatRuleEngine.ensure_attachment_allowed(
            clinic.id,
            1024,
            disallowed,
        )


def test_attachment_rejects_excessive_size(
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

    with pytest.raises(
        ValidationError,
        match="Attachment exceeds the maximum size of 1024 bytes",
    ):
        ChatRuleEngine.ensure_attachment_allowed(
            clinic.id,
            1025,
            attachment_type,
        )


# ============================================================================
# Reactions / Mentions / Voice / Conversation Creation
# ============================================================================


@pytest.mark.parametrize(
    (
        "method_name",
        "feature_flag",
        "expected_message",
    ),
    [
        (
            "ensure_reactions_allowed",
            "chat_reactions_enabled",
            "Message reactions are disabled",
        ),
        (
            "ensure_mentions_allowed",
            "chat_mentions_enabled",
            "Message mentions are disabled",
        ),
        (
            "ensure_voice_messages_allowed",
            "chat_voice_messages_enabled",
            "Voice messages are disabled",
        ),
        (
            "ensure_conversation_creation_allowed",
            "chat_conversation_creation_enabled",
            "Conversation creation is disabled",
        ),
    ],
)
def test_chat_feature_controls(
    clinic,
    make_clinic_settings,
    method_name,
    feature_flag,
    expected_message,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            feature_flag: False,
        },
    )

    method = getattr(ChatRuleEngine, method_name)

    with pytest.raises(
        ValidationError,
        match=expected_message,
    ):
        method(clinic.id)


# ============================================================================
# Department Restrictions
# ============================================================================


def test_department_is_allowed_when_restrictions_disabled(
    clinic,
):
    assert (
        ChatRuleEngine.ensure_department_allowed(
            clinic.id,
            None,
        )
        is None
    )


def test_department_is_required_when_restrictions_enabled(
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
        match="A department is required",
    ):
        ChatRuleEngine.ensure_department_allowed(
            clinic.id,
            None,
        )


def test_department_id_must_be_positive_integer(
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
        match="Department ID must be a positive integer",
    ):
        ChatRuleEngine.ensure_department_allowed(
            clinic.id,
            True,
        )


def test_department_must_be_allowed(
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
        match="This department is not permitted",
    ):
        ChatRuleEngine.ensure_department_allowed(
            clinic.id,
            20,
        )


def test_allowed_department_passes(
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

    assert (
        ChatRuleEngine.ensure_department_allowed(
            clinic.id,
            10,
        )
        is None
    )


# ============================================================================
# Feature Availability
# ============================================================================


def test_available_feature_passes(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": {
                    "voice": True,
                }
            }
        },
    )

    assert (
        ChatRuleEngine.ensure_feature_available(
            clinic.id,
            "voice",
        )
        is None
    )


def test_unavailable_feature_is_rejected(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        system_preferences={
            "chat": {
                "feature_availability": {
                    "voice": False,
                }
            }
        },
    )

    with pytest.raises(
        ValidationError,
        match="Chat feature 'voice' is unavailable",
    ):
        ChatRuleEngine.ensure_feature_available(
            clinic.id,
            "voice",
        )


@pytest.mark.parametrize(
    "feature",
    ["", "   ", None, 123],
)
def test_feature_name_must_be_non_empty_string(
    clinic,
    feature,
):
    with pytest.raises(
        ValidationError,
        match="Feature name must be a non-empty string",
    ):
        ChatRuleEngine.ensure_feature_available(
            clinic.id,
            feature,
        )


# ============================================================================
# Message Editing
# ============================================================================


def test_message_edit_is_allowed_within_window(clinic):
    now = datetime.now(timezone.utc)

    created_at = now - timedelta(
        seconds=ChatRuleEngine.DEFAULTS[
            ChatRule.MESSAGE_EDIT_WINDOW
        ]
    )

    assert (
        ChatRuleEngine.ensure_message_edit_allowed(
            clinic.id,
            created_at,
            now=now,
        )
        is None
    )


def test_message_edit_is_rejected_after_window(clinic):
    now = datetime.now(timezone.utc)

    created_at = now - timedelta(
        seconds=ChatRuleEngine.DEFAULTS[
            ChatRule.MESSAGE_EDIT_WINDOW
        ]
        + 1
    )

    with pytest.raises(
        ValidationError,
        match="The message editing window has expired",
    ):
        ChatRuleEngine.ensure_message_edit_allowed(
            clinic.id,
            created_at,
            now=now,
        )


def test_message_edit_rejects_non_datetime(clinic):
    with pytest.raises(
        ValidationError,
        match="Message creation time must be a datetime",
    ):
        ChatRuleEngine.ensure_message_edit_allowed(
            clinic.id,
            "not-a-date",
        )


def test_message_edit_rejects_future_message(clinic):
    now = datetime.now(timezone.utc)

    with pytest.raises(
        ValidationError,
        match="Message creation time cannot be in the future",
    ):
        ChatRuleEngine.ensure_message_edit_allowed(
            clinic.id,
            now + timedelta(seconds=1),
            now=now,
        )


def test_message_edit_accepts_naive_datetime(clinic):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    created_at = now - timedelta(seconds=60)

    assert (
        ChatRuleEngine.ensure_message_edit_allowed(
            clinic.id,
            created_at,
            now=now,
        )
        is None
    )


# ============================================================================
# Message Deletion
# ============================================================================


def test_message_delete_is_allowed_within_window(clinic):
    now = datetime.now(timezone.utc)

    created_at = now - timedelta(
        seconds=ChatRuleEngine.DEFAULTS[
            ChatRule.MESSAGE_DELETE_WINDOW
        ]
    )

    assert (
        ChatRuleEngine.ensure_message_delete_allowed(
            clinic.id,
            created_at,
            now=now,
        )
        is None
    )


def test_message_delete_is_rejected_after_window(clinic):
    now = datetime.now(timezone.utc)

    created_at = now - timedelta(
        seconds=ChatRuleEngine.DEFAULTS[
            ChatRule.MESSAGE_DELETE_WINDOW
        ]
        + 1
    )

    with pytest.raises(
        ValidationError,
        match="The message deletion window has expired",
    ):
        ChatRuleEngine.ensure_message_delete_allowed(
            clinic.id,
            created_at,
            now=now,
        )


def test_message_delete_rejects_non_datetime(clinic):
    with pytest.raises(
        ValidationError,
        match="Message creation time must be a datetime",
    ):
        ChatRuleEngine.ensure_message_delete_allowed(
            clinic.id,
            "not-a-date",
        )


def test_message_delete_rejects_future_message(clinic):
    now = datetime.now(timezone.utc)

    with pytest.raises(
        ValidationError,
        match="Message creation time cannot be in the future",
    ):
        ChatRuleEngine.ensure_message_delete_allowed(
            clinic.id,
            now + timedelta(seconds=1),
            now=now,
        )


# ============================================================================
# Retention
# ============================================================================


def test_retention_cutoff_uses_default_retention(clinic):
    now = datetime.now(timezone.utc)

    cutoff = ChatRuleEngine.get_retention_cutoff(
        clinic.id,
        now=now,
    )

    expected = now - timedelta(days=90)

    assert cutoff == expected


def test_retention_cutoff_uses_clinic_setting(
    clinic,
    make_clinic_settings,
):
    make_clinic_settings(
        clinic,
        operational_preferences={
            "chat": {
                "retention_days": 30,
            }
        },
    )

    now = datetime.now(timezone.utc)

    cutoff = ChatRuleEngine.get_retention_cutoff(
        clinic.id,
        now=now,
    )

    assert cutoff == now - timedelta(days=30)


def test_retention_cutoff_accepts_naive_datetime(clinic):
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    cutoff = ChatRuleEngine.get_retention_cutoff(
        clinic.id,
        now=now,
    )

    assert cutoff == now.replace(
        tzinfo=timezone.utc
    ) - timedelta(days=90)


# ============================================================================
# Cross-Rule Chat Enforcement
# ============================================================================


@pytest.mark.parametrize(
    "method_name",
    [
        "ensure_direct_messaging_allowed",
        "ensure_reactions_allowed",
        "ensure_mentions_allowed",
        "ensure_voice_messages_allowed",
        "ensure_conversation_creation_allowed",
    ],
)
def test_chat_feature_methods_require_chat_enabled(
    clinic,
    make_clinic_settings,
    method_name,
):
    make_clinic_settings(
        clinic,
        feature_flags={
            "chat_enabled": False,
        },
    )

    method = getattr(ChatRuleEngine, method_name)

    with pytest.raises(
        ValidationError,
        match="Chat is disabled for this clinic",
    ):
        method(clinic.id)