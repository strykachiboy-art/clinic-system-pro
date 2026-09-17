from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums.chat_enums import MentionType


class MessageMentionCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    mention_type: MentionType

    mentioned_user_id: int | None = Field(
        default=None,
        gt=0,
    )

    mentioned_patient_id: int | None = Field(
        default=None,
        gt=0,
    )

    mentioned_conversation_id: int | None = Field(
        default=None,
        gt=0,
    )

    position_start: int | None = Field(
        default=None,
        ge=0,
    )

    position_end: int | None = Field(
        default=None,
        ge=0,
    )

    @model_validator(mode="after")
    def validate_target(self):
        target_count = sum(
            value is not None
            for value in (
                self.mentioned_user_id,
                self.mentioned_patient_id,
                self.mentioned_conversation_id,
            )
        )

        if target_count != 1:
            raise ValueError(
                "Exactly one mention target must be provided."
            )

        if self.mention_type in {
            MentionType.USER,
            MentionType.STAFF,
        }:
            if self.mentioned_user_id is None:
                raise ValueError(
                    "User or staff mentions require mentioned_user_id."
                )

        elif self.mention_type == MentionType.PATIENT:
            if self.mentioned_patient_id is None:
                raise ValueError(
                    "Patient mentions require mentioned_patient_id."
                )

        elif self.mention_type == MentionType.GROUP:
            if self.mentioned_conversation_id is None:
                raise ValueError(
                    "Group mentions require mentioned_conversation_id."
                )

        if (
            self.position_start is not None
            and self.position_end is not None
            and self.position_end < self.position_start
        ):
            raise ValueError(
                "position_end must be greater than or equal to "
                "position_start."
            )

        return self


class MessageMentionResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    mention_type: MentionType
    mentioned_user_id: int | None
    mentioned_patient_id: int | None
    mentioned_conversation_id: int | None
    position_start: int | None
    position_end: int | None
    created_at: datetime