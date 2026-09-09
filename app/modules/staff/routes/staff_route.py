from flask import Blueprint, g, jsonify, request, session
from flask_jwt_extended import get_jwt_identity, jwt_required
from pydantic import ValidationError as PydanticValidationError

from app.extensions import db
from app.core.exceptions import DomainError, ValidationError
from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    DomainError,
    NotFoundError,
    ValidationError,
)
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

from app.modules.staff.schemas.excuse_schema import (
    ExcuseCreateSchema,
    ExcuseListQuerySchema,
    ExcuseRejectSchema,
    ExcuseReviewSchema,
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
    list_payroll,
    list_payroll_for_staff,
    list_staff,
    mark_payroll_paid,
    reject_leave_request,
    request_leave,
    update_staff,
)

from app.modules.staff.services.excuse_service import (
    approve_excuse,
    create_excuse,
    get_excuse,
    get_my_excuses,
    list_excuses,
    reject_excuse,
)


# ============================================================================
# BLUEPRINT
# ============================================================================

staff_bp = Blueprint(
    "staff",
    __name__,
    url_prefix="/api/staff",
)


# ============================================================================
# ROLE MATRIX
# ============================================================================

MANAGEMENT_ROLES = (
    Role.ADMIN,
)

STAFF_VIEW_ROLES = (
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
    Role.RECEPTIONIST,
    Role.PARAMEDIC,
    Role.EMT,
    Role.DRIVER,
    Role.AMBULANCE_DISPATCHER,
    Role.AMBULANCE_COORDINATOR,
    Role.ACCOUNTANT,
    Role.OTHER,
)

LEAVE_MANAGEMENT_ROLES = (
    Role.ADMIN,
)

PAYROLL_ROLES = (
    Role.ADMIN,
    Role.ACCOUNTANT,
)

EXCUSE_REVIEW_ROLES = (
    Role.ADMIN,
)


# ============================================================================
# AUTH HELPERS
# ============================================================================

def _current_user():
    """
    Return the authenticated user.
    """
    identity = get_jwt_identity()

    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        raise ValidationError(
            "Invalid authentication identity"
        )

    user = db.session.get(User, user_id)

    if user is None:
        raise ValidationError(
            "Authenticated user could not be resolved"
        )

    if not user.is_active:
        raise ValidationError(
            "User account is inactive"
        )

    return user


def _current_clinic_id() -> int:
    user = _current_user()

    if user.clinic_id is None:
        raise ValidationError(
            "Authenticated user is not assigned to a clinic"
        )

    return user.clinic_id


def _current_staff_id() -> int:
    user = _current_user()

    if user.staff is None:
        raise ValidationError(
            "Authenticated user is not linked to a staff profile"
        )

    return user.staff.id


def _is_admin(user: User) -> bool:
    role = user.role

    if isinstance(role, Role):
        return role == Role.ADMIN

    return str(role) == Role.ADMIN.value


# ============================================================================
# REQUEST VALIDATION
# ============================================================================

def _validate_json(schema):
    payload = request.get_json(silent=True)

    if payload is None:
        return None, (
            jsonify({
                "error": "Request body must contain valid JSON",
            }),
            400,
        )

    try:
        return schema.model_validate(payload), None

    except PydanticValidationError as exc:
        return None, (
            jsonify({
                "error": "Validation failed",
                "details": exc.errors(),
            }),
            422,
        )
        
        
def _validate_json(schema):
    payload = request.get_json(silent=True)

    if payload is None:
        return None, (
            jsonify({
                "error": "Invalid or missing JSON body"
            }),
            400,
        )

    try:
        return schema.model_validate(payload), None

    except ValidationError as exc:
        details = []

        for error in exc.errors():
            normalized = {
                key: (
                    {
                        ctx_key: str(ctx_value)
                        for ctx_key, ctx_value in value.items()
                    }
                    if key == "ctx" and isinstance(value, dict)
                    else value
                )
                for key, value in error.items()
            }

            details.append(normalized)

        return None, (
            jsonify({
                "error": "Validation failed",
                "details": details,
            }),
            422,
        )
        

