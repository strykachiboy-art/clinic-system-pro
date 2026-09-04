from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.audit_enums import AuditAction


class AuditLogCreateSchema(BaseModel):
    action: AuditAction = Field(
        ...,
        description="The type of audit action performed",
    )

    entity_type: str = Field(
        ...,
        max_length=80,
        description="The model or entity being acted upon",
    )

    entity_id: int = Field(
        ...,
        gt=0,
        description="Primary key ID of the entity",
    )

    description: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Human-readable description of the action",
    )

    old_value: Optional[dict[str, Any]] = Field(
        default=None,
        description="JSON dictionary of old values before the change",
    )

    new_value: Optional[dict[str, Any]] = Field(
        default=None,
        description="JSON dictionary of new values after the change",
    )

    ip_address: Optional[str] = Field(
        default=None,
        max_length=45,
        description="IP address associated with the action",
    )

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponseSchema(AuditLogCreateSchema):
    id: int
    user_id: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)