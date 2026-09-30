from datetime import date, datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
)

from app.core.enums.appointment_enums import AppointmentType


# ============================================================================
# Appointment Creation
# ============================================================================


class AppointmentCreateSchema(BaseModel):
    patient_id: StrictInt = Field(
        ...,
        gt=0,
        description="ID of the patient",
    )

    staff_id: StrictInt = Field(
        ...,
        gt=0,
        description="ID of the staff member",
    )

    scheduled_start: datetime = Field(
        ...,
        description="Start date and time of the appointment",
    )

    scheduled_end: datetime = Field(
        ...,
        description="End date and time of the appointment",
    )

    appointment_type: AppointmentType = Field(
        default=AppointmentType.IN_PERSON,
        description="Type of the appointment",
    )

    reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Reason for the visit",
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Additional notes",
    )

    @field_validator("reason", "notes")
    @classmethod
    def validate_optional_text(cls, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Value cannot be empty")

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ============================================================================
# Appointment Rescheduling
# ============================================================================


class AppointmentRescheduleSchema(BaseModel):
    scheduled_start: datetime = Field(
        ...,
        description="New start date and time",
    )

    scheduled_end: datetime = Field(
        ...,
        description="New end date and time",
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ============================================================================
# Appointment Cancellation
# ============================================================================


class AppointmentCancelSchema(BaseModel):
    cancellation_reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Reason for cancellation",
    )

    @field_validator("cancellation_reason")
    @classmethod
    def validate_cancellation_reason(cls, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Cancellation reason cannot be empty"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ============================================================================
# Appointment Completion
# ============================================================================


class AppointmentCompleteSchema(BaseModel):
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Consultation/visit notes to attach on completion",
    )

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value):
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Notes cannot be empty"
            )

        return value

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


# ============================================================================
# Staff Appointment Schedule Query
# ============================================================================


class AppointmentStaffScheduleQuerySchema(BaseModel):
    date_: Optional[date] = Field(
        default=None,
        alias="date",
        description="Filter staff schedule to a single day (YYYY-MM-DD)",
    )

    page: StrictInt = Field(
        default=1,
        gt=0,
        description="Page number",
    )

    per_page: StrictInt = Field(
        default=50,
        gt=0,
        le=500,
        description="Number of appointments per page",
    )

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )