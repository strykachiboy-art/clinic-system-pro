from datetime import date
from decimal import Decimal
from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, ConflictError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.staff_enums import StaffStatus, LeaveType, LeaveStatus
from app.modules.staff.models.staff_model import Staff, PayrollRecord, LeaveRequest

_EDITABLE_STAFF_FIELDS = {
    "first_name", "last_name", "specialty", "phone", "email", "hired_at",
}


# ---------------------------------------------------------------------
# Staff core
# ---------------------------------------------------------------------

def get_staff(staff_id: int) -> Staff:
    staff = Staff.query.get(staff_id)
    if staff is None:
        raise NotFoundError(f"Staff {staff_id} not found")
    return staff


def list_staff(clinic_id: int | None = None,
               status: StaffStatus | None = None, search: str | None = None) -> list[Staff]:
    query = Staff.query
    if clinic_id is not None:
        query = query.filter_by(clinic_id=clinic_id)
    if status is not None:
        query = query.filter_by(status=status)
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(db.or_(Staff.first_name.ilike(like), Staff.last_name.ilike(like)))
    return query.order_by(Staff.last_name, Staff.first_name).all()



@transactional
def create_staff(clinic_id: int, first_name: str, last_name: str, **fields) -> Staff:
    if not first_name or not first_name.strip():
        raise ValidationError("First name is required")
    if not last_name or not last_name.strip():
        raise ValidationError("Last name is required")

    unknown = set(fields) - _EDITABLE_STAFF_FIELDS - {"user_id"}
    if unknown:
        raise ValidationError(f"Unknown staff field(s): {', '.join(sorted(unknown))}")

    user_id = fields.pop("user_id", None)
    if user_id is not None:
        existing = Staff.query.filter_by(user_id=user_id).first()
        if existing:
            raise ConflictError(f"User {user_id} is already linked to staff {existing.id}")

    staff = Staff(
        clinic_id=clinic_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
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
        description=f"Staff '{staff.first_name} {staff.last_name}' created",
    )
    return staff


@transactional
def update_staff(staff_id: int, **fields) -> Staff:
    staff = get_staff(staff_id)

    unknown = set(fields) - _EDITABLE_STAFF_FIELDS
    if unknown:
        raise ValidationError(f"Unknown staff field(s): {', '.join(sorted(unknown))}")

    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(staff, key)
        if current_val != new_val:
            old_value[key] = current_val.value if hasattr(current_val, "value") else current_val
            new_value[key] = new_val.value if hasattr(new_val, "value") else new_val
            setattr(staff, key, new_val)

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Staff",
            entity_id=staff.id,
            description=f"Staff '{staff.first_name} {staff.last_name}' updated",
            old_value=old_value,
            new_value=new_value,
        )
    return staff


@transactional
def change_staff_status(staff_id: int, new_status: StaffStatus) -> Staff:
    """
    Direct manual override (e.g. suspend, terminate). ON_LEAVE should
    normally be set via approve_leave_request(), not called directly
    here — but not hard-blocked, since HR may need to correct it manually.
    """
    staff = get_staff(staff_id)
    if staff.status == new_status:
        return staff

    old_status = staff.status.value
    staff.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Staff",
        entity_id=staff.id,
        description=f"Staff status changed to '{new_status.value}'",
        old_value={"status": old_status},
        new_value={"status": new_status.value},
    )
    return staff


# ---------------------------------------------------------------------
# Leave requests
# ---------------------------------------------------------------------

def get_leave_request(leave_id: int) -> LeaveRequest:
    leave = LeaveRequest.query.get(leave_id)
    if leave is None:
        raise NotFoundError(f"Leave request {leave_id} not found")
    return leave


def list_leave_requests(staff_id: int | None = None, status: LeaveStatus | None = None) -> list[LeaveRequest]:
    query = LeaveRequest.query
    if staff_id is not None:
        query = query.filter_by(staff_id=staff_id)
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(LeaveRequest.start_date.desc()).all()


def _has_overlapping_approved_leave(staff_id: int, start_date: date, end_date: date,
                                     exclude_leave_id: int | None = None) -> bool:
    query = LeaveRequest.query.filter(
        LeaveRequest.staff_id == staff_id,
        LeaveRequest.status == LeaveStatus.APPROVED,
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )
    if exclude_leave_id is not None:
        query = query.filter(LeaveRequest.id != exclude_leave_id)
    return query.first() is not None


@transactional
def request_leave(staff_id: int, leave_type: LeaveType, start_date: date, end_date: date,
                   reason: str | None = None) -> LeaveRequest:
    get_staff(staff_id)

    if end_date < start_date:
        raise ValidationError("Leave end date cannot be before start date")

    leave = LeaveRequest(
        staff_id=staff_id,
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
        description=f"Leave requested for staff {staff_id} ({leave_type.value}, {start_date} to {end_date})",
        new_value={"leave_type": leave_type.value, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    )
    return leave


@transactional
def approve_leave_request(leave_id: int, reviewed_by_id: int) -> LeaveRequest:
    leave = get_leave_request(leave_id)
    if leave.status != LeaveStatus.PENDING:
        raise ConflictError(f"Leave request {leave_id} is already '{leave.status.value}'")

    if _has_overlapping_approved_leave(leave.staff_id, leave.start_date, leave.end_date, exclude_leave_id=leave.id):
        raise ConflictError(f"Staff {leave.staff_id} already has approved leave overlapping this period")

    leave.status = LeaveStatus.APPROVED
    leave.reviewed_by_id = reviewed_by_id
    leave.reviewed_at = db.func.now()

    today = date.today()
    if leave.start_date <= today <= leave.end_date:
        leave.staff.status = StaffStatus.ON_LEAVE

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=f"Leave request approved for staff {leave.staff_id}",
        new_value={"status": leave.status.value},
    )
    return leave


@transactional
def reject_leave_request(leave_id: int, reviewed_by_id: int, reason: str | None = None) -> LeaveRequest:
    leave = get_leave_request(leave_id)
    if leave.status != LeaveStatus.PENDING:
        raise ConflictError(f"Leave request {leave_id} is already '{leave.status.value}'")

    leave.status = LeaveStatus.REJECTED
    leave.reviewed_by_id = reviewed_by_id
    leave.reviewed_at = db.func.now()
    if reason:
        leave.reason = f"{leave.reason or ''}\nRejection note: {reason}".strip()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="LeaveRequest",
        entity_id=leave.id,
        description=f"Leave request rejected for staff {leave.staff_id}" + (f": {reason}" if reason else ""),
        new_value={"status": leave.status.value},
    )
    return leave


def restore_staff_from_expired_leave() -> int:
    """
    Run daily via Celery beat (same pattern as
    billing_service.mark_overdue_invoices). Reverts ON_LEAVE staff back
    to ACTIVE once their approved leave period has ended and they have
    no other current approved leave.
    """
    today = date.today()
    on_leave_staff = Staff.query.filter_by(status=StaffStatus.ON_LEAVE).all()

    restored = 0
    for staff in on_leave_staff:
        still_on_leave = LeaveRequest.query.filter(
            LeaveRequest.staff_id == staff.id,
            LeaveRequest.status == LeaveStatus.APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        ).first()

        if not still_on_leave:
            staff.status = StaffStatus.ACTIVE
            restored += 1
            create_audit_log(
                action=AuditAction.STATUS_CHANGE,
                entity_type="Staff",
                entity_id=staff.id,
                description="Staff restored to active status (leave period ended, automated)",
                new_value={"status": "active"},
            )

    db.session.commit()
    return restored


# ---------------------------------------------------------------------
# Payroll
# ---------------------------------------------------------------------

def get_payroll_record(record_id: int) -> PayrollRecord:
    record = PayrollRecord.query.get(record_id)
    if record is None:
        raise NotFoundError(f"Payroll record {record_id} not found")
    return record


def list_payroll_for_staff(staff_id: int) -> list[PayrollRecord]:
    return (
        PayrollRecord.query.filter_by(staff_id=staff_id)
        .order_by(PayrollRecord.pay_period_start.desc())
        .all()
    )


@transactional
def create_payroll_record(staff_id: int, pay_period_start: date, pay_period_end: date,
                           base_salary: Decimal, bonuses: Decimal = Decimal("0"),
                           deductions: Decimal = Decimal("0")) -> PayrollRecord:
    get_staff(staff_id)

    if pay_period_end < pay_period_start:
        raise ValidationError("Pay period end cannot be before start")
    if base_salary < 0:
        raise ValidationError("Base salary cannot be negative")

    duplicate = PayrollRecord.query.filter_by(
        staff_id=staff_id, pay_period_start=pay_period_start, pay_period_end=pay_period_end
    ).first()
    if duplicate:
        raise ConflictError(f"Payroll record already exists for staff {staff_id} for this period")

    net_pay = Decimal(base_salary) + Decimal(bonuses) - Decimal(deductions)

    record = PayrollRecord(
        staff_id=staff_id,
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
        description=f"Payroll record created for staff {staff_id} ({pay_period_start} to {pay_period_end})",
        new_value={"net_pay": str(net_pay)},
    )
    return record


@transactional
def generate_payroll_for_period(clinic_id: int, pay_period_start: date, pay_period_end: date,
                                 salary_lookup: dict[int, Decimal]) -> list[PayrollRecord]:
    """
    Batch-generates payroll for every ACTIVE staff member in a clinic
    for one period. salary_lookup maps staff_id -> base_salary, since
    Staff has no salary/compensation field to read from automatically.
    Staff already having a record for this exact period are skipped.
    """
    staff_list = list_staff(clinic_id=clinic_id, status=StaffStatus.ACTIVE)

    created = []
    skipped = []
    for staff in staff_list:
        base_salary = salary_lookup.get(staff.id)
        if base_salary is None:
            skipped.append(staff.id)
            continue

        existing = PayrollRecord.query.filter_by(
            staff_id=staff.id, pay_period_start=pay_period_start, pay_period_end=pay_period_end
        ).first()
        if existing:
            skipped.append(staff.id)
            continue

        net_pay = Decimal(base_salary)
        record = PayrollRecord(
            staff_id=staff.id,
            pay_period_start=pay_period_start,
            pay_period_end=pay_period_end,
            base_salary=base_salary,
            bonuses=Decimal("0"),
            deductions=Decimal("0"),
            net_pay=net_pay,
        )
        db.session.add(record)
        created.append(record)

    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="PayrollRecord",
        entity_id=0,
        description=f"Batch payroll generated for clinic {clinic_id} ({pay_period_start} to {pay_period_end})",
        new_value={"created_count": len(created), "skipped_staff_ids": skipped},
    )
    return created


@transactional
def mark_payroll_paid(record_id: int) -> PayrollRecord:
    record = get_payroll_record(record_id)
    if record.paid_at is not None:
        raise ConflictError(f"Payroll record {record_id} is already marked paid")

    record.paid_at = db.func.now()

    create_audit_log(
        action=AuditAction.PAYMENT,
        entity_type="PayrollRecord",
        entity_id=record.id,
        description=f"Payroll marked paid for staff {record.staff_id}",
        new_value={"net_pay": str(record.net_pay)},
    )
    return record