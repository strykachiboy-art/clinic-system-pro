from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums.consultation_enums import ConsultationStatus, ConsultationType


class ConsultationStartSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: int = Field(..., description="ID of the patient")
    staff_id: int = Field(..., description="ID of the attending staff member")
    appointment_id: Optional[int] = Field(None, description="Linked appointment, if this consultation started from one")

    consultation_type: ConsultationType = Field(default=ConsultationType.GENERAL)
    template_id: Optional[int] = Field(None, description="Consultation template to structure this note")

    chief_complaint: Optional[str] = Field(None)
    symptoms: Optional[str] = Field(None)

    class Config:
        from_attributes = True


class ConsultationUpdateSchema(BaseModel):
    """For in-progress editing of the clinical note before it's completed."""
    chief_complaint: Optional[str] = Field(None)
    symptoms: Optional[str] = Field(None)
    diagnosis: Optional[str] = Field(None)
    treatment_plan: Optional[str] = Field(None)
    notes: Optional[str] = Field(None)

    voice_note_url: Optional[str] = Field(None, max_length=255)
    transcribed_text: Optional[str] = Field(None)

    class Config:
        from_attributes = True


class ConsultationCompleteSchema(BaseModel):
    """Final sign-off — diagnosis is required to close out a consultation,
    everything else is optional last-minute additions."""
    diagnosis: str = Field(..., description="Final diagnosis, required to complete a consultation")
    treatment_plan: Optional[str] = Field(None)
    notes: Optional[str] = Field(None)


class ConsultationCancelSchema(BaseModel):
    reason: Optional[str] = Field(None, description="Reason the consultation was cancelled")


class ConsultationTemplateCreateSchema(BaseModel):
    clinic_id: Optional[int] = Field(None, description="Null for a clinic-agnostic/global template")
    name: str = Field(..., max_length=150)
    specialty: Optional[str] = Field(None, max_length=100)
    structure: dict = Field(..., description="JSON structure defining the template's sections/fields")
    is_active: bool = Field(True)

    class Config:
        from_attributes = True