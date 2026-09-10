from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


class PaginationSchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
    )

    per_page: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class PaginationResponseSchema(BaseModel):
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


class ExcuseCreateSchema(BaseModel):
    leave_request_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional leave request this excuse supports",
    )

    excuse_type: ExcuseType = Field(
        ...,
        description="Type of excuse",
    )

    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Reason/details supporting the excuse",
    )

    document_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional supporting document reference",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ExcuseReviewSchema(BaseModel):
    """Approve an excuse."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ExcuseRejectSchema(BaseModel):
    """Reject an excuse."""

    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Reason for rejecting the excuse",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ExcuseListQuerySchema(PaginationSchema):
    staff_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    leave_request_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    excuse_type: Optional[ExcuseType] = None

    status: Optional[ExcuseStatus] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ExcuseResponseSchema(BaseModel):
    id: int = Field(
        ...,
        gt=0,
    )

    staff_id: int = Field(
        ...,
        gt=0,
    )

    leave_request_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    excuse_type: ExcuseType

    status: ExcuseStatus

    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
    )

    document_url: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    rejection_reason: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    reviewed_by_user_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    reviewed_at: Optional[datetime] = None

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class ExcuseListResponseSchema(
    PaginationResponseSchema,
):
    items: list[ExcuseResponseSchema]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )