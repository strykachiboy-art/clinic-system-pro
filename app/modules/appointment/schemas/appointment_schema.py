from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums.appointment_enums import AppointmentStatus, AppointmentType


class AppointmentCreateSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: int = Field(..., description="ID of the patient")
    staff_id: int = Field(..., description="ID of the staff member (doctor/practitioner)")
    
    scheduled_start: datetime = Field(..., description="Start date and time of the appointment")
    scheduled_end: datetime = Field(..., description="End date and time of the appointment")
    
    appointment_type: AppointmentType = Field(
        default=AppointmentType.IN_PERSON, 
        description="Type of the appointment"
    )
    reason: Optional[str] = Field(None, max_length=255, description="Reason for the visit")
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        from_attributes = True


class AppointmentUpdateSchema(BaseModel):
    staff_id: Optional[int] = Field(None, description="Updated staff ID")
    scheduled_start: Optional[datetime] = Field(None, description="Updated start time")
    scheduled_end: Optional[datetime] = Field(None, description="Updated end time")
    
    status: Optional[AppointmentStatus] = Field(None, description="Updated appointment status")
    appointment_type: Optional[AppointmentType] = Field(None, description="Updated appointment type")
    
    reason: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None)
    
    reminder_sent: Optional[bool] = Field(None)
    cancelled_at: Optional[datetime] = Field(None)
    cancellation_reason: Optional[str] = Field(None, max_length=255)

    class Config:
        from_attributes = True


class AppointmentRescheduleSchema(BaseModel):
    scheduled_start: datetime = Field(..., description="New start date and time")
    scheduled_end: datetime = Field(..., description="New end date and time")


class AppointmentCancelSchema(BaseModel):
    reason: Optional[str] = Field(None, max_length=255, description="Reason for cancellation")


class AppointmentCompleteSchema(BaseModel):
    notes: Optional[str] = Field(None, description="Consultation/visit notes to attach on completion")


class AppointmentStaffScheduleQuerySchema(BaseModel):
    date_: Optional[date] = Field(None, alias="date", description="Filter staff schedule to a single day (YYYY-MM-DD)")

    class Config:
        populate_by_name = True