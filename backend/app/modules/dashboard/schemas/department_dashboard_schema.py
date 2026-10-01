from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.department_enums import DepartmentStatus
from app.core.enums.staff_department_enums import StaffDepartmentStatus


class ManagementDepartmentSummarySchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    code: str
    name: str
    status: DepartmentStatus

    active_staff_count: int = Field(
        ...,
        ge=0,
    )

    primary_staff_count: int = Field(
        ...,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class ManagementDepartmentDashboardSchema(BaseModel):
    total_departments: int = Field(
        ...,
        ge=0,
    )

    active_departments: int = Field(
        ...,
        ge=0,
    )

    inactive_departments: int = Field(
        ...,
        ge=0,
    )

    suspended_departments: int = Field(
        ...,
        ge=0,
    )

    departments: list[
        ManagementDepartmentSummarySchema
    ] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class ClinicalDepartmentSchema(BaseModel):
    department_id: int = Field(
        ...,
        gt=0,
    )

    code: str
    name: str
    status: StaffDepartmentStatus
    is_primary: bool

    model_config = ConfigDict(
        extra="forbid",
    )


class SuperAdminDepartmentClinicSummarySchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
    )

    clinic_name: str

    total_departments: int = Field(
        ...,
        ge=0,
    )

    active_departments: int = Field(
        ...,
        ge=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class SuperAdminDepartmentDashboardSchema(BaseModel):
    total_departments: int = Field(
        ...,
        ge=0,
    )

    active_departments: int = Field(
        ...,
        ge=0,
    )

    by_clinic: list[
        SuperAdminDepartmentClinicSummarySchema
    ] = Field(
        default_factory=list,
    )

    model_config = ConfigDict(
        extra="forbid",
    )
