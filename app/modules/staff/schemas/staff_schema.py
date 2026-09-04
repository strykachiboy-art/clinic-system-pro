from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums.staff_enums import (
    LeaveStatus,
    LeaveType,
    StaffStatus,
)


# ============================================================================
# STAFF
# ============================================================================


class StaffCreateSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
        description="ID of the clinic the staff member belongs to",
    )
    user_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional user account linked to this staff member",
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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class StaffStatusUpdateSchema(BaseModel):
    status: StaffStatus = Field(
        ...,
        description="New staff status",
    )

    model_config = ConfigDict(from_attributes=True)


class StaffListQuerySchema(BaseModel):
    clinic_id: Optional[int] = Field(
        default=None,
        gt=0,
    )
    status: Optional[StaffStatus] = None
    search: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# LEAVE
# ============================================================================


class LeaveRequestCreateSchema(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0,
    )
    leave_type: LeaveType = Field(...)
    start_date: date = Field(...)
    end_date: date = Field(...)
    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Leave end date cannot be before start date")
        return self

    model_config = ConfigDict(from_attributes=True)


class LeaveReviewSchema(BaseModel):
    reviewed_by_id: int = Field(
        ...,
        gt=0,
        description="Staff ID of the person reviewing the leave request",
    )

    model_config = ConfigDict(from_attributes=True)


class LeaveRejectSchema(BaseModel):
    reviewed_by_id: int = Field(
        ...,
        gt=0,
        description="Staff ID of the person rejecting the leave request",
    )
    reason: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    model_config = ConfigDict(from_attributes=True)


class LeaveListQuerySchema(BaseModel):
    staff_id: Optional[int] = Field(
        default=None,
        gt=0,
    )
    status: Optional[LeaveStatus] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# PAYROLL
# ============================================================================


class PayrollCreateSchema(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0,
    )
    pay_period_start: date = Field(...)
    pay_period_end: date = Field(...)

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
        if self.pay_period_end < self.pay_period_start:
            raise ValueError(
                "Pay period end cannot be before pay period start"
            )
        return self

    model_config = ConfigDict(from_attributes=True)


class PayrollGenerateSchema(BaseModel):
    clinic_id: int = Field(
        ...,
        gt=0,
    )
    pay_period_start: date = Field(...)
    pay_period_end: date = Field(...)

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
            if staff_id <= 0:
                raise ValueError(
                    "Salary lookup contains an invalid staff ID"
                )

            if salary < Decimal("0"):
                raise ValueError(
                    f"Salary for staff {staff_id} cannot be negative"
                )

        return self

    model_config = ConfigDict(from_attributes=True)


class PayrollListQuerySchema(BaseModel):
    staff_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    model_config = ConfigDict(from_attributes=True)