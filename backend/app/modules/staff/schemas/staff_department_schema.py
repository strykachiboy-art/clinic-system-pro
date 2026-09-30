from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StaffDepartmentUpdateSchema(BaseModel):
    department_id: int | None = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
    )
