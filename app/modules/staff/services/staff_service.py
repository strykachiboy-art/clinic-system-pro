from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from app.extensions import db

from app.core.auth.user.models.user_model import User
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import (
    LeaveStatus,
    LeaveType,
    StaffStatus,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.modules.staff.models.staff_model import (
    LeaveRequest,
    PayrollRecord,
    Staff,
)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _get_staff(
    staff_id: int,
    clinic_id: Optional[int] = None,
    lock: bool = False,
) -> Staff:
    """
    Fetch a staff member.

    When clinic_id is supplied, the lookup is tenant-scoped.
    """

    query = Staff.query.filter(
        Staff.id == staff_id,
    )

    if clinic_id is not None:
        query = query.filter(
            Staff.clinic_id == clinic_id,
        )

    if lock:
        query = query.with_for_update()

    staff = query.first()

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    return staff


def get_staff(
    staff_id: int,
    clinic_id: Optional[int] = None,
) -> Staff:
    """
    Public staff lookup used by other services and routes.

    Supplying clinic_id enforces tenant isolation.
    """
    return _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
    )


def _get_user(
    user_id: int,
    clinic_id: Optional[int] = None,
) -> User:
    """
    Fetch a user and optionally enforce clinic ownership.
    """

    user = db.session.get(
        User,
        user_id,
    )

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    if clinic_id is not None and user.clinic_id != clinic_id:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _ensure_active_clinic(clinic_id: int) -> None:
    """
    Ensure the clinic exists and is active.

    Kept intentionally lightweight here so the Staff service does not
    introduce a circular dependency on clinic_service.
    """

    from app.modules.clinic.models.clinic_model import Clinic

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    status = clinic.status

    if getattr(status, "value", status) != "active":
        raise ConflictError(
            f"Clinic {clinic_id} is not active"
        )


def _serialize_enum(value):
    return (
        value.value
        if hasattr(value, "value")
        else value
    )


# ============================================================================
# STAFF
# ============================================================================

_EDITABLE_STAFF_FIELDS = {
    "first_name",
    "last_name",
    "specialty",
    "phone",
    "email",
    "hired_at",
}


def list_staff(
    clinic_id: int,
    status: StaffStatus | None = None,
    search: str | None = None,
) -> list[Staff]:
    """
    List staff belonging only to the requested clinic.
    """

    query = Staff.query.filter(
        Staff.clinic_id == clinic_id,
    )

    if status is not None:
        query = query.filter(
            Staff.status == status,
        )

    if search:
        search_value = search.strip()

        if search_value:
            like = f"%{search_value}%"

            query = query.filter(
                db.or_(
                    Staff.first_name.ilike(like),
                    Staff.last_name.ilike(like),
                )
            )

    return (
        query
        .order_by(
            Staff.last_name.asc(),
            Staff.first_name.asc(),
        )
        .all()
    )


@transactional
def create_staff(
    clinic_id: int,
    first_name: str,
    last_name: str,
    user_id: Optional[int] = None,
    specialty=None,
    phone=None,
    email=None,
    hired_at=None,
) -> Staff:
    """
    Create a staff profile inside the authenticated clinic.
    """

    _ensure_active_clinic(clinic_id)

    if not first_name or not first_name.strip():
        raise ValidationError(
            "First name is required"
        )

    if not last_name or not last_name.strip():
        raise ValidationError(
            "Last name is required"
        )

    if user_id is not None:
        user = _get_user(
            user_id=user_id,
            clinic_id=clinic_id,
        )

        if not getattr(user, "is_active", True):
            raise ValidationError(
                "User account is inactive"
            )

        existing = Staff.query.filter(
            Staff.user_id == user_id,
        ).first()

        if existing is not None:
            raise ConflictError(
                f"User {user_id} is already linked to staff {existing.id}"
            )

    staff = Staff(
        clinic_id=clinic_id,
        user_id=user_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        specialty=specialty,
        phone=phone,
        email=email,
        hired_at=hired_at,
        status=StaffStatus.ACTIVE,
    )

    db.session.add(staff)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Staff",
        entity_id=staff.id,
        description=(
            f"Staff '{staff.first_name} {staff.last_name}' created"
        ),
        user_id=None,
        new_value={
            "clinic_id": clinic_id,
            "user_id": user_id,
            "first_name": staff.first_name,
            "last_name": staff.last_name,
        },
    )

    return staff


@transactional
def update_staff(
    staff_id: int,
    clinic_id: int,
    **fields,
) -> Staff:
    """
    Update clinic-owned staff fields.

    Clinic ID is mandatory so an authenticated clinic cannot update
    another clinic's staff member.
    """

    _ensure_active_clinic(clinic_id)

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
        lock=True,
    )

    unknown = (
        set(fields)
        - _EDITABLE_STAFF_FIELDS
    )

    if unknown:
        raise ValidationError(
            "Unknown staff field(s): "
            + ", ".join(sorted(unknown))
        )

    old_value = {}
    new_value = {}

    for key, new_value_raw in fields.items():
        current_value = getattr(
            staff,
            key,
        )

        if current_value == new_value_raw:
            continue

        if key in {
            "first_name",
            "last_name",
        }:
            if (
                new_value_raw is None
                or not str(new_value_raw).strip()
            ):
                raise ValidationError(
                    f"{key.replace('_', ' ').title()} is required"
                )

            new_value_raw = str(
                new_value_raw
            ).strip()

        old_value[key] = _serialize_enum(
            current_value
        )

        new_value[key] = _serialize_enum(
            new_value_raw
        )

        setattr(
            staff,
            key,
            new_value_raw,
        )

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Staff",
            entity_id=staff.id,
            description=(
                f"Staff '{staff.first_name} "
                f"{staff.last_name}' updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return staff


@transactional
def change_staff_status(
    staff_id: int,
    clinic_id: int,
    new_status: StaffStatus,
) -> Staff:
    """
    Change staff status inside the authenticated clinic.
    """

    _ensure_active_clinic(clinic_id)

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if staff.status == new_status:
        return staff

    old_status = _serialize_enum(
        staff.status
    )

    staff.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Staff",
        entity_id=staff.id,
        description=(
            f"Staff status changed to "
            f"'{new_status.value}'"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": new_status.value,
        },
    )

    return staff


# ============================================================================
# LEAVE REQUESTS
# ============================================================================

def _get_leave_request(
    leave_id: int,
    clinic_id: Optional[int] = None,
    lock: bool = False,
) -> LeaveRequest:
    """
    Fetch a leave request through its Staff relationship so that
    clinic isolation is enforced.
    """

    query = (
        LeaveRequest.query
        .join(
            Staff,
            Staff.id == LeaveRequest.staff_id,
        )
        .filter(
            LeaveRequest.id == leave_id,
        )
    )

    if clinic_id is not None:
        query = query.filter(
            Staff.clinic_id == clinic_id,
        )

    if lock:
        query = query.with_for_update()

    leave = query.first()

    if leave is None:
        raise NotFoundError(
            f"Leave request {leave_id} not found"
        )

    return leave


def get_leave_request(
    leave_id: int,
    clinic_id: Optional[int] = None,
) -> LeaveRequest:
    """
    Public clinic-scoped leave lookup.
    """

    return _get_leave_request(
        leave_id=leave_id,
        clinic_id=clinic_id,
    )


def list_leave_requests(
    clinic_id: int,
    staff_id: Optional[int] = None,
    status: LeaveStatus | None = None,
) -> list[LeaveRequest]:
    """
    List leave requests belonging to a clinic.
    """

    query = (
        LeaveRequest.query
        .join(
            Staff,
            Staff.id == LeaveRequest.staff_id,
        )
        .filter(
            Staff.clinic_id == clinic_id,
        )
    )

    if staff_id is not None:
        query = query.filter(
            LeaveRequest.staff_id == staff_id,
        )

    if status is not None:
        query = query.filter(
            LeaveRequest.status == status,
        )

    return (
        query
        .order_by(
            LeaveRequest.start_date.desc(),
            LeaveRequest.created_at.desc(),
        )
        .all()
    )


def _has_overlapping_approved_leave(
    staff_id: int,
    start_date: date,
    end_date: date,
    exclude_leave_id: Optional[int] = None,
) -> bool:
    """
    Check for another approved leave period overlapping the requested
    dates.
    """

    query = LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )

    if exclude_leave_id is not None:
        query = query.filter(
            LeaveRequest.id != exclude_leave_id,
        )

    return (
        query.first()
        is not None
    )


@transactional
def request_leave(
    clinic_id: int,
    staff_id: int,
    actor_user_id: int,
    leave_type: LeaveType,
    start_date: date,
    end_date: date,
    reason: Optional[str] = None,
) -> LeaveRequest:
    """
    Create a leave request for the authenticated staff member.
    """

    _ensure_active_clinic(clinic_id)

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
    )

    user = _get_user(
        user_id=actor_user_id,
        clinic_id=clinic_id,
    )

    if staff.user_id != user.id:
        raise ValidationError(
            "Staff member does not belong to the authenticated user"
        )

    if end_date < start_date:
        raise ValidationError(
            "Leave end date cannot be before start date"
        )

    if staff.status in (
        StaffStatus.SUSPENDED,
        StaffStatus.TERMINATED,
    ):
        raise ConflictError(
            "Inactive staff members cannot request leave"
        )

    overlapping_pending = LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff.id,
        LeaveRequest.status == LeaveStatus.PENDING,
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    ).first()

    if overlapping_pending is not None:
        raise ConflictError(
            "Staff member already has a pending "
            "leave request overlapping this period"
        )

    if _has_overlapping_approved_leave(
        staff_id=staff.id,
        start_date=start_date,
        end_date=end_date,
    ):
        raise ConflictError(
            "Staff member already has approved leave "
            "overlapping this period"
        )

    leave = LeaveRequest(
        staff_id=staff.id,
        leave_type=leave_type,
        status=LeaveStatus.PENDING,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip()
        if isinstance(reason, str)
        else reason,
    )

    db.session.add(leave)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=(
            f"Leave requested for staff {staff.id}"
        ),
        user_id=actor_user_id,
        new_value={
            "clinic_id": clinic_id,
            "staff_id": staff.id,
            "leave_type": leave_type.value,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )

    return leave


@transactional
def approve_leave_request(
    leave_id: int,
    clinic_id: int,
    reviewer_user_id: int,
) -> LeaveRequest:
    """
    Approve a pending leave request.

    The operation is clinic-scoped and locked to prevent two
    administrators from approving the same request concurrently.
    """

    _ensure_active_clinic(clinic_id)

    leave = _get_leave_request(
        leave_id=leave_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if leave.status != LeaveStatus.PENDING:
        raise ConflictError(
            f"Leave request {leave_id} is already "
            f"'{leave.status.value}'"
        )

    reviewer = _get_user(
        user_id=reviewer_user_id,
        clinic_id=clinic_id,
    )

    if reviewer.role != Role.ADMIN:
        raise ValidationError(
            "Only an administrator can approve leave requests"
        )

    if not getattr(
        reviewer,
        "is_active",
        True,
    ):
        raise ValidationError(
            "Reviewer account is inactive"
        )

    if _has_overlapping_approved_leave(
        staff_id=leave.staff_id,
        start_date=leave.start_date,
        end_date=leave.end_date,
        exclude_leave_id=leave.id,
    ):
        raise ConflictError(
            f"Staff {leave.staff_id} already has "
            "approved leave overlapping this period"
        )

    old_status = leave.status.value

    leave.status = LeaveStatus.APPROVED
    leave.reviewed_by_user_id = reviewer.id
    leave.reviewed_at = _utcnow()

    today = date.today()

    if (
        leave.start_date <= today <= leave.end_date
    ):
        staff = _get_staff(
            staff_id=leave.staff_id,
            clinic_id=clinic_id,
            lock=True,
        )

        staff.status = StaffStatus.ON_LEAVE

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=(
            f"Leave request approved for "
            f"staff {leave.staff_id}"
        ),
        user_id=reviewer.id,
        old_value={
            "status": old_status,
        },
        new_value={
            "status": leave.status.value,
            "reviewed_by_user_id": reviewer.id,
        },
    )

    return leave


@transactional
def reject_leave_request(
    leave_id: int,
    clinic_id: int,
    reviewer_user_id: int,
    reason: Optional[str] = None,
) -> LeaveRequest:
    """
    Reject a pending leave request.
    """

    _ensure_active_clinic(clinic_id)

    leave = _get_leave_request(
        leave_id=leave_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if leave.status != LeaveStatus.PENDING:
        raise ConflictError(
            f"Leave request {leave_id} is already "
            f"'{leave.status.value}'"
        )

    reviewer = _get_user(
        user_id=reviewer_user_id,
        clinic_id=clinic_id,
    )

    if reviewer.role != Role.ADMIN:
        raise ValidationError(
            "Only an administrator can reject leave requests"
        )

    if not getattr(
        reviewer,
        "is_active",
        True,
    ):
        raise ValidationError(
            "Reviewer account is inactive"
        )

    normalized_reason = (
        reason.strip()
        if isinstance(reason, str)
        else reason
    )

    if normalized_reason is not None and not normalized_reason:
        raise ValidationError(
            "Rejection reason cannot be empty"
        )

    old_status = leave.status.value

    leave.status = LeaveStatus.REJECTED
    leave.reviewed_by_user_id = reviewer.id
    leave.reviewed_at = _utcnow()

    if normalized_reason:
        leave.reason = (
            f"{leave.reason}\n"
            f"Rejection note: {normalized_reason}"
        ).strip() if leave.reason else (
            f"Rejection note: {normalized_reason}"
        )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=(
            f"Leave request rejected for "
            f"staff {leave.staff_id}"
        ),
        user_id=reviewer.id,
        old_value={
            "status": old_status,
        },
        new_value={
            "status": leave.status.value,
            "reviewed_by_user_id": reviewer.id,
            "reason": normalized_reason,
        },
    )

    return leave


