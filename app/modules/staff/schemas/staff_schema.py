from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.core.enums.staff_enums import (
    LeaveStatus,
    LeaveType,
    StaffStatus,
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


class StaffCreateSchema(BaseModel):
    """Create a staff profile."""

    user_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

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

    specialty: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    phone: Optional[str] = Field(
        default=None,
        max_length=30,
    )

    email: Optional[str] = Field(
        default=None,
        max_length=120,
    )

    hired_at: Optional[date] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class StaffUpdateSchema(BaseModel):
    first_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=80,
    )

    last_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=80,
    )

    specialty: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    phone: Optional[str] = Field(
        default=None,
        max_length=30,
    )

    email: Optional[str] = Field(
        default=None,
        max_length=120,
    )

    hired_at: Optional[date] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class StaffStatusUpdateSchema(BaseModel):
    status: StaffStatus

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class StaffListQuerySchema(PaginationSchema):
    status: Optional[StaffStatus] = None

    search: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class LeaveRequestCreateSchema(BaseModel):
    """Create a leave request for the authenticated staff member."""

    leave_type: LeaveType

    start_date: date

    end_date: date

    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError(
                "Leave end date cannot be before start date"
            )

        return self

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class LeaveReviewSchema(BaseModel):
    """Approve a leave request."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class LeaveRejectSchema(BaseModel):
    """Reject a leave request."""

    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class LeaveListQuerySchema(PaginationSchema):
    staff_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    status: Optional[LeaveStatus] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class PayrollCreateSchema(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0,
    )

    pay_period_start: date

    pay_period_end: date

    base_salary: Decimal = Field(
        ...,
        ge=Decimal("0"),
    )

    bonuses: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
    )

    deductions: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
    )

    @model_validator(mode="after")
    def validate_period(self):
        if isinstance(self.staff_id, bool):
            raise ValueError(
                "Staff ID must be a positive integer"
            )

        if self.pay_period_end < self.pay_period_start:
            raise ValueError(
                "Pay period end cannot be before pay period start"
            )

        net_pay = (
            self.base_salary
            + self.bonuses
            - self.deductions
        )

        if net_pay < Decimal("0"):
            raise ValueError(
                "Deductions cannot exceed total earnings"
            )

        return self

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class PayrollGenerateSchema(BaseModel):
    pay_period_start: date

    pay_period_end: date

    salary_lookup: dict[int, Decimal] = Field(
        ...,
        description="Mapping of staff ID to base salary",
    )

    @model_validator(mode="after")
    def validate_period_and_salaries(self):
        if self.pay_period_end < self.pay_period_start:
            raise ValueError(
                "Pay period end cannot be before pay period start"
            )

        for staff_id, salary in self.salary_lookup.items():
            if isinstance(staff_id, bool) or staff_id <= 0:
                raise ValueError(
                    "Salary lookup contains an invalid staff ID"
                )

            if salary < Decimal("0"):
                raise ValueError(
                    f"Salary for staff {staff_id} cannot be negative"
                )

        return self

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class PayrollListQuerySchema(PaginationSchema):
    staff_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class StaffListResponseSchema(
    PaginationResponseSchema,
):
    items: list[StaffCreateSchema]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class LeaveListResponseSchema(
    PaginationResponseSchema,
):
    items: list[LeaveRequestCreateSchema]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class PayrollListResponseSchema(
    PaginationResponseSchema,
):
    items: list[PayrollCreateSchema]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )