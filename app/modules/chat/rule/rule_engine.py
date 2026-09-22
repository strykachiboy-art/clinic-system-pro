from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from sqlalchemy import text

from app.extensions import db
from app.core.enums.chat_enums import AttachmentType
from app.core.exceptions import ValidationError
from app.modules.settings.models.clinic_settings import ClinicSettings


def _utcnow():
    return datetime.now(timezone.utc)


class ChatRule:
    MAX_MESSAGE_LENGTH = "max_message_length"
    MAX_GROUP_PARTICIPANTS = "max_group_participants"
    MAX_ATTACHMENT_SIZE = "max_attachment_size"
    ALLOWED_ATTACHMENT_TYPES = "allowed_attachment_types"
    DIRECT_MESSAGING_ENABLED = "direct_messaging_enabled"
    MESSAGE_EDIT_WINDOW = "message_edit_window"
    MESSAGE_DELETE_WINDOW = "message_delete_window"
    RETENTION_DAYS = "retention_days"
    REACTIONS_ENABLED = "reactions_enabled"
    MENTIONS_ENABLED = "mentions_enabled"
    VOICE_MESSAGES_ENABLED = "voice_messages_enabled"
    CONVERSATION_CREATION_ENABLED = "conversation_creation_enabled"
    DEPARTMENT_RESTRICTIONS = "department_restrictions"
    FEATURE_AVAILABILITY = "feature_availability"


