from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.staff_enums import (
    LeaveStatus,
    LeaveType,
    StaffStatus,
)
from app.modules.clinic.services.clinic_service import ensure_clinic_active
from app.modules.staff.models.staff_model import (
    LeaveRequest,
    PayrollRecord,
    Staff,
)


_EDITABLE_STAFF_FIELDS = {
    "first_name",
    "last_name",
    "specialty",
    "phone",
    "email",
    "hired_at",
}


def _utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------


def _get_staff(staff_id: int, lock: bool = False) -> Staff:
    query = Staff.query.filter_by(id=staff_id)

    if lock:
        query = query.with_for_update()

    staff = query.first()

    if staff is None:
        raise NotFoundError(f"Staff {staff_id} not found")

    return staff


def _get_leave_request(leave_id: int, lock: bool = False) -> LeaveRequest:
    query = LeaveRequest.query.filter_by(id=leave_id)

    if lock:
        query = query.with_for_update()

    leave = query.first()

    if leave is None:
        raise NotFoundError(f"Leave request {leave_id} not found")

    return leave


def _get_payroll_record(
    record_id: int,
    lock: bool = False,
) -> PayrollRecord:
    query = PayrollRecord.query.filter_by(id=record_id)

    if lock:
        query = query.with_for_update()

    record = query.first()

    if record is None:
        raise NotFoundError(f"Payroll record {record_id} not found")

    return record


def _ensure_staff_clinic_active(staff: Staff) -> None:
    """
    Ensure the clinic owning the staff member is currently active.

    Historical reads deliberately do not call this helper.
    """
    ensure_clinic_active(staff.clinic_id)


def _validate_staff_name(first_name: str, last_name: str) -> tuple[str, str]:
    if not first_name or not first_name.strip():
        raise ValidationError("First name is required")

    if not last_name or not last_name.strip():
        raise ValidationError("Last name is required")

    return first_name.strip(), last_name.strip()


def _validate_staff_fields(fields: dict) -> None:
    unknown = set(fields) - _EDITABLE_STAFF_FIELDS - {"user_id"}

    if unknown:
        raise ValidationError(
            f"Unknown staff field(s): {', '.join(sorted(unknown))}"
        )


def _validate_leave_dates(
    start_date: date,
    end_date: date,
) -> None:
    if end_date < start_date:
        raise ValidationError(
            "Leave end date cannot be before start date"
        )


def _validate_pay_period(
    pay_period_start: date,
    pay_period_end: date,
) -> None:
    if pay_period_end < pay_period_start:
        raise ValidationError(
            "Pay period end cannot be before start"
        )


def _to_decimal(value, field_name: str) -> Decimal:
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            f"{field_name} must be a valid decimal amount"
        )

    if not decimal_value.is_finite():
        raise ValidationError(
            f"{field_name} must be a finite decimal amount"
        )

    return decimal_value


def _validate_payroll_amounts(
    base_salary: Decimal,
    bonuses: Decimal,
    deductions: Decimal,
) -> Decimal:
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

    net_pay = base_salary + bonuses - deductions

    if net_pay < 0:
        raise ValidationError(
            "Deductions cannot exceed gross pay"
        )

    return net_pay


def _validate_leave_reviewer(
    leave: LeaveRequest,
    reviewed_by_id: int,
) -> Staff:
    reviewer = _get_staff(reviewed_by_id)

    if reviewer.clinic_id != leave.staff.clinic_id:
        raise ValidationError(
            "Leave reviewer must belong to the same clinic as the staff member"
        )

    if reviewer.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Leave reviewer Staff {reviewer.id} must be active"
        )

    _ensure_staff_clinic_active(leave.staff)

    return reviewer


def _has_overlapping_approved_leave(
    staff_id: int,
    start_date: date,
    end_date: date,
    exclude_leave_id: int | None = None,
) -> bool:
    query = LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )

    if exclude_leave_id is not None:
        query = query.filter(
            LeaveRequest.id != exclude_leave_id
        )

    return query.first() is not None


# ---------------------------------------------------------------------
# Staff core - READ
# ---------------------------------------------------------------------


def get_staff(staff_id: int) -> Staff:
    """
    Retrieve staff regardless of clinic status.

    Staff belonging to inactive or suspended clinics remain historically
    accessible.
    """
    return _get_staff(staff_id)


def list_staff(
    clinic_id: int | None = None,
    status: StaffStatus | None = None,
    search: str | None = None,
) -> list[Staff]:
    """
    List staff.

    This is a read operation and therefore does not require the clinic
    to be active.
    """
    query = Staff.query

    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)

    if status is not None:
        query = query.filter_by(status=status)

    if search:
        search_term = search.strip()

        if search_term:
            like = f"%{search_term}%"

            query = query.filter(
                db.or_(
                    Staff.first_name.ilike(like),
                    Staff.last_name.ilike(like),
                )
            )

    return query.order_by(
        Staff.last_name,
        Staff.first_name,
    ).all()


