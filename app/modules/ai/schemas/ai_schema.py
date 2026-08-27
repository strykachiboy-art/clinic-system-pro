from typing import Optional
from pydantic import BaseModel, Field


class DrugInteractionCheckSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: Optional[int] = Field(None, description="ID of the patient, if tied to one")
    drug_names: list[str] = Field(..., min_length=2, description="Drug names to check against each other")

    class Config:
        from_attributes = True


class TriageAssistantSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: int = Field(..., description="ID of the patient being triaged")
    symptoms: str = Field(..., description="Free-text description of presenting symptoms")
    vitals: Optional[dict] = Field(None, description="Optional recent vitals snapshot, e.g. {'temp_c': 38.5}")


class LabResultInterpreterSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: Optional[int] = Field(None, description="ID of the patient, if tied to one")
    lab_order_id: Optional[int] = Field(None, description="ID of the source LabOrder, if any")
    result_data: dict = Field(..., description="Raw lab result values to interpret, e.g. {'WBC': 11.2, 'unit': '10^9/L'}")