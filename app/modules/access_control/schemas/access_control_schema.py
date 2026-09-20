from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    StrictInt,
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
    is_active: StrictBool
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlClinicTransferSchema(BaseModel):
    destination_clinic_id: StrictInt = Field(
        ...,
        gt=0,
    )
    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlUserResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )
    email: EmailStr
    role: Role
    is_active: StrictBool
    clinic_id: StrictInt | None = Field(
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
    previous_status: StrictBool
    new_status: StrictBool
    reason: str | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlClinicTransferResponseSchema(BaseModel):
    user: AccessControlUserResponseSchema
    previous_clinic_id: StrictInt | None = Field(
        default=None,
        gt=0,
    )
    new_clinic_id: StrictInt = Field(
        ...,
        gt=0,
    )
    reason: str | None = None

    model_config = ConfigDict(
        extra="forbid",
    )


class AccessControlUserListQuerySchema(BaseModel):
    page: StrictInt = Field(
        default=1,
        ge=1,
    )
    per_page: StrictInt = Field(
        default=50,
        ge=1,
        le=500,
    )
    role: Role | None = None
    is_active: StrictBool | None = None

    model_config = ConfigDict(
        extra="forbid",
    )