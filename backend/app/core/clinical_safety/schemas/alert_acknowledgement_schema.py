from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.core.enums.clinical_safety_enums import (
    AlertAcknowledgementType,
)


class AlertAcknowledgementCreateSchema(BaseModel):
    acknowledgement_type: AlertAcknowledgementType

    justification: str | None = Field(
        default=None,
        max_length=5000,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "justification",
        mode="before",
    )
    @classmethod
    def normalize_justification(
        cls,
        value,
    ):
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_acknowledgement_requirements(self):
        if (
            self.acknowledgement_type
            == AlertAcknowledgementType.OVERRIDDEN
            and not self.justification
        ):
            raise ValueError(
                "Justification is required when overriding a clinical alert"
            )

        return self


class AlertAcknowledgementResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    alert_id: StrictInt = Field(
        ...,
        gt=0,
    )

    acknowledged_by_user_id: StrictInt = Field(
        ...,
        gt=0,
    )

    acknowledgement_type: AlertAcknowledgementType

    justification: str | None

    acknowledged_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )