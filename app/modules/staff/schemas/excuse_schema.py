from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
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

    model_config = ConfigDict(from_attributes=True)


class ExcuseReviewSchema(BaseModel):
    """
    Approve an excuse.

    reviewed_by_user_id is intentionally excluded.
    The reviewer is derived from the authenticated user.
    """

    model_config = ConfigDict(from_attributes=True)


class ExcuseRejectSchema(BaseModel):
    """
    Reject an excuse.

    reviewed_by_user_id is intentionally excluded.
    The reviewer is derived from the authenticated user.
    """

    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Reason for rejecting the excuse",
    )

    model_config = ConfigDict(from_attributes=True)


class ExcuseListQuerySchema(BaseModel):
    """
    Filters for listing excuses within the authenticated clinic.
    """

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

    model_config = ConfigDict(from_attributes=True)


class ExcuseResponseSchema(BaseModel):
    id: int
    staff_id: int
    leave_request_id: Optional[int]
    excuse_type: ExcuseType
    status: ExcuseStatus
    description: str
    document_url: Optional[str]
    rejection_reason: Optional[str]
    reviewed_by_user_id: Optional[int]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)