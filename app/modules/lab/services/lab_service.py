from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums.lab_enums import LabOrderStatus, LabResultFlag, SampleType


class LabTestCreateSchema(BaseModel):
    clinic_id: Optional[int] = Field(None, description="Null for a clinic-agnostic/global test catalog entry")
    name: str = Field(..., max_length=150)
    code: Optional[str] = Field(None, max_length=50)
    sample_type: SampleType = Field(default=SampleType.BLOOD)
    reference_range: Optional[str] = Field(None, max_length=150)
    unit: Optional[str] = Field(None, max_length=30)
    price: Optional[Decimal] = Field(None, ge=0)

    class Config:
        from_attributes = True


class LabTestUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    code: Optional[str] = Field(None, max_length=50)
    sample_type: Optional[SampleType] = Field(None)
    reference_range: Optional[str] = Field(None, max_length=150)
    unit: Optional[str] = Field(None, max_length=30)
    price: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = Field(None)

    class Config:
        from_attributes = True


class LabOrderItemInputSchema(BaseModel):
    test_id: int = Field(..., description="ID of the LabTest being ordered")


class LabOrderCreateSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")
    patient_id: int = Field(..., description="ID of the patient")
    consultation_id: Optional[int] = Field(None, description="Linked consultation, if ordered during one")
    ordered_by_id: int = Field(..., description="ID of the staff member ordering the tests")

    tests: list[LabOrderItemInputSchema] = Field(..., min_length=1, description="Tests to include in this order")

    class Config:
        from_attributes = True


class LabOrderCollectSampleSchema(BaseModel):
    """Marks a sample as physically collected — moves status to SAMPLE_COLLECTED."""
    qr_code: Optional[str] = Field(None, max_length=150, description="Sample tracking code, if used")


class LabOrderEquipmentLinkSchema(BaseModel):
    """Links an order to an external machine/LIS reference once it starts processing."""
    equipment_reference_id: str = Field(..., max_length=150)


class LabOrderCancelSchema(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


class LabResultEntrySchema(BaseModel):
    result_value: str = Field(..., max_length=150)
    flag: Optional[LabResultFlag] = Field(None)
    result_notes: Optional[str] = Field(None)
    result_file_url: Optional[str] = Field(None, max_length=255)