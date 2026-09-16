from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums.clinic_enums import ClinicStatus, ClinicType
from app.core.enums.staff_enums import StaffStatus


# ============================================================================
# MY / AUTHENTICATED USER PROFILE
# ============================================================================


class ProfileUserSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    email: str | None = Field(
        None,
        max_length=255,
    )

    is_active: bool

    clinic_id: int | None = Field(
        None,
        gt=0,
    )

    profile_image_storage_key: str | None = Field(
        None,
        max_length=500,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# PUBLIC / OTHER USER PROFILE
# ============================================================================


class PublicProfileUserSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    profile_image_url: str | None = Field(
        None,
        max_length=2000,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

# ============================================================================
# PROFILE IMAGE RESPONSES
# ============================================================================


class ProfileImageUploadResponseSchema(BaseModel):
    profile_image_storage_key: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class ProfileImageRemoveResponseSchema(BaseModel):
    profile_image_storage_key: None = None

    model_config = ConfigDict(
        extra="forbid",
    )


# ============================================================================
# STAFF PROFILE
# ============================================================================


class ProfileStaffSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    user_id: int | None = Field(
        None,
        gt=0,
    )

    first_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    last_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    specialty: str | None = Field(
        None,
        max_length=255,
    )

    phone: str | None = Field(
        None,
        max_length=50,
    )

    email: str | None = Field(
        None,
        max_length=255,
    )

    status: StaffStatus

    hired_at: date | datetime | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# PUBLIC STAFF PROFILE
# ============================================================================


class PublicProfileStaffSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    user_id: int | None = Field(
        None,
        gt=0,
    )

    first_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    last_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    specialty: str | None = Field(
        None,
        max_length=255,
    )

    status: StaffStatus

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# CLINIC PROFILE
# ============================================================================


class ProfileClinicSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    clinic_type: ClinicType

    status: ClinicStatus

    parent_clinic_id: int | None = Field(
        None,
        gt=0,
    )

    is_headquarters: bool

    address: str | None = Field(
        None,
        max_length=500,
    )

    city: str | None = Field(
        None,
        max_length=100,
    )

    country: str | None = Field(
        None,
        max_length=100,
    )

    phone: str | None = Field(
        None,
        max_length=50,
    )

    email: str | None = Field(
        None,
        max_length=255,
    )

    timezone: str | None = Field(
        None,
        max_length=100,
    )

    opening_time: time | None = None

    closing_time: time | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# MY / AUTHENTICATED PROFILE RESPONSE
# ============================================================================


class ProfileResponseSchema(BaseModel):
    user: ProfileUserSchema

    staff: ProfileStaffSchema | None = None

    clinic: ProfileClinicSchema | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# PUBLIC / OTHER USER PROFILE RESPONSE
# ============================================================================


class PublicProfileResponseSchema(BaseModel):
    user: PublicProfileUserSchema

    staff: PublicProfileStaffSchema | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


# ============================================================================
# PROFILE UPDATE
# ============================================================================


class ProfileUpdateSchema(BaseModel):
    """
    Fields that may be updated through the authenticated
    profile endpoint.

    Profile images are intentionally excluded.
    Image upload/removal uses dedicated authenticated
    operations.
    """

    first_name: str | None = Field(
        None,
        min_length=1,
        max_length=150,
    )

    last_name: str | None = Field(
        None,
        min_length=1,
        max_length=150,
    )

    phone: str | None = Field(
        None,
        max_length=50,
    )

    email: str | None = Field(
        None,
        max_length=255,
    )

    specialty: str | None = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator(
        "first_name",
        "last_name",
        "phone",
        "email",
        "specialty",
        mode="after",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Value cannot be blank"
            )

        return value