def restore_staff_from_expired_leave() -> int:
    """
    Restore staff whose approved leave periods have ended.

    Intended for scheduled execution.
    """

    today = date.today()

    on_leave_staff = (
        Staff.query
        .filter(
            Staff.status == StaffStatus.ON_LEAVE,
        )
        .all()
    )

    restored = 0

    for staff in on_leave_staff:
        still_on_leave = LeaveRequest.query.filter(
            LeaveRequest.staff_id == staff.id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        ).first()

        if still_on_leave is None:
            old_status = staff.status.value

            staff.status = StaffStatus.ACTIVE
            restored += 1

            create_audit_log(
                action=AuditAction.STATUS_CHANGE,
                entity_type="Staff",
                entity_id=staff.id,
                description=(
                    "Staff restored to active status "
                    "after approved leave ended"
                ),
                old_value={
                    "status": old_status,
                },
                new_value={
                    "status": StaffStatus.ACTIVE.value,
                },
            )

    db.session.commit()

    return restored


# ============================================================================
# PAYROLL
# ============================================================================

def get_payroll_record(
    record_id: int,
    clinic_id: Optional[int] = None,
) -> PayrollRecord:
    """
    Fetch payroll record through its staff member and enforce clinic
    ownership when clinic_id is supplied.
    """

    query = (
        PayrollRecord.query
        .join(
            Staff,
            Staff.id == PayrollRecord.staff_id,
        )
        .filter(
            PayrollRecord.id == record_id,
        )
    )

    if clinic_id is not None:
        query = query.filter(
            Staff.clinic_id == clinic_id,
        )

    record = query.first()

    if record is None:
        raise NotFoundError(
            f"Payroll record {record_id} not found"
        )

    return record


def list_payroll(
    clinic_id: int,
) -> list[PayrollRecord]:
    """
    List payroll records belonging to a clinic.
    """

    return (
        PayrollRecord.query
        .join(
            Staff,
            Staff.id == PayrollRecord.staff_id,
        )
        .filter(
            Staff.clinic_id == clinic_id,
        )
        .order_by(
            PayrollRecord.pay_period_start.desc(),
        )
        .all()
    )


def list_payroll_for_staff(
    clinic_id: int,
    staff_id: int,
) -> list[PayrollRecord]:
    """
    List payroll records for a clinic-owned staff member.
    """

    _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
    )

    return (
        PayrollRecord.query
        .filter(
            PayrollRecord.staff_id == staff_id,
        )
        .order_by(
            PayrollRecord.pay_period_start.desc(),
        )
        .all()
    )


