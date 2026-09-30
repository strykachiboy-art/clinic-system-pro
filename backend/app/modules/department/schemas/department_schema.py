from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.department_enums import DepartmentStatus


class DepartmentCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    code: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )


class DepartmentUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )


class DepartmentStatusUpdateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    status: DepartmentStatus


class DepartmentListQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    status: DepartmentStatus | None = None

    search: str | None = Field(
        default=None,
        max_length=150,
    )


class DepartmentResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    clinic_id: int
    code: str
    name: str
    description: str | None = None
    status: DepartmentStatus
    created_at: datetime
    updated_at: datetime