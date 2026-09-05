from flask import Blueprint, jsonify, request

from app.core.enums.role_enums import Role
from app.core.utils.decorators import role_required

from app.modules.staff.schemas.staff_schema import (
    LeaveListQuerySchema,
    LeaveRejectSchema,
    LeaveRequestCreateSchema,
    LeaveReviewSchema,
    PayrollCreateSchema,
    PayrollGenerateSchema,
    PayrollListQuerySchema,
    StaffCreateSchema,
    StaffListQuerySchema,
    StaffStatusUpdateSchema,
    StaffUpdateSchema,
)

from app.modules.staff.services.staff_service import (
    approve_leave_request,
    change_staff_status,
    create_payroll_record,
    create_staff,
    generate_payroll_for_period,
    get_leave_request,
    get_payroll_record,
    get_staff,
    list_leave_requests,
    list_payroll_for_staff,
    list_staff,
    mark_payroll_paid,
    reject_leave_request,
    request_leave,
    update_staff,
)


staff_bp = Blueprint(
    "staff",
    __name__,
    url_prefix="/api/staff",
)


# ============================================================================
# ROLE GROUPS
# ============================================================================

MANAGEMENT_ROLES = (
    Role.ADMIN,
)

STAFF_VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.RECEPTIONIST,
)

LEAVE_MANAGEMENT_ROLES = (
    Role.ADMIN,
)

PAYROLL_ROLES = (
    Role.ADMIN,
    Role.ACCOUNTANT,
)


# ============================================================================
# SERIALIZERS
# ============================================================================


def _serialize_staff(staff):
    return {
        "id": staff.id,
        "clinic_id": staff.clinic_id,
        "user_id": staff.user_id,
        "first_name": staff.first_name,
        "last_name": staff.last_name,
        "specialty": staff.specialty,
        "phone": staff.phone,
        "email": staff.email,
        "status": staff.status.value,
        "hired_at": (
            staff.hired_at.isoformat()
            if staff.hired_at
            else None
        ),
        "created_at": (
            staff.created_at.isoformat()
            if staff.created_at
            else None
        ),
        "updated_at": (
            staff.updated_at.isoformat()
            if staff.updated_at
            else None
        ),
    }


def _serialize_leave(leave):
    return {
        "id": leave.id,
        "staff_id": leave.staff_id,
        "leave_type": leave.leave_type.value,
        "status": leave.status.value,
        "start_date": leave.start_date.isoformat(),
        "end_date": leave.end_date.isoformat(),
        "reason": leave.reason,
        "reviewed_by_id": leave.reviewed_by_id,
        "reviewed_at": (
            leave.reviewed_at.isoformat()
            if leave.reviewed_at
            else None
        ),
        "created_at": (
            leave.created_at.isoformat()
            if leave.created_at
            else None
        ),
        "updated_at": (
            leave.updated_at.isoformat()
            if leave.updated_at
            else None
        ),
    }


def _serialize_payroll(record):
    return {
        "id": record.id,
        "staff_id": record.staff_id,
        "pay_period_start": record.pay_period_start.isoformat(),
        "pay_period_end": record.pay_period_end.isoformat(),
        "base_salary": str(record.base_salary),
        "bonuses": str(record.bonuses),
        "deductions": str(record.deductions),
        "net_pay": str(record.net_pay),
        "paid_at": (
            record.paid_at.isoformat()
            if record.paid_at
            else None
        ),
        "created_at": (
            record.created_at.isoformat()
            if record.created_at
            else None
        ),
        "updated_at": (
            record.updated_at.isoformat()
            if record.updated_at
            else None
        ),
    }


# ============================================================================
# STAFF
# ============================================================================


@staff_bp.post("")
@role_required(*MANAGEMENT_ROLES)
def create_staff_route():
    payload = StaffCreateSchema.model_validate(
        request.get_json() or {}
    )

    staff = create_staff(
        clinic_id=payload.clinic_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        user_id=payload.user_id,
        specialty=payload.specialty,
        phone=payload.phone,
        email=payload.email,
        hired_at=payload.hired_at,
    )

    return jsonify({
        "message": "Staff created successfully",
        "data": _serialize_staff(staff),
    }), 201


@staff_bp.get("")
@role_required(*STAFF_VIEW_ROLES)
def list_staff_route():
    payload = StaffListQuerySchema.model_validate(
        request.args.to_dict()
    )

    staff = list_staff(
        clinic_id=payload.clinic_id,
        status=payload.status,
        search=payload.search,
    )

    return jsonify({
        "data": [
            _serialize_staff(item)
            for item in staff
        ],
    }), 200


@staff_bp.get("/<int:staff_id>")
@role_required(*STAFF_VIEW_ROLES)
def get_staff_route(staff_id: int):
    staff = get_staff(staff_id)

    return jsonify({
        "data": _serialize_staff(staff),
    }), 200


@staff_bp.patch("/<int:staff_id>")
@role_required(*MANAGEMENT_ROLES)
def update_staff_route(staff_id: int):
    payload = StaffUpdateSchema.model_validate(
        request.get_json() or {}
    )

    fields = payload.model_dump(
        exclude_unset=True,
    )

    staff = update_staff(
        staff_id=staff_id,
        **fields,
    )

    return jsonify({
        "message": "Staff updated successfully",
        "data": _serialize_staff(staff),
    }), 200


