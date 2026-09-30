from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
)

from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
)


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500

MAX_DESCRIPTION_LENGTH = 2000
MAX_DOCUMENT_URL_LENGTH = 500
MAX_REJECTION_REASON_LENGTH = 2000


class PaginationSchema(BaseModel):
    page: int = Field(
        default=DEFAULT_PAGE,
        ge=1,
        le=10_000_000,
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
    total: StrictInt = Field(
        ...,
        ge=0,
    )

    page: StrictInt = Field(
        ...,
        ge=1,
    )

    per_page: StrictInt = Field(
        ...,
        ge=1,
        le=MAX_PER_PAGE,
    )

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )


class ExcuseCreateSchema(BaseModel):
    leave_request_id: Optional[StrictInt] = Field(
        default=None,
        gt=0,
        description="Optional leave request this excuse supports",
    )

    excuse_type: ExcuseType = Field(
        ...,
        description="Type of excuse",
    )

    description: StrictStr = Field(
        ...,
        min_length=1,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Reason/details supporting the excuse",
    )

    document_url: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=MAX_DOCUMENT_URL_LENGTH,
        description="Optional supporting document reference",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class ExcuseReviewSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )


class ExcuseRejectSchema(BaseModel):
    reason: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=MAX_REJECTION_REASON_LENGTH,
        description="Reason for rejecting the excuse",
    )

    model_config = ConfigDict(
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
        extra="forbid",
    )


class ExcuseResponseSchema(BaseModel):
    id: StrictInt = Field(
        ...,
        gt=0,
    )

    staff_id: StrictInt = Field(
        ...,
        gt=0,
    )

    leave_request_id: Optional[StrictInt] = Field(
        default=None,
        gt=0,
    )

    excuse_type: ExcuseType

    status: ExcuseStatus

    description: StrictStr = Field(
        ...,
        min_length=1,
        max_length=MAX_DESCRIPTION_LENGTH,
    )

    document_url: Optional[StrictStr] = Field(
        default=None,
        max_length=MAX_DOCUMENT_URL_LENGTH,
    )

    rejection_reason: Optional[StrictStr] = Field(
        default=None,
        min_length=1,
        max_length=MAX_REJECTION_REASON_LENGTH,
    )

    reviewed_by_user_id: Optional[StrictInt] = Field(
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