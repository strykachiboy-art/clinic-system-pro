from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums.patient_enums import (
    BloodType,
    FamilyRelation,
    Gender,
)


# ============================================================================
# Patient
# ============================================================================

class PatientCreateSchema(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)

    date_of_birth: Optional[date] = None

    gender: Optional[Gender] = None
    blood_type: Optional[BloodType] = None

    phone: Optional[str] = Field(
        None,
        max_length=30,
    )

    email: Optional[EmailStr] = None

    address: Optional[str] = Field(
        None,
        max_length=255,
    )

    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

    emirates_id: Optional[str] = Field(
        None,
        max_length=50,
    )

    umrn: Optional[str] = Field(
        None,
        max_length=50,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientUpdateSchema(BaseModel):
    first_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=80,
    )

    last_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=80,
    )

    date_of_birth: Optional[date] = None

    gender: Optional[Gender] = None
    blood_type: Optional[BloodType] = None

    phone: Optional[str] = Field(
        None,
        max_length=30,
    )

    email: Optional[EmailStr] = None

    address: Optional[str] = Field(
        None,
        max_length=255,
    )

    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

    emirates_id: Optional[str] = Field(
        None,
        max_length=50,
    )

    umrn: Optional[str] = Field(
        None,
        max_length=50,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientStatusUpdateSchema(BaseModel):
    is_active: bool

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientResponseSchema(BaseModel):
    id: int
    clinic_id: int
    patient_number: str

    first_name: str
    last_name: str

    date_of_birth: Optional[date] = None

    gender: Optional[Gender] = None
    blood_type: Optional[BloodType] = None

    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None

    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

    emirates_id: Optional[str] = None
    umrn: Optional[str] = None

    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Family Members
# ============================================================================

class PatientFamilyMemberCreateSchema(BaseModel):
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=160,
    )

    relation: FamilyRelation

    phone: Optional[str] = Field(
        None,
        max_length=30,
    )

    is_emergency_contact: bool = False

    related_patient_id: Optional[int] = Field(
        None,
        gt=0,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientFamilyMemberUpdateSchema(BaseModel):
    full_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=160,
    )

    relation: Optional[FamilyRelation] = None

    phone: Optional[str] = Field(
        None,
        max_length=30,
    )

    is_emergency_contact: Optional[bool] = None

    related_patient_id: Optional[int] = Field(
        None,
        gt=0,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientFamilyMemberResponseSchema(BaseModel):
    id: int
    patient_id: int
    related_patient_id: Optional[int] = None

    full_name: str
    relation: FamilyRelation

    phone: Optional[str] = None
    is_emergency_contact: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Insurance
# ============================================================================

class PatientInsuranceCreateSchema(BaseModel):
    provider_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
    )

    policy_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    plan_type: Optional[str] = Field(
        None,
        max_length=100,
    )

    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None

    is_primary: bool = False
    is_active: bool = True

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientInsuranceUpdateSchema(BaseModel):
    provider_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=120,
    )

    policy_number: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
    )

    plan_type: Optional[str] = Field(
        None,
        max_length=100,
    )

    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None

    is_primary: Optional[bool] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientInsuranceResponseSchema(BaseModel):
    id: int
    patient_id: int

    provider_name: str
    policy_number: str
    plan_type: Optional[str] = None

    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None

    is_primary: bool
    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ============================================================================
# Vitals
# ============================================================================

class PatientVitalsCreateSchema(BaseModel):
    temperature: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
    )

    blood_pressure_systolic: Optional[int] = Field(
        None,
        ge=0,
        le=400,
    )

    blood_pressure_diastolic: Optional[int] = Field(
        None,
        ge=0,
        le=300,
    )

    heart_rate: Optional[int] = Field(
        None,
        ge=0,
        le=400,
    )

    respiratory_rate: Optional[int] = Field(
        None,
        ge=0,
        le=200,
    )

    oxygen_saturation: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
    )

    weight: Optional[Decimal] = Field(
        None,
        ge=0,
    )

    height: Optional[Decimal] = Field(
        None,
        ge=0,
    )

    recorded_at: Optional[datetime] = None

    consultation_id: Optional[int] = Field(
        None,
        gt=0,
    )

    recorded_by_id: Optional[int] = Field(
        None,
        gt=0,
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class PatientVitalsResponseSchema(BaseModel):
    id: int
    patient_id: int

    consultation_id: Optional[int] = None
    recorded_by_id: Optional[int] = None

    temperature: Optional[Decimal] = Field(
        default=None,
        validation_alias="temperature_c",
    )

    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None

    heart_rate: Optional[int] = Field(
        default=None,
        validation_alias="heart_rate_bpm",
    )

    respiratory_rate: Optional[int] = None

    oxygen_saturation: Optional[Decimal] = None

    weight: Optional[Decimal] = Field(
        default=None,
        validation_alias="weight_kg",
    )

    height: Optional[Decimal] = Field(
        default=None,
        validation_alias="height_cm",
    )

    recorded_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )