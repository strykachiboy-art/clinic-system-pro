from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums.patient_enums import (
    BloodType,
    FamilyRelation,
    Gender,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


REQUEST_CONFIG = ConfigDict(
    extra="forbid",
    from_attributes=True,
)


class PatientPaginationSchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        description="Page number",
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
        description="Items per page",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class PatientListQuerySchema(PatientPaginationSchema):
    active_only: bool = False

    search: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class PatientFamilyMemberListQuerySchema(
    PatientPaginationSchema
):
    pass


class PatientInsuranceListQuerySchema(
    PatientPaginationSchema
):
    pass


class PatientVitalsListQuerySchema(
    PatientPaginationSchema
):
    pass


class PatientCreateSchema(BaseModel):
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=80,
    )

    last_name: str = Field(
        ...,
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

    model_config = REQUEST_CONFIG


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

    model_config = REQUEST_CONFIG


class PatientStatusUpdateSchema(BaseModel):
    is_active: bool

    model_config = REQUEST_CONFIG


class PatientResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    clinic_id: int = Field(
        ...,
        gt=0,
    )

    patient_number: str = Field(
        ...,
        min_length=1,
    )

    first_name: str = Field(
        ...,
        min_length=1,
    )

    last_name: str = Field(
        ...,
        min_length=1,
    )

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
        extra="forbid",
    )


class PatientListResponseSchema(BaseModel):
    items: list[PatientResponseSchema]
    total: int = Field(
        ...,
        ge=0,
    )

    page: int = Field(
        ...,
        ge=1,
    )

    per_page: int = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


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

    model_config = REQUEST_CONFIG


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

    model_config = REQUEST_CONFIG


class PatientFamilyMemberResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    patient_id: int = Field(
        ...,
        gt=0,
    )

    related_patient_id: Optional[int] = Field(
        None,
        gt=0,
    )

    full_name: str = Field(
        ...,
        min_length=1,
    )

    relation: FamilyRelation

    phone: Optional[str] = None
    is_emergency_contact: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class PatientFamilyMemberListResponseSchema(BaseModel):
    items: list[PatientFamilyMemberResponseSchema]
    total: int = Field(
        ...,
        ge=0,
    )

    page: int = Field(
        ...,
        ge=1,
    )

    per_page: int = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


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

    model_config = REQUEST_CONFIG


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

    model_config = REQUEST_CONFIG


class PatientInsuranceResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    patient_id: int = Field(
        ...,
        gt=0,
    )

    provider_name: str = Field(
        ...,
        min_length=1,
    )

    policy_number: str = Field(
        ...,
        min_length=1,
    )

    plan_type: Optional[str] = None

    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None

    is_primary: bool
    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class PatientInsuranceListResponseSchema(BaseModel):
    items: list[PatientInsuranceResponseSchema]
    total: int = Field(
        ...,
        ge=0,
    )

    page: int = Field(
        ...,
        ge=1,
    )

    per_page: int = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


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

    consultation_id: Optional[int] = Field(
        None,
        gt=0,
    )

    model_config = REQUEST_CONFIG


class PatientVitalsResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    patient_id: int = Field(
        ...,
        gt=0,
    )

    consultation_id: Optional[int] = Field(
        None,
        gt=0,
    )

    recorded_by_id: Optional[int] = Field(
        None,
        gt=0,
    )

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
        extra="forbid",
    )


class PatientVitalsListResponseSchema(BaseModel):
    items: list[PatientVitalsResponseSchema]
    total: int = Field(
        ...,
        ge=0,
    )

    page: int = Field(
        ...,
        ge=1,
    )

    per_page: int = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )