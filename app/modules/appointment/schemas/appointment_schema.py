from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.core.enums.appointment_enums import AppointmentType


class AppointmentCreateSchema(BaseModel):
    clinic_id: int = Field(..., gt=0, description="ID of the clinic")
    patient_id: int = Field(..., gt=0, description="ID of the patient")
    staff_id: int = Field(..., gt=0, description="ID of the staff member")

    scheduled_start: datetime = Field(
        ..., description="Start date and time of the appointment"
    )
    scheduled_end: datetime = Field(
        ..., description="End date and time of the appointment"
    )

    appointment_type: AppointmentType = Field(
        default=AppointmentType.IN_PERSON,
        description="Type of the appointment",
    )
    reason: Optional[str] = Field(
        None,
        max_length=255,
        description="Reason for the visit",
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes",
    )

    class Config:
        from_attributes = True


class AppointmentRescheduleSchema(BaseModel):
    scheduled_start: datetime = Field(
        ..., description="New start date and time"
    )
    scheduled_end: datetime = Field(
        ..., description="New end date and time"
    )


class AppointmentCancelSchema(BaseModel):
    cancellation_reason: Optional[str] = Field(
        None,
        max_length=255,
        description="Reason for cancellation",
    )


class AppointmentCompleteSchema(BaseModel):
    notes: Optional[str] = Field(
        None,
        description="Consultation/visit notes to attach on completion",
    )


class AppointmentStaffScheduleQuerySchema(BaseModel):
    date_: Optional[date] = Field(
        None,
        alias="date",
        description="Filter staff schedule to a single day (YYYY-MM-DD)",
    )

    class Config:
        populate_by_name = True