@staff_bp.patch("/<int:staff_id>/status")
@role_required(*MANAGEMENT_ROLES)
def change_staff_status_route(staff_id: int):
    payload = StaffStatusUpdateSchema.model_validate(
        request.get_json() or {}
    )

    staff = change_staff_status(
        staff_id=staff_id,
        new_status=payload.status,
    )

    return jsonify({
        "message": "Staff status updated successfully",
        "data": _serialize_staff(staff),
    }), 200


# ============================================================================
# LEAVE REQUESTS
# ============================================================================


@staff_bp.post("/leaves")
@role_required(*STAFF_VIEW_ROLES)
def request_leave_route():
    payload = LeaveRequestCreateSchema.model_validate(
        request.get_json() or {}
    )

    leave = request_leave(
        staff_id=payload.staff_id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Leave request submitted successfully",
        "data": _serialize_leave(leave),
    }), 201


@staff_bp.get("/leaves")
@role_required(*STAFF_VIEW_ROLES)
def list_leave_requests_route():
    payload = LeaveListQuerySchema.model_validate(
        request.args.to_dict()
    )

    leaves = list_leave_requests(
        staff_id=payload.staff_id,
        status=payload.status,
    )

    return jsonify({
        "data": [
            _serialize_leave(leave)
            for leave in leaves
        ],
    }), 200


@staff_bp.get("/leaves/<int:leave_id>")
@role_required(*STAFF_VIEW_ROLES)
def get_leave_request_route(leave_id: int):
    leave = get_leave_request(leave_id)

    return jsonify({
        "data": _serialize_leave(leave),
    }), 200


@staff_bp.post("/leaves/<int:leave_id>/approve")
@role_required(*LEAVE_MANAGEMENT_ROLES)
def approve_leave_request_route(leave_id: int):
    payload = LeaveReviewSchema.model_validate(
        request.get_json() or {}
    )

    leave = approve_leave_request(
        leave_id=leave_id,
        reviewed_by_id=payload.reviewed_by_id,
    )

    return jsonify({
        "message": "Leave request approved successfully",
        "data": _serialize_leave(leave),
    }), 200


@staff_bp.post("/leaves/<int:leave_id>/reject")
@role_required(*LEAVE_MANAGEMENT_ROLES)
def reject_leave_request_route(leave_id: int):
    payload = LeaveRejectSchema.model_validate(
        request.get_json() or {}
    )

    leave = reject_leave_request(
        leave_id=leave_id,
        reviewed_by_id=payload.reviewed_by_id,
        reason=payload.reason,
    )

    return jsonify({
        "message": "Leave request rejected successfully",
        "data": _serialize_leave(leave),
    }), 200


# ============================================================================
# PAYROLL
# ============================================================================


@staff_bp.post("/payroll")
@role_required(*PAYROLL_ROLES)
def create_payroll_record_route():
    payload = PayrollCreateSchema.model_validate(
        request.get_json() or {}
    )

    record = create_payroll_record(
        staff_id=payload.staff_id,
        pay_period_start=payload.pay_period_start,
        pay_period_end=payload.pay_period_end,
        base_salary=payload.base_salary,
        bonuses=payload.bonuses,
        deductions=payload.deductions,
    )

    return jsonify({
        "message": "Payroll record created successfully",
        "data": _serialize_payroll(record),
    }), 201


@staff_bp.post("/payroll/generate")
@role_required(*PAYROLL_ROLES)
def generate_payroll_route():
    payload = PayrollGenerateSchema.model_validate(
        request.get_json() or {}
    )

    records = generate_payroll_for_period(
        clinic_id=payload.clinic_id,
        pay_period_start=payload.pay_period_start,
        pay_period_end=payload.pay_period_end,
        salary_lookup=payload.salary_lookup,
    )

    return jsonify({
        "message": "Payroll generated successfully",
        "data": [
            _serialize_payroll(record)
            for record in records
        ],
        "count": len(records),
    }), 201


@staff_bp.get("/payroll")
@role_required(*PAYROLL_ROLES)
def list_payroll_route():
    payload = PayrollListQuerySchema.model_validate(
        request.args.to_dict()
    )

    if payload.staff_id is None:
        return jsonify({
            "error": "staff_id query parameter is required",
        }), 422

    records = list_payroll_for_staff(
        staff_id=payload.staff_id,
    )

    return jsonify({
        "data": [
            _serialize_payroll(record)
            for record in records
        ],
    }), 200


@staff_bp.get("/payroll/<int:record_id>")
@role_required(*PAYROLL_ROLES)
def get_payroll_record_route(record_id: int):
    record = get_payroll_record(record_id)

    return jsonify({
        "data": _serialize_payroll(record),
    }), 200


@staff_bp.post("/payroll/<int:record_id>/pay")
@role_required(*PAYROLL_ROLES)
def mark_payroll_paid_route(record_id: int):
    record = mark_payroll_paid(
        record_id=record_id,
    )

    return jsonify({
        "message": "Payroll marked as paid successfully",
        "data": _serialize_payroll(record),
    }), 200