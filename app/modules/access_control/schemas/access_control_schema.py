from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)

from app.core.enums.role_enums import Role


class AccessControlRoleUpdateSchema(BaseModel):
    role: Role
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlStatusUpdateSchema(BaseModel):
    is_active: bool
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlUserResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )
    email: EmailStr
    role: Role
    is_active: bool
    clinic_id: int | None = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class AccessControlRoleChangeResponseSchema(BaseModel):
    user: AccessControlUserResponseSchema
    previous_role: Role
    new_role: Role
    reason: str | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlStatusChangeResponseSchema(BaseModel):
    user: AccessControlUserResponseSchema
    previous_status: bool
    new_status: bool
    reason: str | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlUserListQuerySchema(BaseModel):
    page: int = Field(
        default=1,
        ge=1,
    )
    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )
    role: Role | None = None
    is_active: bool | None = None

    model_config = ConfigDict(
        extra="forbid",
    )