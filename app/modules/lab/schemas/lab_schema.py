from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums.lab_enums import (
    LabOrderStatus,
    LabResultFlag,
    SampleType,
)


# ---------------------------------------------------------------------
# Lab test catalog
# ---------------------------------------------------------------------


class LabTestCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)

    loinc_code: Optional[str] = Field(
        None,
        max_length=20,
    )

    code: Optional[str] = Field(
        None,
        max_length=50,
    )

    sample_type: SampleType = Field(
        default=SampleType.BLOOD,
    )

    reference_range: Optional[str] = Field(
        None,
        max_length=150,
    )

    unit: Optional[str] = Field(
        None,
        max_length=30,
    )

    price: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
    )

    critical_low: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    critical_high: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    is_active: bool = Field(
        default=True,
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_critical_range(self):
        if (
            self.critical_low is not None
            and self.critical_high is not None
            and self.critical_low >= self.critical_high
        ):
            raise ValueError(
                "critical_low must be less than critical_high"
            )

        return self


class LabTestUpdateSchema(BaseModel):
    loinc_code: Optional[str] = Field(
        None,
        max_length=20,
    )

    code: Optional[str] = Field(
        None,
        max_length=50,
    )

    sample_type: Optional[SampleType] = None

    reference_range: Optional[str] = Field(
        None,
        max_length=150,
    )

    unit: Optional[str] = Field(
        None,
        max_length=30,
    )

    price: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
    )

    critical_low: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    critical_high: Optional[Decimal] = Field(
        None,
        decimal_places=3,
    )

    is_active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_critical_range(self):
        if (
            self.critical_low is not None
            and self.critical_high is not None
            and self.critical_low >= self.critical_high
        ):
            raise ValueError(
                "critical_low must be less than critical_high"
            )

        return self


class LabTestListQuerySchema(BaseModel):
    clinic_id: Optional[int] = Field(
        None,
        gt=0,
    )

    active_only: bool = Field(
        default=True,
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------
# Lab orders
# ---------------------------------------------------------------------


class LabOrderCreateSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
    )

    patient_id: int = Field(
        ...,
        gt=0,
    )

    ordered_by_id: int = Field(
        ...,
        gt=0,
    )

    test_ids: list[int] = Field(
        ...,
        min_length=1,
    )

    consultation_id: Optional[int] = Field(
        None,
        gt=0,
    )

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_test_ids(self):
        if any(test_id <= 0 for test_id in self.test_ids):
            raise ValueError(
                "All test_ids must be greater than zero"
            )

        if len(self.test_ids) != len(set(self.test_ids)):
            raise ValueError(
                "Duplicate test_ids are not allowed"
            )

        return self


class LabSampleCollectionSchema(BaseModel):
    scanned_qr_code: Optional[str] = Field(
        None,
        min_length=1,
        max_length=150,
    )

    model_config = ConfigDict(from_attributes=True)


class LabEquipmentLinkSchema(BaseModel):
    equipment_reference_id: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    model_config = ConfigDict(from_attributes=True)


class LabOrderCancelSchema(BaseModel):
    reason: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------


class LabResultCreateSchema(BaseModel):
    result_value: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    flag: Optional[LabResultFlag] = None

    result_notes: Optional[str] = None

    result_file_url: Optional[str] = Field(
        None,
        max_length=255,
    )

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------
# Query schemas
# ---------------------------------------------------------------------


class LabOrderListQuerySchema(BaseModel):
    patient_id: int = Field(
        ...,
        gt=0,
    )

    model_config = ConfigDict(from_attributes=True)