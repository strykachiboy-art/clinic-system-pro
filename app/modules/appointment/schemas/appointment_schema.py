from datetime import date, datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.enums.appointment_enums import AppointmentType


# ============================================================================
# Appointment Creation
# ============================================================================


class AppointmentCreateSchema(BaseModel):
    """
    Request schema for creating an appointment.

    clinic_id is intentionally excluded.

    The clinic is derived from the authenticated user's
    clinic assignment by the route layer.
    """

    patient_id: int = Field(
        ...,
        gt=0,
        description="ID of the patient",
    )

    staff_id: int = Field(
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
        description="Additional notes",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Appointment Rescheduling
# ============================================================================


class AppointmentRescheduleSchema(BaseModel):
    """
    Request schema for rescheduling an appointment.
    """

    scheduled_start: datetime = Field(
        ...,
        description="New start date and time",
    )

    scheduled_end: datetime = Field(
        ...,
        description="New end date and time",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Appointment Cancellation
# ============================================================================


class AppointmentCancelSchema(BaseModel):
    """
    Request schema for cancelling an appointment.
    """

    cancellation_reason: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Reason for cancellation",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Appointment Completion
# ============================================================================


class AppointmentCompleteSchema(BaseModel):
    """
    Request schema for completing an appointment.
    """

    notes: Optional[str] = Field(
        default=None,
        description="Consultation/visit notes to attach on completion",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Staff Appointment Schedule Query
# ============================================================================


class AppointmentStaffScheduleQuerySchema(BaseModel):
    """
    Query parameters for retrieving a staff member's schedule.
    """

    date_: Optional[date] = Field(
        default=None,
        alias="date",
        description="Filter staff schedule to a single day (YYYY-MM-DD)",
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )