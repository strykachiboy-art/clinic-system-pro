from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

from app.core.enums.patient_enums import Gender, BloodType, FamilyRelation


class PatientCreateSchema(BaseModel):
    clinic_id: int = Field(..., description="ID of the clinic")

    first_name: str = Field(..., max_length=80)
    last_name: str = Field(..., max_length=80)
    date_of_birth: Optional[date] = Field(None)
    gender: Optional[Gender] = Field(None)
    blood_type: BloodType = Field(default=BloodType.UNKNOWN)

    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=255)

    allergies: Optional[str] = Field(None)
    chronic_conditions: Optional[str] = Field(None)

    # patient_number is server-generated (see project notes), not client-supplied

    class Config:
        from_attributes = True


class PatientUpdateSchema(BaseModel):
    first_name: Optional[str] = Field(None, max_length=80)
    last_name: Optional[str] = Field(None, max_length=80)
    date_of_birth: Optional[date] = Field(None)
    gender: Optional[Gender] = Field(None)
    blood_type: Optional[BloodType] = Field(None)

    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=255)

    allergies: Optional[str] = Field(None)
    chronic_conditions: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)

    class Config:
        from_attributes = True


class PatientFamilyMemberCreateSchema(BaseModel):
    full_name: str = Field(..., max_length=150)
    relation: FamilyRelation = Field(...)
    phone: Optional[str] = Field(None, max_length=30)
    is_emergency_contact: bool = Field(False)
    related_patient_id: Optional[int] = Field(None, description="Set if this family member is also a registered patient")

    class Config:
        from_attributes = True


class PatientFamilyMemberUpdateSchema(BaseModel):
    full_name: Optional[str] = Field(None, max_length=150)
    relation: Optional[FamilyRelation] = Field(None)
    phone: Optional[str] = Field(None, max_length=30)
    is_emergency_contact: Optional[bool] = Field(None)

    class Config:
        from_attributes = True


class PatientInsuranceCreateSchema(BaseModel):
    provider_name: str = Field(..., max_length=150)
    policy_number: str = Field(..., max_length=100)
    plan_type: Optional[str] = Field(None, max_length=100)

    coverage_start: Optional[date] = Field(None)
    coverage_end: Optional[date] = Field(None)
    is_primary: bool = Field(True)

    class Config:
        from_attributes = True


class PatientInsuranceUpdateSchema(BaseModel):
    provider_name: Optional[str] = Field(None, max_length=150)
    policy_number: Optional[str] = Field(None, max_length=100)
    plan_type: Optional[str] = Field(None, max_length=100)

    coverage_start: Optional[date] = Field(None)
    coverage_end: Optional[date] = Field(None)
    is_primary: Optional[bool] = Field(None)
    is_active: Optional[bool] = Field(None)

    class Config:
        from_attributes = True


class PatientVitalsRecordSchema(BaseModel):
    """One reading. Deliberately append-only — see PatientVitals model docstring:
    it's a historical log so trends can be charted, not a single row that gets
    overwritten each visit."""
    consultation_id: Optional[int] = Field(None, description="Linked consultation, if recorded during one")
    recorded_by_id: Optional[int] = Field(None, description="Staff member who took the reading")

    temperature_c: Optional[Decimal] = Field(None, description="Body temperature in Celsius")
    blood_pressure_systolic: Optional[int] = Field(None, gt=0)
    blood_pressure_diastolic: Optional[int] = Field(None, gt=0)
    heart_rate_bpm: Optional[int] = Field(None, gt=0)
    respiratory_rate: Optional[int] = Field(None, gt=0)
    oxygen_saturation: Optional[Decimal] = Field(None, ge=0, le=100, description="SpO2 percentage")
    weight_kg: Optional[Decimal] = Field(None, gt=0)
    height_cm: Optional[Decimal] = Field(None, gt=0)