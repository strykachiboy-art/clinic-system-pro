from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)

from app.core.enums.audit_enums import AuditAction


class AuditLogCreateSchema(BaseModel):
    action: AuditAction = Field(
        ...,
        description="The type of audit action performed",
    )

    entity_type: StrictStr = Field(
        ...,
        min_length=1,
        max_length=80,
        description="The model or entity being acted upon",
    )

    entity_id: StrictInt = Field(
        ...,
        gt=0,
        description="Primary key ID of the entity",
    )

    description: StrictStr | None = Field(
        default=None,
        max_length=255,
        description="Human-readable description of the action",
    )

    old_value: dict[str, Any] | None = Field(
        default=None,
        description="JSON dictionary of old values before the change",
    )

    new_value: dict[str, Any] | None = Field(
        default=None,
        description="JSON dictionary of new values after the change",
    )

    ip_address: StrictStr | None = Field(
        default=None,
        max_length=45,
        description="IP address associated with the action",
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "entity_type",
        "description",
        "ip_address",
    )
    @classmethod
    def normalize_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Value cannot be empty"
            )

        return value