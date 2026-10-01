from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.staff_department_enums import (
    StaffDepartmentStatus,
)


class StaffDepartmentCreateSchema(BaseModel):
    department_id: int = Field(
        ...,
        gt=0,
    )

    is_primary: bool = False

    model_config = ConfigDict(
        extra="forbid",
    )


class StaffDepartmentUpdateSchema(BaseModel):
    department_id: int | None = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class StaffDepartmentListQuerySchema(BaseModel):
    include_ended: bool = False

    model_config = ConfigDict(
        extra="forbid",
    )


class StaffDepartmentResponseSchema(BaseModel):
    id: int
    clinic_id: int
    staff_id: int
    department_id: int
    is_primary: bool
    status: StaffDepartmentStatus
    assigned_at: datetime
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )
