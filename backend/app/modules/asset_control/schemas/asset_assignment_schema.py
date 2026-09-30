from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetAssignmentCreateSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    staff_id: int = Field(
        gt=0,
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class AssetAssignmentReturnSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class AssetAssignmentResponseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    id: int
    clinic_id: int
    asset_id: int
    staff_id: int

    assigned_at: datetime
    returned_at: datetime | None = None

    assigned_by_user_id: int | None = None
    returned_by_user_id: int | None = None

    notes: str | None = None

    created_at: datetime
    updated_at: datetime


class AssetAssignmentListQuerySchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    asset_id: int | None = Field(
        default=None,
        gt=0,
    )

    staff_id: int | None = Field(
        default=None,
        gt=0,
    )

    active_only: bool = False

    assigned_from: datetime | None = None
    assigned_to: datetime | None = None

    page: int = Field(
        default=1,
        ge=1,
    )

    per_page: int = Field(
        default=50,
        ge=1,
        le=500,
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "AssetAssignmentListQuerySchema":
        if (
            self.assigned_from is not None
            and self.assigned_to is not None
            and self.assigned_to < self.assigned_from
        ):
            raise ValueError(
                "assigned_to must be greater than or equal to assigned_from"
            )

        return self