def _validate_query(schema):
    try:
        return schema.model_validate(
            request.args.to_dict()
        ), None

    except PydanticValidationError as exc:
        return None, (
            jsonify({
                "error": "Validation failed",
                "details": exc.errors(),
            }),
            422,
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
        "status": (
            staff.status.value
            if hasattr(staff.status, "value")
            else staff.status
        ),
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
        "leave_type": (
            leave.leave_type.value
            if hasattr(leave.leave_type, "value")
            else leave.leave_type
        ),
        "status": (
            leave.status.value
            if hasattr(leave.status, "value")
            else leave.status
        ),
        "start_date": (
            leave.start_date.isoformat()
            if leave.start_date
            else None
        ),
        "end_date": (
            leave.end_date.isoformat()
            if leave.end_date
            else None
        ),
        "reason": leave.reason,
        "reviewed_by_user_id": leave.reviewed_by_user_id,
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
    paid_at = getattr(record, "paid_at", None)

    return {
        "id": record.id,
        "staff_id": record.staff_id,
        "pay_period_start": (
            record.pay_period_start.isoformat()
            if record.pay_period_start
            else None
        ),
        "pay_period_end": (
            record.pay_period_end.isoformat()
            if record.pay_period_end
            else None
        ),
        "base_salary": str(record.base_salary),
        "bonuses": str(record.bonuses),
        "deductions": str(record.deductions),
        "net_pay": str(record.net_pay),
        "paid_at": (
            paid_at.isoformat()
            if paid_at
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


def _serialize_excuse(excuse):
    return {
        "id": excuse.id,
        "staff_id": excuse.staff_id,
        "leave_request_id": excuse.leave_request_id,
        "excuse_type": (
            excuse.excuse_type.value
            if hasattr(excuse.excuse_type, "value")
            else excuse.excuse_type
        ),
        "status": (
            excuse.status.value
            if hasattr(excuse.status, "value")
            else excuse.status
        ),
        "description": excuse.description,
        "document_url": excuse.document_url,

        # Important:
        # rejection_reason belongs in the response, not creation.
        "rejection_reason": getattr(
            excuse,
            "rejection_reason",
            None,
        ),

        "reviewed_by_user_id": excuse.reviewed_by_user_id,
        "reviewed_at": (
            excuse.reviewed_at.isoformat()
            if excuse.reviewed_at
            else None
        ),
        "created_at": (
            excuse.created_at.isoformat()
            if excuse.created_at
            else None
        ),
        "updated_at": (
            excuse.updated_at.isoformat()
            if excuse.updated_at
            else None
        ),
    }


# ============================================================================
# STAFF
# ============================================================================

@staff_bp.post("")
@jwt_required()
@role_required(*MANAGEMENT_ROLES)
def create_staff_route():
    payload, error = _validate_json(
        StaffCreateSchema
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        staff = create_staff(
            clinic_id=clinic_id,
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

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def list_staff_route():
    try:
        payload, error = _validate_query(
            StaffListQuerySchema
        )

        if error:
            return error

        clinic_id = _current_clinic_id()

        staff = list_staff(
            clinic_id=clinic_id,
            status=payload.status,
            search=payload.search,
        )

        return jsonify({
            "data": [
                _serialize_staff(item)
                for item in staff
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/<int:staff_id>")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def get_staff_route(staff_id: int):
    try:
        clinic_id = _current_clinic_id()

        staff = get_staff(
            staff_id=staff_id,
            clinic_id=clinic_id,
        )

        return jsonify({
            "data": _serialize_staff(staff),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.patch("/<int:staff_id>")
@jwt_required()
@role_required(*MANAGEMENT_ROLES)
def update_staff_route(staff_id: int):
    payload, error = _validate_json(
        StaffUpdateSchema
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        fields = payload.model_dump(
            exclude_unset=True
        )

        staff = update_staff(
            staff_id=staff_id,
            clinic_id=clinic_id,
            **fields,
        )

        return jsonify({
            "message": "Staff updated successfully",
            "data": _serialize_staff(staff),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.patch("/<int:staff_id>/status")
@jwt_required()
@role_required(*MANAGEMENT_ROLES)
def change_staff_status_route(staff_id: int):
    payload, error = _validate_json(
        StaffStatusUpdateSchema
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        staff = change_staff_status(
            staff_id=staff_id,
            clinic_id=clinic_id,
            new_status=payload.status,
        )

        return jsonify({
            "message": "Staff status updated successfully",
            "data": _serialize_staff(staff),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# LEAVE
# ============================================================================

@staff_bp.post("/leave")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def request_leave_route():
    payload, error = _validate_json(
        LeaveRequestCreateSchema
    )

    if error:
        return error

    try:
        user = _current_user()
        clinic_id = _current_clinic_id()
        staff_id = _current_staff_id()

        leave = request_leave(
            clinic_id=clinic_id,
            staff_id=staff_id,
            actor_user_id=user.id,
            leave_type=payload.leave_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            reason=payload.reason,
        )

        return jsonify({
            "message": "Leave request submitted successfully",
            "data": _serialize_leave(leave),
        }), 201

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/leave")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def list_leave_route():
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload, error = _validate_query(
            LeaveListQuerySchema
        )

        if error:
            return error

        staff_id = payload.staff_id

        # Non-admin users may only view their own leave.
        if not _is_admin(user):
            staff_id = _current_staff_id()

        leaves = list_leave_requests(
            clinic_id=clinic_id,
            staff_id=staff_id,
            status=payload.status,
        )

        return jsonify({
            "data": [
                _serialize_leave(leave)
                for leave in leaves
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/leave/<int:leave_id>")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def get_leave_route(leave_id: int):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        leave = get_leave_request(
            leave_id=leave_id,
            clinic_id=clinic_id,
        )

        # Non-admin users cannot inspect another staff member's leave.
        if not _is_admin(user):
            staff_id = _current_staff_id()

            if leave.staff_id != staff_id:
                raise NotFoundError(
                    f"Leave request {leave_id} not found"
                )

        return jsonify({
            "data": _serialize_leave(leave),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.post("/leave/<int:leave_id>/approve")
@jwt_required()
@role_required(*LEAVE_MANAGEMENT_ROLES)
def approve_leave_route(leave_id: int):
    payload, error = _validate_json(
        LeaveReviewSchema
    )

    if error:
        return error

    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        leave = approve_leave_request(
            leave_id=leave_id,
            clinic_id=clinic_id,
            reviewer_user_id=user.id,
        )

        return jsonify({
            "message": "Leave request approved successfully",
            "data": _serialize_leave(leave),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.post("/leave/<int:leave_id>/reject")
@jwt_required()
@role_required(*LEAVE_MANAGEMENT_ROLES)
def reject_leave_route(leave_id: int):
    payload, error = _validate_json(
        LeaveRejectSchema
    )

    if error:
        return error

    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        leave = reject_leave_request(
            leave_id=leave_id,
            clinic_id=clinic_id,
            reviewer_user_id=user.id,
            reason=payload.reason,
        )

        return jsonify({
            "message": "Leave request rejected successfully",
            "data": _serialize_leave(leave),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# EXCUSES
# ============================================================================

@staff_bp.post("/excuses")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def create_excuse_route():
    payload, error = _validate_json(
        ExcuseCreateSchema
    )

    if error:
        return error

    try:
        user = _current_user()
        clinic_id = _current_clinic_id()
        staff_id = _current_staff_id()

        excuse = create_excuse(
            clinic_id=clinic_id,
            staff_id=staff_id,
            actor_user_id=user.id,
            excuse_type=payload.excuse_type,
            description=payload.description,
            leave_request_id=payload.leave_request_id,
            document_url=payload.document_url,
        )

        return jsonify({
            "message": "Excuse submitted successfully",
            "data": _serialize_excuse(excuse),
        }), 201

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/excuses")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def list_excuses_route():
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        payload, error = _validate_query(
            ExcuseListQuerySchema
        )

        if error:
            return error

        if _is_admin(user):
            excuses = list_excuses(
                clinic_id=clinic_id,
                staff_id=payload.staff_id,
                leave_request_id=payload.leave_request_id,
                excuse_type=payload.excuse_type,
                status=payload.status,
            )
        else:
            staff_id = _current_staff_id()

            excuses = list_excuses(
                clinic_id=clinic_id,
                staff_id=staff_id,
                leave_request_id=payload.leave_request_id,
                excuse_type=payload.excuse_type,
                status=payload.status,
            )

        return jsonify({
            "data": [
                _serialize_excuse(excuse)
                for excuse in excuses
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


# Keep /me before /<int:excuse_id>.
@staff_bp.get("/excuses/me")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def get_my_excuses_route():
    try:
        clinic_id = _current_clinic_id()
        staff_id = _current_staff_id()

        excuses = get_my_excuses(
            clinic_id=clinic_id,
            staff_id=staff_id,
        )

        return jsonify({
            "data": [
                _serialize_excuse(excuse)
                for excuse in excuses
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/excuses/<int:excuse_id>")
@jwt_required()
@role_required(*STAFF_VIEW_ROLES)
def get_excuse_route(excuse_id: int):
    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        excuse = get_excuse(
            excuse_id=excuse_id,
            clinic_id=clinic_id,
        )

        # Non-admin users may only inspect their own excuses.
        if not _is_admin(user):
            staff_id = _current_staff_id()

            if excuse.staff_id != staff_id:
                raise NotFoundError(
                    f"Excuse {excuse_id} not found"
                )

        return jsonify({
            "data": _serialize_excuse(excuse),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.post("/excuses/<int:excuse_id>/approve")
@jwt_required()
@role_required(*EXCUSE_REVIEW_ROLES)
def approve_excuse_route(excuse_id: int):
    payload, error = _validate_json(
        ExcuseReviewSchema
    )

    if error:
        return error

    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        excuse = approve_excuse(
            excuse_id=excuse_id,
            clinic_id=clinic_id,
            reviewer_user_id=user.id,
        )

        return jsonify({
            "message": "Excuse approved successfully",
            "data": _serialize_excuse(excuse),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.post("/excuses/<int:excuse_id>/reject")
@jwt_required()
@role_required(*EXCUSE_REVIEW_ROLES)
def reject_excuse_route(excuse_id: int):
    payload, error = _validate_json(
        ExcuseRejectSchema
    )

    if error:
        return error

    try:
        user = _current_user()
        clinic_id = _current_clinic_id()

        excuse = reject_excuse(
            excuse_id=excuse_id,
            clinic_id=clinic_id,
            reviewer_user_id=user.id,
            reason=payload.reason,
        )

        return jsonify({
            "message": "Excuse rejected successfully",
            "data": _serialize_excuse(excuse),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


# ============================================================================
# PAYROLL
# ============================================================================

@staff_bp.post("/payroll")
@jwt_required()
@role_required(*PAYROLL_ROLES)
def create_payroll_route():
    payload, error = _validate_json(
        PayrollCreateSchema
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        record = create_payroll_record(
            clinic_id=clinic_id,
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

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.post("/payroll/generate")
@jwt_required()
@role_required(*PAYROLL_ROLES)
def generate_payroll_route():
    payload, error = _validate_json(
        PayrollGenerateSchema
    )

    if error:
        return error

    try:
        clinic_id = _current_clinic_id()

        records = generate_payroll_for_period(
            clinic_id=clinic_id,
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
        }), 201

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/payroll")
@jwt_required()
@role_required(*PAYROLL_ROLES)
def list_payroll_route():
    try:
        clinic_id = _current_clinic_id()

        payload, error = _validate_query(
            PayrollListQuerySchema
        )

        if error:
            return error

        if payload.staff_id is not None:
            records = list_payroll_for_staff(
                clinic_id=clinic_id,
                staff_id=payload.staff_id,
            )
        else:
            records = list_payroll(
                clinic_id=clinic_id,
            )

        return jsonify({
            "data": [
                _serialize_payroll(record)
                for record in records
            ],
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.get("/payroll/<int:record_id>")
@jwt_required()
@role_required(*PAYROLL_ROLES)
def get_payroll_route(record_id: int):
    try:
        clinic_id = _current_clinic_id()

        record = get_payroll_record(
            record_id=record_id,
            clinic_id=clinic_id,
        )

        return jsonify({
            "data": _serialize_payroll(record),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code


@staff_bp.post("/payroll/<int:record_id>/pay")
@jwt_required()
@role_required(*PAYROLL_ROLES)
def mark_payroll_paid_route(record_id: int):
    try:
        clinic_id = _current_clinic_id()

        record = mark_payroll_paid(
            record_id=record_id,
            clinic_id=clinic_id,
        )

        return jsonify({
            "message": "Payroll marked as paid successfully",
            "data": _serialize_payroll(record),
        }), 200

    except DomainError as exc:
        return jsonify({
            "error": str(exc),
        }), exc.status_code