@transactional
def create_payroll_record(
    clinic_id: int,
    staff_id: int,
    pay_period_start: date,
    pay_period_end: date,
    base_salary: Decimal,
    bonuses: Decimal = Decimal("0"),
    deductions: Decimal = Decimal("0"),
) -> PayrollRecord:
    """
    Create a payroll record for clinic-owned staff.
    """

    _ensure_active_clinic(clinic_id)

    staff = _get_staff(
        staff_id=staff_id,
        clinic_id=clinic_id,
        lock=True,
    )

    if pay_period_end < pay_period_start:
        raise ValidationError(
            "Pay period end cannot be before start"
        )

    base_salary = Decimal(base_salary)
    bonuses = Decimal(bonuses)
    deductions = Decimal(deductions)

    if base_salary < 0:
        raise ValidationError(
            "Base salary cannot be negative"
        )

    if bonuses < 0:
        raise ValidationError(
            "Bonuses cannot be negative"
        )

    if deductions < 0:
        raise ValidationError(
            "Deductions cannot be negative"
        )

    net_pay = (
        base_salary
        + bonuses
        - deductions
    )

    if net_pay < 0:
        raise ValidationError(
            "Net pay cannot be negative"
        )

    duplicate = PayrollRecord.query.filter(
        PayrollRecord.staff_id == staff.id,
        PayrollRecord.pay_period_start == pay_period_start,
        PayrollRecord.pay_period_end == pay_period_end,
    ).first()

    if duplicate is not None:
        raise ConflictError(
            "Payroll record already exists for "
            f"staff {staff.id} for this period"
        )

    record = PayrollRecord(
        staff_id=staff.id,
        pay_period_start=pay_period_start,
        pay_period_end=pay_period_end,
        base_salary=base_salary,
        bonuses=bonuses,
        deductions=deductions,
        net_pay=net_pay,
    )

    db.session.add(record)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PayrollRecord",
        entity_id=record.id,
        description=(
            f"Payroll record created for "
            f"staff {staff.id}"
        ),
        new_value={
            "clinic_id": clinic_id,
            "staff_id": staff.id,
            "pay_period_start": (
                pay_period_start.isoformat()
            ),
            "pay_period_end": (
                pay_period_end.isoformat()
            ),
            "base_salary": str(base_salary),
            "bonuses": str(bonuses),
            "deductions": str(deductions),
            "net_pay": str(net_pay),
        },
    )

    return record


@transactional
def generate_payroll_for_period(
    clinic_id: int,
    pay_period_start: date,
    pay_period_end: date,
    salary_lookup: dict[int, Decimal],
) -> list[PayrollRecord]:
    """
    Generate payroll for active staff in a clinic.

    salary_lookup maps staff IDs to base salaries.
    Existing records for the same period are skipped.
    """

    _ensure_active_clinic(clinic_id)

    if pay_period_end < pay_period_start:
        raise ValidationError(
            "Pay period end cannot be before start"
        )

    staff_list = list_staff(
        clinic_id=clinic_id,
        status=StaffStatus.ACTIVE,
    )

    created: list[PayrollRecord] = []
    skipped_staff_ids: list[int] = []

    for staff in staff_list:
        base_salary = salary_lookup.get(
            staff.id
        )

        if base_salary is None:
            skipped_staff_ids.append(
                staff.id
            )
            continue

        base_salary = Decimal(
            base_salary
        )

        if base_salary < 0:
            raise ValidationError(
                f"Base salary cannot be negative for staff {staff.id}"
            )

        existing = PayrollRecord.query.filter(
            PayrollRecord.staff_id == staff.id,
            PayrollRecord.pay_period_start == pay_period_start,
            PayrollRecord.pay_period_end == pay_period_end,
        ).first()

        if existing is not None:
            skipped_staff_ids.append(
                staff.id
            )
            continue

        record = PayrollRecord(
            staff_id=staff.id,
            pay_period_start=pay_period_start,
            pay_period_end=pay_period_end,
            base_salary=base_salary,
            bonuses=Decimal("0"),
            deductions=Decimal("0"),
            net_pay=base_salary,
        )

        db.session.add(record)
        created.append(record)

    db.session.flush()

    for record in created:
        create_audit_log(
            action=AuditAction.CREATE,
            entity_type="PayrollRecord",
            entity_id=record.id,
            description=(
                f"Payroll record generated for "
                f"staff {record.staff_id}"
            ),
            new_value={
                "clinic_id": clinic_id,
                "staff_id": record.staff_id,
                "pay_period_start": (
                    pay_period_start.isoformat()
                ),
                "pay_period_end": (
                    pay_period_end.isoformat()
                ),
                "net_pay": str(record.net_pay),
            },
        )

    return created


@transactional
def mark_payroll_paid(
    record_id: int,
    clinic_id: int,
) -> PayrollRecord:
    """
    Mark a clinic-owned payroll record as paid.
    """

    _ensure_active_clinic(clinic_id)

    record = get_payroll_record(
        record_id=record_id,
        clinic_id=clinic_id,
    )

    if record.paid_at is not None:
        raise ConflictError(
            f"Payroll record {record_id} "
            "is already marked paid"
        )

    record.paid_at = _utcnow()

    create_audit_log(
        action=AuditAction.PAYMENT,
        entity_type="PayrollRecord",
        entity_id=record.id,
        description=(
            f"Payroll marked paid for "
            f"staff {record.staff_id}"
        ),
        new_value={
            "net_pay": str(record.net_pay),
            "paid_at": record.paid_at.isoformat(),
        },
    )

    return record