# ---------------------------------------------------------------------
# Staff core - WRITE
# ---------------------------------------------------------------------


@transactional
def create_staff(
    clinic_id: int,
    first_name: str,
    last_name: str,
    **fields,
) -> Staff:
    """
    Create a staff member.

    A staff member can only be created under an ACTIVE clinic.
    """
    ensure_clinic_active(clinic_id)

    first_name, last_name = _validate_staff_name(
        first_name,
        last_name,
    )

    _validate_staff_fields(fields)

    user_id = fields.pop("user_id", None)

    if user_id is not None:
        existing = Staff.query.filter_by(
            user_id=user_id
        ).first()

        if existing:
            raise ConflictError(
                f"User {user_id} is already linked to "
                f"staff {existing.id}"
            )

    staff = Staff(
        clinic_id=clinic_id,
        first_name=first_name,
        last_name=last_name,
        user_id=user_id,
        status=StaffStatus.ACTIVE,
        **fields,
    )

    db.session.add(staff)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Staff",
        entity_id=staff.id,
        description=(
            f"Staff '{staff.first_name} "
            f"{staff.last_name}' created"
        ),
        new_value={
            "clinic_id": clinic_id,
            "user_id": user_id,
            "status": staff.status.value,
        },
    )

    return staff


@transactional
def update_staff(
    staff_id: int,
    **fields,
) -> Staff:
    """
    Update editable staff information.

    Staff belonging to inactive/suspended clinics cannot be modified.
    """
    staff = _get_staff(staff_id)

    _ensure_staff_clinic_active(staff)

    unknown = set(fields) - _EDITABLE_STAFF_FIELDS

    if unknown:
        raise ValidationError(
            f"Unknown staff field(s): "
            f"{', '.join(sorted(unknown))}"
        )

    if "first_name" in fields:
        if not fields["first_name"] or not fields["first_name"].strip():
            raise ValidationError("First name is required")

        fields["first_name"] = fields["first_name"].strip()

    if "last_name" in fields:
        if not fields["last_name"] or not fields["last_name"].strip():
            raise ValidationError("Last name is required")

        fields["last_name"] = fields["last_name"].strip()

    old_value = {}
    new_value = {}

    for key, new_val in fields.items():
        current_val = getattr(staff, key)

        if current_val == new_val:
            continue

        old_value[key] = (
            current_val.value
            if hasattr(current_val, "value")
            else current_val
        )

        new_value[key] = (
            new_val.value
            if hasattr(new_val, "value")
            else new_val
        )

        setattr(staff, key, new_val)

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
    new_status: StaffStatus,
) -> Staff:
    """
    Manually change StaffStatus.

    Normal Staff status changes require the owning clinic to be active.

    ON_LEAVE is normally managed by the leave workflow, but this method
    intentionally allows manual HR correction.
    """
    staff = _get_staff(
        staff_id,
        lock=True,
    )

    _ensure_staff_clinic_active(staff)

    if staff.status == new_status:
        return staff

    old_status = staff.status.value

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


# ---------------------------------------------------------------------
# Leave requests - READ
# ---------------------------------------------------------------------


def get_leave_request(
    leave_id: int,
) -> LeaveRequest:
    """
    Retrieve leave history regardless of clinic status.
    """
    return _get_leave_request(leave_id)


def list_leave_requests(
    staff_id: int | None = None,
    status: LeaveStatus | None = None,
) -> list[LeaveRequest]:
    """
    List leave requests.

    Historical leave remains readable even when a clinic is inactive
    or suspended.
    """
    query = LeaveRequest.query

    if staff_id is not None:
        query = query.filter_by(
            staff_id=staff_id
        )

    if status is not None:
        query = query.filter_by(
            status=status
        )

    return query.order_by(
        LeaveRequest.start_date.desc()
    ).all()


# ---------------------------------------------------------------------
# Leave requests - WRITE
# ---------------------------------------------------------------------


@transactional
def request_leave(
    staff_id: int,
    leave_type: LeaveType,
    start_date: date,
    end_date: date,
    reason: str | None = None,
) -> LeaveRequest:
    """
    Request leave for a staff member.

    Leave requests are operational HR writes and therefore require the
    staff member's clinic to be active.
    """
    staff = _get_staff(
        staff_id,
        lock=True,
    )

    _ensure_staff_clinic_active(staff)

    if staff.status in {
        StaffStatus.TERMINATED,
        StaffStatus.SUSPENDED,
    }:
        raise ValidationError(
            f"Staff {staff.id} cannot request leave "
            f"while status is '{staff.status.value}'"
        )

    _validate_leave_dates(
        start_date,
        end_date,
    )

    leave = LeaveRequest(
        staff_id=staff.id,
        leave_type=leave_type,
        status=LeaveStatus.PENDING,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
    )

    db.session.add(leave)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=(
            f"Leave requested for staff {staff.id} "
            f"({leave_type.value}, "
            f"{start_date} to {end_date})"
        ),
        new_value={
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
    reviewed_by_id: int,
) -> LeaveRequest:
    """
    Approve a pending leave request.

    The leave owner and reviewer must belong to the same active clinic.
    """
    leave = _get_leave_request(
        leave_id,
        lock=True,
    )

    staff = _get_staff(
        leave.staff_id,
        lock=True,
    )

    _ensure_staff_clinic_active(staff)

    if leave.status != LeaveStatus.PENDING:
        raise ConflictError(
            f"Leave request {leave.id} is already "
            f"'{leave.status.value}'"
        )

    reviewer = _validate_leave_reviewer(
        leave,
        reviewed_by_id,
    )

    if _has_overlapping_approved_leave(
        staff_id=staff.id,
        start_date=leave.start_date,
        end_date=leave.end_date,
        exclude_leave_id=leave.id,
    ):
        raise ConflictError(
            f"Staff {staff.id} already has approved "
            f"leave overlapping this period"
        )

    leave.status = LeaveStatus.APPROVED
    leave.reviewed_by_id = reviewer.id
    leave.reviewed_at = _utcnow()

    today = date.today()

    if (
        leave.start_date <= today <= leave.end_date
        and staff.status == StaffStatus.ACTIVE
    ):
        old_staff_status = staff.status.value

        staff.status = StaffStatus.ON_LEAVE

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Staff",
            entity_id=staff.id,
            description=(
                f"Staff {staff.id} placed on leave "
                f"after leave request {leave.id} "
                f"was approved"
            ),
            old_value={
                "status": old_staff_status,
            },
            new_value={
                "status": StaffStatus.ON_LEAVE.value,
            },
        )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=(
            f"Leave request approved for "
            f"staff {staff.id}"
        ),
        new_value={
            "status": leave.status.value,
            "reviewed_by_id": reviewer.id,
        },
    )

    return leave


@transactional
def reject_leave_request(
    leave_id: int,
    reviewed_by_id: int,
    reason: str | None = None,
) -> LeaveRequest:
    """
    Reject a pending leave request.

    The leave owner and reviewer must belong to the same active clinic.
    """
    leave = _get_leave_request(
        leave_id,
        lock=True,
    )

    staff = _get_staff(
        leave.staff_id,
        lock=True,
    )

    _ensure_staff_clinic_active(staff)

    if leave.status != LeaveStatus.PENDING:
        raise ConflictError(
            f"Leave request {leave.id} is already "
            f"'{leave.status.value}'"
        )

    reviewer = _validate_leave_reviewer(
        leave,
        reviewed_by_id,
    )

    leave.status = LeaveStatus.REJECTED
    leave.reviewed_by_id = reviewer.id
    leave.reviewed_at = _utcnow()

    if reason:
        leave.reason = (
            f"{leave.reason or ''}\n"
            f"Rejection note: {reason}"
        ).strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=(
            f"Leave request rejected for "
            f"staff {staff.id}"
            + (f": {reason}" if reason else "")
        ),
        new_value={
            "status": leave.status.value,
            "reviewed_by_id": reviewer.id,
        },
    )

    return leave


def restore_staff_from_expired_leave() -> int:
    """
    Restore Staff members from ON_LEAVE after their approved leave ends.

    This is an automated HR state reconciliation rather than a new
    operational activity. Therefore it deliberately does NOT require
    the clinic to be ACTIVE.

    Example:

        Clinic = SUSPENDED
        Staff  = ON_LEAVE
        Leave expires
                ↓
        Staff = ACTIVE

    The clinic's own status still prevents operational writes elsewhere.
    """
    today = date.today()

    on_leave_staff = (
        Staff.query
        .filter_by(status=StaffStatus.ON_LEAVE)
        .with_for_update()
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

        if still_on_leave:
            continue

        staff.status = StaffStatus.ACTIVE
        restored += 1

        create_audit_log(
            action=AuditAction.STATUS_CHANGE,
            entity_type="Staff",
            entity_id=staff.id,
            description=(
                "Staff restored to active status "
                "(leave period ended, automated)"
            ),
            new_value={
                "status": StaffStatus.ACTIVE.value,
            },
        )

    db.session.commit()

    return restored


# ---------------------------------------------------------------------
# Payroll - READ
# ---------------------------------------------------------------------


def get_payroll_record(
    record_id: int,
) -> PayrollRecord:
    """
    Retrieve payroll history regardless of clinic status.
    """
    return _get_payroll_record(record_id)


def list_payroll_for_staff(
    staff_id: int,
) -> list[PayrollRecord]:
    """
    List payroll history regardless of clinic status.
    """
    return (
        PayrollRecord.query
        .filter_by(staff_id=staff_id)
        .order_by(
            PayrollRecord.pay_period_start.desc()
        )
        .all()
    )


# ---------------------------------------------------------------------
# Payroll - WRITE
# ---------------------------------------------------------------------


@transactional
def create_payroll_record(
    staff_id: int,
    pay_period_start: date,
    pay_period_end: date,
    base_salary: Decimal,
    bonuses: Decimal = Decimal("0"),
    deductions: Decimal = Decimal("0"),
) -> PayrollRecord:
    """
    Create payroll for one Staff member.

    Payroll writes require the Staff member's clinic to be active.
    """
    staff = _get_staff(
        staff_id,
        lock=True,
    )

    _ensure_staff_clinic_active(staff)

    _validate_pay_period(
        pay_period_start,
        pay_period_end,
    )

    base_salary = _to_decimal(
        base_salary,
        "Base salary",
    )

    bonuses = _to_decimal(
        bonuses,
        "Bonuses",
    )

    deductions = _to_decimal(
        deductions,
        "Deductions",
    )

    net_pay = _validate_payroll_amounts(
        base_salary,
        bonuses,
        deductions,
    )

    duplicate = PayrollRecord.query.filter_by(
        staff_id=staff.id,
        pay_period_start=pay_period_start,
        pay_period_end=pay_period_end,
    ).first()

    if duplicate:
        raise ConflictError(
            f"Payroll record already exists for "
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
            f"Payroll record created for staff "
            f"{staff.id} "
            f"({pay_period_start} to {pay_period_end})"
        ),
        new_value={
            "staff_id": staff.id,
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
    Generate payroll for ACTIVE staff in one clinic.

    Staff already having a payroll record for the exact period are
    skipped.

    The clinic itself must be ACTIVE.
    """
    ensure_clinic_active(clinic_id)

    _validate_pay_period(
        pay_period_start,
        pay_period_end,
    )

    if not isinstance(salary_lookup, dict):
        raise ValidationError(
            "salary_lookup must be a dictionary"
        )

    staff_list = (
        Staff.query
        .filter_by(
            clinic_id=clinic_id,
            status=StaffStatus.ACTIVE,
        )
        .with_for_update()
        .all()
    )

    created: list[PayrollRecord] = []
    skipped: list[int] = []

    for staff in staff_list:
        raw_base_salary = salary_lookup.get(staff.id)

        if raw_base_salary is None:
            skipped.append(staff.id)
            continue

        base_salary = _to_decimal(
            raw_base_salary,
            f"Base salary for staff {staff.id}",
        )

        bonuses = Decimal("0")
        deductions = Decimal("0")

        net_pay = _validate_payroll_amounts(
            base_salary,
            bonuses,
            deductions,
        )

        existing = PayrollRecord.query.filter_by(
            staff_id=staff.id,
            pay_period_start=pay_period_start,
            pay_period_end=pay_period_end,
        ).first()

        if existing:
            skipped.append(staff.id)
            continue

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
        created.append(record)

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PayrollRecord",
        entity_id=0,
        description=(
            f"Batch payroll generated for clinic "
            f"{clinic_id} "
            f"({pay_period_start} to {pay_period_end})"
        ),
        new_value={
            "clinic_id": clinic_id,
            "created_count": len(created),
            "skipped_staff_ids": skipped,
        },
    )

    return created


@transactional
def mark_payroll_paid(
    record_id: int,
) -> PayrollRecord:
    """
    Mark a payroll record as paid.

    Historical payroll remains readable, but changing its payment state
    requires the owning clinic to be active.
    """
    record = _get_payroll_record(
        record_id,
        lock=True,
    )

    staff = _get_staff(
        record.staff_id,
        lock=True,
    )

    _ensure_staff_clinic_active(staff)

    if record.paid_at is not None:
        raise ConflictError(
            f"Payroll record {record.id} is already marked paid"
        )

    record.paid_at = _utcnow()

    create_audit_log(
        action=AuditAction.PAYMENT,
        entity_type="PayrollRecord",
        entity_id=record.id,
        description=(
            f"Payroll marked paid for staff "
            f"{staff.id}"
        ),
        new_value={
            "net_pay": str(record.net_pay),
            "paid_at": record.paid_at.isoformat(),
        },
    )

    return record