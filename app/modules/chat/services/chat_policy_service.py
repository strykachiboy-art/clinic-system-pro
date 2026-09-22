from __future__ import annotations

from datetime import datetime
from typing import Any

from app.modules.chat.rule.rule_engine import (
    ChatRuleEngine,
)
from app.core.enums.chat_enums import AttachmentType
from app.core.exceptions import ValidationError
from app.modules.settings.models.clinic_settings import ClinicSettings


_SETTINGS_UNSET = object()


class ChatPolicyService:
    @classmethod
    def get_settings(
        cls,
        clinic_id: int,
    ) -> ClinicSettings | None:
        return ChatRuleEngine.get_settings(
            clinic_id,
        )

    @classmethod
    def ensure_chat_enabled(
        cls,
        clinic_id: int,
        settings: ClinicSettings | None | object = (
            _SETTINGS_UNSET
        ),
    ) -> None:
        if settings is _SETTINGS_UNSET:
            ChatRuleEngine.ensure_chat_enabled(
                clinic_id,
            )
            return

        ChatRuleEngine.ensure_chat_enabled(
            clinic_id,
            settings=settings,
        )

    @classmethod
    def ensure_conversation_creation_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        ChatRuleEngine.ensure_conversation_creation_allowed(
            clinic_id,
        )

    @classmethod
    def ensure_direct_conversation_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        ChatRuleEngine.ensure_direct_messaging_allowed(
            clinic_id,
        )
        ChatRuleEngine.ensure_conversation_creation_allowed(
            clinic_id,
        )

    @classmethod
    def ensure_group_conversation_allowed(
        cls,
        clinic_id: int,
        participant_count: int,
    ) -> None:
        ChatRuleEngine.ensure_conversation_creation_allowed(
            clinic_id,
        )
        ChatRuleEngine.ensure_group_size_allowed(
            clinic_id,
            participant_count,
        )

    @classmethod
    def ensure_department_conversation_allowed(
        cls,
        clinic_id: int,
        department_id: int | None,
        participant_count: int,
    ) -> None:
        ChatRuleEngine.ensure_conversation_creation_allowed(
            clinic_id,
        )
        ChatRuleEngine.ensure_department_allowed(
            clinic_id,
            department_id,
        )
        ChatRuleEngine.ensure_group_size_allowed(
            clinic_id,
            participant_count,
        )

    @classmethod
    def ensure_message_content_allowed(
        cls,
        clinic_id: int,
        message: str,
    ) -> None:
        ChatRuleEngine.ensure_message_length_allowed(
            clinic_id,
            message,
        )

    @classmethod
    def ensure_attachment_allowed(
        cls,
        clinic_id: int,
        file_size_bytes: int,
        attachment_type: AttachmentType | str,
    ) -> None:
        ChatRuleEngine.ensure_attachment_allowed(
            clinic_id,
            file_size_bytes,
            attachment_type,
        )

    @classmethod
    def ensure_reactions_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        ChatRuleEngine.ensure_reactions_allowed(
            clinic_id,
        )

    @classmethod
    def ensure_mentions_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        ChatRuleEngine.ensure_mentions_allowed(
            clinic_id,
        )

    @classmethod
    def ensure_voice_messages_allowed(
        cls,
        clinic_id: int,
    ) -> None:
        ChatRuleEngine.ensure_voice_messages_allowed(
            clinic_id,
        )

    @classmethod
    def ensure_feature_available(
        cls,
        clinic_id: int,
        feature: str,
    ) -> None:
        ChatRuleEngine.ensure_feature_available(
            clinic_id,
            feature,
        )

    @classmethod
    def ensure_message_edit_allowed(
        cls,
        clinic_id: int,
        created_at: datetime,
        now: datetime | None = None,
    ) -> None:
        ChatRuleEngine.ensure_message_edit_allowed(
            clinic_id,
            created_at,
            now,
        )

    @classmethod
    def ensure_message_delete_allowed(
        cls,
        clinic_id: int,
        created_at: datetime,
        now: datetime | None = None,
    ) -> None:
        ChatRuleEngine.ensure_message_delete_allowed(
            clinic_id,
            created_at,
            now,
        )

    @classmethod
    def get_retention_cutoff(
        cls,
        clinic_id: int,
        now: datetime | None = None,
    ) -> datetime:
        return ChatRuleEngine.get_retention_cutoff(
            clinic_id,
            now,
        )

    @classmethod
    def get_effective_policy(
        cls,
        clinic_id: int,
    ) -> dict[str, Any]:
        return ChatRuleEngine.get_all_rules(
            clinic_id,
        )

    @classmethod
    def get_rule(
        cls,
        clinic_id: int,
        rule: str,
    ) -> Any:
        if (
            not isinstance(rule, str)
            or not rule.strip()
        ):
            raise ValidationError(
                "Chat rule name must be a non-empty string"
            )

        return ChatRuleEngine.resolve(
            clinic_id,
            rule,
        )