class ChatRuleEngine:
    _MISSING = object()
    _SETTINGS_UNSET = object()

    DEFAULTS: dict[str, Any] = {
        ChatRule.MAX_MESSAGE_LENGTH: 5000,
        ChatRule.MAX_GROUP_PARTICIPANTS: 50,
        ChatRule.MAX_ATTACHMENT_SIZE: 10 * 1024 * 1024,
        ChatRule.ALLOWED_ATTACHMENT_TYPES: [
            member.value for member in AttachmentType
        ],
        ChatRule.DIRECT_MESSAGING_ENABLED: True,
        ChatRule.MESSAGE_EDIT_WINDOW: 15 * 60,
        ChatRule.MESSAGE_DELETE_WINDOW: 15 * 60,
        ChatRule.RETENTION_DAYS: 90,
        ChatRule.REACTIONS_ENABLED: True,
        ChatRule.MENTIONS_ENABLED: True,
        ChatRule.VOICE_MESSAGES_ENABLED: True,
        ChatRule.CONVERSATION_CREATION_ENABLED: True,
        ChatRule.DEPARTMENT_RESTRICTIONS: {
            "enabled": False,
            "allowed_department_ids": [],
        },
        ChatRule.FEATURE_AVAILABILITY: {},
    }

    HARD_LIMITS: dict[str, Any] = {
        ChatRule.MAX_MESSAGE_LENGTH: 10_000,
        ChatRule.MAX_GROUP_PARTICIPANTS: 500,
        ChatRule.MAX_ATTACHMENT_SIZE: 25 * 1024 * 1024,
        ChatRule.MESSAGE_EDIT_WINDOW: 24 * 60 * 60,
        ChatRule.MESSAGE_DELETE_WINDOW: 24 * 60 * 60,
        ChatRule.RETENTION_DAYS: 3650,
    }

    FEATURE_FLAGS: dict[str, str] = {
        ChatRule.DIRECT_MESSAGING_ENABLED: "direct_chat_enabled",
        ChatRule.REACTIONS_ENABLED: "chat_reactions_enabled",
        ChatRule.MENTIONS_ENABLED: "chat_mentions_enabled",
        ChatRule.VOICE_MESSAGES_ENABLED: "chat_voice_messages_enabled",
        ChatRule.CONVERSATION_CREATION_ENABLED: (
            "chat_conversation_creation_enabled"
        ),
    }

    OPERATIONAL_KEYS: dict[str, str] = {
        ChatRule.MAX_MESSAGE_LENGTH: "max_message_length",
        ChatRule.MAX_GROUP_PARTICIPANTS: "max_group_participants",
        ChatRule.MAX_ATTACHMENT_SIZE: "max_attachment_size",
        ChatRule.ALLOWED_ATTACHMENT_TYPES: "allowed_attachment_types",
        ChatRule.MESSAGE_EDIT_WINDOW: "message_edit_window_seconds",
        ChatRule.MESSAGE_DELETE_WINDOW: "message_delete_window_seconds",
        ChatRule.RETENTION_DAYS: "retention_days",
    }

    SECURITY_KEYS: dict[str, str] = {
        ChatRule.DEPARTMENT_RESTRICTIONS: "department_restrictions",
    }

    SYSTEM_KEYS: dict[str, str] = {
        ChatRule.FEATURE_AVAILABILITY: "feature_availability",
    }

    @classmethod
    def _get_settings(
        cls,
        clinic_id: int,
    ) -> ClinicSettings | None:
        if (
            isinstance(clinic_id, bool)
            or not isinstance(clinic_id, int)
            or clinic_id <= 0
        ):
            raise ValidationError(
                "Clinic ID must be greater than zero"
            )

        stmt = db.select(
            ClinicSettings
        ).where(
            ClinicSettings.clinic_id == clinic_id
        )

        return db.session.execute(
            stmt
        ).scalar_one_or_none()

    @classmethod
    def get_settings(
        cls,
        clinic_id: int,
    ) -> ClinicSettings | None:
        return cls._get_settings(
            clinic_id,
        )

    @classmethod
    def _get_chat_feature_flags(
        cls,
        settings: ClinicSettings | None,
    ) -> dict[str, Any]:
        if settings is None:
            return {}

        flags = settings.feature_flags

        if not isinstance(
            flags,
            dict,
        ):
            raise ValidationError(
                "Clinic feature flags must be a JSON object"
            )

        return flags

    @classmethod
    def _get_operational_preferences(
        cls,
        settings: ClinicSettings | None,
    ) -> dict[str, Any]:
        if settings is None:
            return {}

        preferences = settings.operational_preferences

        if not isinstance(
            preferences,
            dict,
        ):
            raise ValidationError(
                "Clinic operational preferences must be a JSON object"
            )

        return preferences

    @classmethod
    def _get_security_preferences(
        cls,
        settings: ClinicSettings | None,
    ) -> dict[str, Any]:
        if settings is None:
            return {}

        preferences = settings.security_preferences

        if not isinstance(
            preferences,
            dict,
        ):
            raise ValidationError(
                "Clinic security preferences must be a JSON object"
            )

        return preferences

    @classmethod
    def _get_system_preferences(
        cls,
        settings: ClinicSettings | None,
    ) -> dict[str, Any]:
        if settings is None:
            return {}

        preferences = settings.system_preferences

        if not isinstance(
            preferences,
            dict,
        ):
            raise ValidationError(
                "Clinic system preferences must be a JSON object"
            )

        return preferences

    @classmethod
    def _chat_settings(
        cls,
        settings: ClinicSettings | None,
        container: dict[str, Any],
        key: str,
    ) -> Any:
        chat_settings = container.get(
            "chat",
            {},
        )

        if not isinstance(
            chat_settings,
            dict,
        ):
            raise ValidationError(
                "Chat settings must be a JSON object"
            )

        if key not in chat_settings:
            return cls._MISSING

        return chat_settings[key]

    @classmethod
    def _feature_enabled(
        cls,
        settings: ClinicSettings | None,
        feature_name: str,
    ) -> bool:
        if settings is None:
            return True

        flags = cls._get_chat_feature_flags(
            settings
        )

        if feature_name not in flags:
            return True

        value = flags[feature_name]

        if not isinstance(
            value,
            bool,
        ):
            raise ValidationError(
                f"Feature flag '{feature_name}' must be boolean"
            )

        return value

    @classmethod
    def _validate_boolean(
        cls,
        rule: str,
        value: Any,
    ) -> bool:
        if not isinstance(
            value,
            bool,
        ):
            raise ValidationError(
                f"Chat rule '{rule}' must be boolean"
            )

        return value

    @classmethod
    def _validate_positive_integer(
        cls,
        rule: str,
        value: Any,
    ) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
        ):
            raise ValidationError(
                f"Chat rule '{rule}' must be an integer"
            )

        if value <= 0:
            raise ValidationError(
                f"Chat rule '{rule}' must be greater than zero"
            )

        return value

    @classmethod
    def _validate_non_negative_integer(
        cls,
        rule: str,
        value: Any,
    ) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
        ):
            raise ValidationError(
                f"Chat rule '{rule}' must be an integer"
            )

        if value < 0:
            raise ValidationError(
                f"Chat rule '{rule}' cannot be negative"
            )

        return value

    @classmethod
    def _validate_attachment_types(
        cls,
        value: Any,
    ) -> list[str]:
        if not isinstance(
            value,
            list,
        ):
            raise ValidationError(
                "Allowed attachment types must be a list"
            )

        valid_types = {
            member.value
            for member in AttachmentType
        }

        normalized: list[str] = []

        for item in value:
            if isinstance(
                item,
                Enum,
            ):
                item = item.value

            if not isinstance(
                item,
                str,
            ):
                raise ValidationError(
                    "Attachment types must contain strings"
                )

            if item not in valid_types:
                raise ValidationError(
                    f"Unsupported attachment type: {item}"
                )

            if item not in normalized:
                normalized.append(item)

        if not normalized:
            raise ValidationError(
                "At least one attachment type must be allowed"
            )

        return normalized

    @classmethod
    def _validate_department_restrictions(
        cls,
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(
            value,
            dict,
        ):
            raise ValidationError(
                "Department restrictions must be a JSON object"
            )

        enabled = value.get(
            "enabled",
            False,
        )

        allowed_ids = value.get(
            "allowed_department_ids",
            [],
        )

        if not isinstance(
            enabled,
            bool,
        ):
            raise ValidationError(
                "Department restriction 'enabled' must be boolean"
            )

        if not isinstance(
            allowed_ids,
            list,
        ):
            raise ValidationError(
                "allowed_department_ids must be a list"
            )

        normalized_ids: list[int] = []

        for department_id in allowed_ids:
            if (
                isinstance(department_id, bool)
                or not isinstance(department_id, int)
                or department_id <= 0
            ):
                raise ValidationError(
                    "Department IDs must be positive integers"
                )

            if department_id not in normalized_ids:
                normalized_ids.append(
                    department_id
                )

        if enabled and not normalized_ids:
            raise ValidationError(
                "At least one department must be allowed "
                "when department restrictions are enabled"
            )

        return {
            "enabled": enabled,
            "allowed_department_ids": normalized_ids,
        }

    @classmethod
    def _validate_feature_availability(
        cls,
        value: Any,
    ) -> dict[str, bool]:
        if not isinstance(
            value,
            dict,
        ):
            raise ValidationError(
                "Feature availability must be a JSON object"
            )

        result: dict[str, bool] = {}

        for feature, enabled in value.items():
            if (
                not isinstance(feature, str)
                or not feature.strip()
                or feature.strip().isdigit()
            ):
                raise ValidationError(
                    "Feature availability keys must be "
                    "non-empty non-numeric strings"
                )

            if not isinstance(
                enabled,
                bool,
            ):
                raise ValidationError(
                    f"Feature availability '{feature}' must be boolean"
                )

            result[feature] = enabled

        return result

    @classmethod
    def _resolve_raw_value(
        cls,
        rule: str,
        clinic_id: int,
    ) -> Any:
        settings = cls._get_settings(
            clinic_id
        )

        operational = cls._get_operational_preferences(
            settings
        )

        security = cls._get_security_preferences(
            settings
        )

        system = cls._get_system_preferences(
            settings
        )

        if rule in cls.OPERATIONAL_KEYS:
            value = cls._chat_settings(
                settings,
                operational,
                cls.OPERATIONAL_KEYS[rule],
            )

            if value is cls._MISSING:
                return cls.DEFAULTS[rule]

            return value

        if rule in cls.SECURITY_KEYS:
            value = cls._chat_settings(
                settings,
                security,
                cls.SECURITY_KEYS[rule],
            )

            if value is cls._MISSING:
                return cls.DEFAULTS[rule]

            return value

        if rule in cls.SYSTEM_KEYS:
            value = cls._chat_settings(
                settings,
                system,
                cls.SYSTEM_KEYS[rule],
            )

            if value is cls._MISSING:
                return cls.DEFAULTS[rule]

            return value

        if rule in cls.FEATURE_FLAGS:
            feature_flag = cls.FEATURE_FLAGS[rule]

            enabled = cls._feature_enabled(
                settings,
                feature_flag,
            )

            if not enabled:
                return False

            if settings is None:
                return cls.DEFAULTS[rule]

            flags = cls._get_chat_feature_flags(
                settings
            )

            if feature_flag in flags:
                return flags[feature_flag]

            value = cls._chat_settings(
                settings,
                operational,
                feature_flag,
            )

            if value is cls._MISSING:
                return cls.DEFAULTS[rule]

            return value

        raise ValidationError(
            f"Unknown chat rule: {rule}"
        )

    @classmethod
    def _apply_hard_limit(
        cls,
        rule: str,
        value: Any,
    ) -> Any:
        hard_limit = cls.HARD_LIMITS.get(
            rule
        )

        if hard_limit is None:
            return value

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            int,
        ):
            return min(
                value,
                hard_limit,
            )

        return value

    @classmethod
    def resolve(
        cls,
        clinic_id: int,
        rule: str,
    ) -> Any:
        value = cls._resolve_raw_value(
            rule,
            clinic_id,
        )

        if rule == ChatRule.MAX_MESSAGE_LENGTH:
            value = cls._validate_positive_integer(
                rule,
                value,
            )

        elif rule == ChatRule.MAX_GROUP_PARTICIPANTS:
            value = cls._validate_positive_integer(
                rule,
                value,
            )

        elif rule == ChatRule.MAX_ATTACHMENT_SIZE:
            value = cls._validate_positive_integer(
                rule,
                value,
            )

        elif rule == ChatRule.ALLOWED_ATTACHMENT_TYPES:
            value = cls._validate_attachment_types(
                value,
            )

        elif rule in {
            ChatRule.DIRECT_MESSAGING_ENABLED,
            ChatRule.REACTIONS_ENABLED,
            ChatRule.MENTIONS_ENABLED,
            ChatRule.VOICE_MESSAGES_ENABLED,
            ChatRule.CONVERSATION_CREATION_ENABLED,
        }:
            value = cls._validate_boolean(
                rule,
                value,
            )

        elif rule in {
            ChatRule.MESSAGE_EDIT_WINDOW,
            ChatRule.MESSAGE_DELETE_WINDOW,
            ChatRule.RETENTION_DAYS,
        }:
            value = cls._validate_positive_integer(
                rule,
                value,
            )

        elif rule == ChatRule.DEPARTMENT_RESTRICTIONS:
            value = cls._validate_department_restrictions(
                value,
            )

        elif rule == ChatRule.FEATURE_AVAILABILITY:
            value = cls._validate_feature_availability(
                value,
            )

        value = cls._apply_hard_limit(
            rule,
            value,
        )

        return value

    @classmethod
    def get_all_rules(
        cls,
        clinic_id: int,
    ) -> dict[str, Any]:
        return {
            rule: cls.resolve(
                clinic_id,
                rule,
            )
            for rule in (
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
            )
        }

    @classmethod
    def ensure_chat_enabled(
        cls,
        clinic_id: int,
        settings: ClinicSettings | None | object = _SETTINGS_UNSET,
    ) -> None:
        if settings is cls._SETTINGS_UNSET:
            settings = cls._get_settings(
                clinic_id
            )
        elif (
            settings is not None
            and settings.clinic_id != clinic_id
        ):
            raise ValidationError(
                "Clinic settings do not belong to the requested clinic"
            )

        if (
            settings is not None
            and not settings.is_enabled
        ):
            raise ValidationError(
                "Chat settings are disabled for this clinic"
            )

        flags = cls._get_chat_feature_flags(
            settings
        )

        chat_enabled = flags.get(
            "chat_enabled",
            True,
        )

        if not isinstance(
            chat_enabled,
            bool,
        ):
            raise ValidationError(
                "Feature flag 'chat_enabled' must be boolean"
            )

        if not chat_enabled:
            raise ValidationError(
                "Chat is disabled for this clinic"
            )

    @classmethod
    def ensure_direct_messaging_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        cls.ensure_chat_enabled(
            clinic_id
        )

        if not cls.resolve(
            clinic_id,
            ChatRule.DIRECT_MESSAGING_ENABLED,
        ):
            raise ValidationError(
                "Direct messaging is disabled"
            )

    @classmethod
    def ensure_group_size_allowed(
        cls,
        clinic_id: int,
        participant_count: int,
    ) -> None:
        if (
            isinstance(participant_count, bool)
            or not isinstance(participant_count, int)
            or participant_count <= 0
        ):
            raise ValidationError(
                "Participant count must be a positive integer"
            )

        maximum = cls.resolve(
            clinic_id,
            ChatRule.MAX_GROUP_PARTICIPANTS,
        )

        if participant_count > maximum:
            raise ValidationError(
                f"Conversation cannot have more than "
                f"{maximum} participants"
            )

    @classmethod
    def ensure_message_length_allowed(
        cls,
        clinic_id: int,
        message: str,
    ) -> None:
        if not isinstance(
            message,
            str,
        ):
            raise ValidationError(
                "Message content must be a string"
            )

        maximum = cls.resolve(
            clinic_id,
            ChatRule.MAX_MESSAGE_LENGTH,
        )

        if len(message) > maximum:
            raise ValidationError(
                f"Message exceeds the maximum length of "
                f"{maximum} characters"
            )

    @classmethod
    def ensure_attachment_allowed(
        cls,
        clinic_id: int,
        file_size_bytes: int,
        attachment_type: AttachmentType | str,
    ) -> None:
        if (
            isinstance(file_size_bytes, bool)
            or not isinstance(file_size_bytes, int)
            or file_size_bytes < 0
        ):
            raise ValidationError(
                "Attachment size must be a "
                "non-negative integer"
            )

        if isinstance(
            attachment_type,
            AttachmentType,
        ):
            attachment_type = attachment_type.value

        if not isinstance(
            attachment_type,
            str,
        ):
            raise ValidationError(
                "Attachment type must be a string"
            )

        allowed_types = cls.resolve(
            clinic_id,
            ChatRule.ALLOWED_ATTACHMENT_TYPES,
        )

        if attachment_type not in allowed_types:
            raise ValidationError(
                f"Attachment type '{attachment_type}' "
                f"is not allowed"
            )

        maximum_size = cls.resolve(
            clinic_id,
            ChatRule.MAX_ATTACHMENT_SIZE,
        )

        if file_size_bytes > maximum_size:
            raise ValidationError(
                f"Attachment exceeds the maximum size of "
                f"{maximum_size} bytes"
            )

    @classmethod
    def ensure_reactions_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        cls.ensure_chat_enabled(
            clinic_id
        )

        if not cls.resolve(
            clinic_id,
            ChatRule.REACTIONS_ENABLED,
        ):
            raise ValidationError(
                "Message reactions are disabled"
            )

    @classmethod
    def ensure_mentions_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        cls.ensure_chat_enabled(
            clinic_id
        )

        if not cls.resolve(
            clinic_id,
            ChatRule.MENTIONS_ENABLED,
        ):
            raise ValidationError(
                "Message mentions are disabled"
            )

    @classmethod
    def ensure_voice_messages_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        cls.ensure_chat_enabled(
            clinic_id
        )

        if not cls.resolve(
            clinic_id,
            ChatRule.VOICE_MESSAGES_ENABLED,
        ):
            raise ValidationError(
                "Voice messages are disabled"
            )

    @classmethod
    def ensure_conversation_creation_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        cls.ensure_chat_enabled(
            clinic_id
        )

        if not cls.resolve(
            clinic_id,
            ChatRule.CONVERSATION_CREATION_ENABLED,
        ):
            raise ValidationError(
                "Conversation creation is disabled"
            )

    @classmethod
    def ensure_department_allowed(
        cls,
        clinic_id: int,
        department_id: int | None,
    ) -> None:
        restrictions = cls.resolve(
            clinic_id,
            ChatRule.DEPARTMENT_RESTRICTIONS,
        )

        if not restrictions["enabled"]:
            return

        if department_id is None:
            raise ValidationError(
                "A department is required by the clinic "
                "chat policy"
            )

        if (
            isinstance(department_id, bool)
            or not isinstance(department_id, int)
            or department_id <= 0
        ):
            raise ValidationError(
                "Department ID must be a positive integer"
            )

        if (
            department_id
            not in restrictions["allowed_department_ids"]
        ):
            raise ValidationError(
                "This department is not permitted by the "
                "clinic chat policy"
            )

    @classmethod
    def ensure_feature_available(
        cls,
        clinic_id: int,
        feature: str,
    ) -> None:
        if (
            not isinstance(feature, str)
            or not feature.strip()
            or feature.strip().isdigit()
        ):
            raise ValidationError(
                "Feature name must be a non-empty string"
            )

        availability = cls.resolve(
            clinic_id,
            ChatRule.FEATURE_AVAILABILITY,
        )

        if (
            feature in availability
            and not availability[feature]
        ):
            raise ValidationError(
                f"Chat feature '{feature}' is unavailable"
            )

    @classmethod
    def ensure_message_edit_allowed(
        cls,
        clinic_id: int,
        created_at: datetime,
        now: datetime | None = None,
    ) -> None:
        if not isinstance(
            created_at,
            datetime,
        ):
            raise ValidationError(
                "Message creation time must be a datetime"
            )

        now = now or datetime.now(
            timezone.utc
        )

        if created_at.tzinfo is None:
            created_at = created_at.replace(
                tzinfo=timezone.utc
            )

        if now.tzinfo is None:
            now = now.replace(
                tzinfo=timezone.utc
            )

        if now < created_at:
            raise ValidationError(
                "Message creation time cannot be "
                "in the future"
            )

        window_seconds = cls.resolve(
            clinic_id,
            ChatRule.MESSAGE_EDIT_WINDOW,
        )

        if (
            now - created_at
            > timedelta(
                seconds=window_seconds
            )
        ):
            raise ValidationError(
                "The message editing window has expired"
            )

    @classmethod
    def ensure_message_delete_allowed(
        cls,
        clinic_id: int,
        created_at: datetime,
        now: datetime | None = None,
    ) -> None:
        if not isinstance(
            created_at,
            datetime,
        ):
            raise ValidationError(
                "Message creation time must be a datetime"
            )

        now = now or datetime.now(
            timezone.utc
        )

        if created_at.tzinfo is None:
            created_at = created_at.replace(
                tzinfo=timezone.utc
            )

        if now.tzinfo is None:
            now = now.replace(
                tzinfo=timezone.utc
            )

        if now < created_at:
            raise ValidationError(
                "Message creation time cannot be "
                "in the future"
            )

        window_seconds = cls.resolve(
            clinic_id,
            ChatRule.MESSAGE_DELETE_WINDOW,
        )

        if (
            now - created_at
            > timedelta(
                seconds=window_seconds
            )
        ):
            raise ValidationError(
                "The message deletion window has expired"
            )

    @classmethod
    def get_retention_cutoff(
        cls,
        clinic_id: int,
        now: datetime | None = None,
    ) -> datetime:
        now = now or datetime.now(
            timezone.utc
        )

        if now.tzinfo is None:
            now = now.replace(
                tzinfo=timezone.utc
            )

        retention_days = cls.resolve(
            clinic_id,
            ChatRule.RETENTION_DAYS,
        )

        return now - timedelta(
            days=retention_days
        )