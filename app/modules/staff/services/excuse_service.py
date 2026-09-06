from datetime import datetime, timezone
from typing import Optional

from app.extensions import db

from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.excuse_enums import (
    ExcuseStatus,
    ExcuseType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional

from app.core.auth.user.models.user_model import User
from app.modules.staff.models.staff_model import (
    LeaveRequest,
    Staff,
)
from app.modules.staff.models.excuse_model import Excuse


def _utcnow():
    return datetime.now(timezone.utc)


def _db_now():
    """
    Return a naive UTC datetime for database DateTime columns.
    """
    return _utcnow().replace(tzinfo=None)


# ----------------------------------------------------------------------
# LOOKUPS
# ----------------------------------------------------------------------


def _get_staff(
    staff_id: int,
    clinic_id: Optional[int] = None,
    lock: bool = False,
) -> Staff:
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


def _get_user(
    user_id: int,
    clinic_id: Optional[int] = None,
) -> User:
    query = User.query.filter(
        User.id == user_id,
    )

    if clinic_id is not None:
        query = query.filter(
            User.clinic_id == clinic_id,
        )

    user = query.first()

    if user is None:
        raise NotFoundError(
            f"User {user_id} not found"
        )

    return user


def _get_excuse(
    excuse_id: int,
    clinic_id: Optional[int] = None,
    lock: bool = False,
) -> Excuse:
    """
    Fetch an excuse while enforcing clinic ownership
    through its Staff relationship.
    """

    query = (
        Excuse.query
        .join(
            Staff,
            Excuse.staff_id == Staff.id,
        )
        .filter(
            Excuse.id == excuse_id,
        )
    )

    if clinic_id is not None:
        query = query.filter(
            Staff.clinic_id == clinic_id,
        )

    if lock:
        query = query.with_for_update()

    excuse = query.first()

    if excuse is None:
        raise NotFoundError(
            f"Excuse {excuse_id} not found"
        )

    return excuse


def _get_leave_request(
    leave_request_id: int,
    clinic_id: int,
    lock: bool = False,
) -> LeaveRequest:
    """
    Fetch a leave request belonging to the authenticated clinic.
    """

    query = (
        LeaveRequest.query
        .join(
            Staff,
            LeaveRequest.staff_id == Staff.id,
        )
        .filter(
            LeaveRequest.id == leave_request_id,
            Staff.clinic_id == clinic_id,
        )
    )

    if lock:
        query = query.with_for_update()

    leave_request = query.first()

    if leave_request is None:
        raise NotFoundError(
            f"Leave request {leave_request_id} not found"
        )

    return leave_request


# ----------------------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------------------


def _validate_staff_can_submit_excuse(
    staff: Staff,
) -> None:
    """
    Staff must not be suspended or terminated to submit
    a new excuse.
    """

    if staff.status in (
        StaffStatus.SUSPENDED,
        StaffStatus.TERMINATED,
    ):
        raise ConflictError(
            f"Staff {staff.id} cannot submit an excuse "
            f"while in '{staff.status.value}' status"
        )


def _validate_excuse_type(
    excuse_type: ExcuseType,
) -> None:
    if not isinstance(excuse_type, ExcuseType):
        raise ValidationError(
            "Invalid excuse type"
        )


def _validate_description(
    description: str,
) -> str:
    if description is None:
        raise ValidationError(
            "Excuse description is required"
        )

    description = description.strip()

    if not description:
        raise ValidationError(
            "Excuse description is required"
        )

    if len(description) > 2000:
        raise ValidationError(
            "Excuse description cannot exceed 2000 characters"
        )

    return description


def _validate_document_url(
    document_url: Optional[str],
) -> Optional[str]:
    if document_url is None:
        return None

    document_url = document_url.strip()

    if not document_url:
        return None

    if len(document_url) > 500:
        raise ValidationError(
            "Document URL cannot exceed 500 characters"
        )

    return document_url


def _validate_rejection_reason(
    reason: Optional[str],
) -> Optional[str]:
    """
    Normalize and validate the persistent rejection reason.
    """

    if reason is None:
        return None

    reason = reason.strip()

    if not reason:
        raise ValidationError(
            "Rejection reason cannot be empty"
        )

    if len(reason) > 2000:
        raise ValidationError(
            "Rejection reason cannot exceed 2000 characters"
        )

    return reason


def _validate_reviewer(
    reviewer_user_id: int,
    clinic_id: int,
) -> User:
    reviewer = _get_user(
        reviewer_user_id,
        clinic_id=clinic_id,
    )

    if not reviewer.is_active:
        raise ValidationError(
            "Inactive users cannot review excuses"
        )

    if reviewer.role != Role.ADMIN:
        raise ValidationError(
            "Only administrators can review excuses"
        )

    return reviewer


def _validate_leave_request_for_staff(
    leave_request: LeaveRequest,
    staff: Staff,
) -> None:
    if leave_request.staff_id != staff.id:
        raise ConflictError(
            "Leave request does not belong to this staff member"
        )


# ----------------------------------------------------------------------
# CREATE
# ----------------------------------------------------------------------


@transactional
def create_excuse(
    *,
    clinic_id: int,
    staff_id: int,
    excuse_type: ExcuseType,
    description: str,
    leave_request_id: Optional[int] = None,
    document_url: Optional[str] = None,
) -> Excuse:
    """
    Create an excuse for a staff member.

    The route should derive staff_id from the authenticated
    user's linked Staff record rather than accepting it from
    the client.
    """

    staff = _get_staff(
        staff_id,
        clinic_id=clinic_id,
        lock=True,
    )

    _validate_staff_can_submit_excuse(staff)
    _validate_excuse_type(excuse_type)

    description = _validate_description(description)
    document_url = _validate_document_url(document_url)

    leave_request = None

    if leave_request_id is not None:
        leave_request = _get_leave_request(
            leave_request_id,
            clinic_id=clinic_id,
            lock=True,
        )

        _validate_leave_request_for_staff(
            leave_request,
            staff,
        )

    excuse = Excuse(
        staff_id=staff.id,
        leave_request_id=(
            leave_request.id
            if leave_request is not None
            else None
        ),
        excuse_type=excuse_type,
        status=ExcuseStatus.PENDING,
        description=description,
        document_url=document_url,
        rejection_reason=None,
    )

    db.session.add(excuse)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Excuse",
        entity_id=excuse.id,
        description=(
            f"Excuse created for staff {staff.id}"
        ),
        new_value={
            "staff_id": staff.id,
            "leave_request_id": excuse.leave_request_id,
            "excuse_type": excuse.excuse_type.value,
            "status": excuse.status.value,
        },
        user_id=(
            staff.user_id
            if staff.user_id is not None
            else None
        ),
    )

    return excuse


# ----------------------------------------------------------------------
# READ
# ----------------------------------------------------------------------


def get_excuse(
    excuse_id: int,
    clinic_id: int,
) -> Excuse:
    return _get_excuse(
        excuse_id,
        clinic_id=clinic_id,
    )


def list_excuses(
    *,
    clinic_id: int,
    staff_id: Optional[int] = None,
    leave_request_id: Optional[int] = None,
    excuse_type: Optional[ExcuseType] = None,
    status: Optional[ExcuseStatus] = None,
):
    """
    List excuses belonging only to the authenticated clinic.
    """

    query = (
        Excuse.query
        .join(
            Staff,
            Excuse.staff_id == Staff.id,
        )
        .filter(
            Staff.clinic_id == clinic_id,
        )
    )

    if staff_id is not None:
        query = query.filter(
            Excuse.staff_id == staff_id,
        )

    if leave_request_id is not None:
        query = query.filter(
            Excuse.leave_request_id == leave_request_id,
        )

    if excuse_type is not None:
        query = query.filter(
            Excuse.excuse_type == excuse_type,
        )

    if status is not None:
        query = query.filter(
            Excuse.status == status,
        )

    return (
        query
        .order_by(
            Excuse.created_at.desc(),
        )
        .all()
    )


def list_staff_excuses(
    *,
    clinic_id: int,
    staff_id: int,
):
    """
    Return excuses for one staff member.

    The staff member must belong to the authenticated clinic.
    """

    _get_staff(
        staff_id,
        clinic_id=clinic_id,
    )

    return (
        Excuse.query
        .filter(
            Excuse.staff_id == staff_id,
        )
        .order_by(
            Excuse.created_at.desc(),
        )
        .all()
    )


def get_my_excuses(
    *,
    clinic_id: int,
    staff_id: int,
):
    """
    Return only the authenticated staff member's excuses.
    """

    return list_staff_excuses(
        clinic_id=clinic_id,
        staff_id=staff_id,
    )


# ----------------------------------------------------------------------
# APPROVE
# ----------------------------------------------------------------------


@transactional
def approve_excuse(
    *,
    excuse_id: int,
    clinic_id: int,
    reviewer_user_id: int,
) -> Excuse:
    """
    Approve a pending excuse.

    Reviewer is always the authenticated User.
    """

    excuse = _get_excuse(
        excuse_id,
        clinic_id=clinic_id,
        lock=True,
    )

    reviewer = _validate_reviewer(
        reviewer_user_id,
        clinic_id,
    )

    if excuse.status != ExcuseStatus.PENDING:
        raise ConflictError(
            f"Excuse {excuse.id} is already "
            f"'{excuse.status.value}' and cannot be approved"
        )

    now = _db_now()

    old_status = excuse.status

    excuse.status = ExcuseStatus.APPROVED
    excuse.rejection_reason = None
    excuse.reviewed_by_user_id = reviewer.id
    excuse.reviewed_at = now

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Excuse",
        entity_id=excuse.id,
        description=(
            f"Excuse {excuse.id} approved by "
            f"administrator {reviewer.id}"
        ),
        old_value={
            "status": old_status.value,
        },
        new_value={
            "status": excuse.status.value,
            "reviewed_by_user_id": reviewer.id,
            "reviewed_at": now.isoformat(),
            "rejection_reason": None,
        },
        user_id=reviewer.id,
    )

    return excuse


# ----------------------------------------------------------------------
# REJECT
# ----------------------------------------------------------------------


@transactional
def reject_excuse(
    *,
    excuse_id: int,
    clinic_id: int,
    reviewer_user_id: int,
    reason: Optional[str] = None,
) -> Excuse:
    """
    Reject a pending excuse.

    The rejection reason is persisted on the Excuse record
    and also captured in the audit log.
    """

    excuse = _get_excuse(
        excuse_id,
        clinic_id=clinic_id,
        lock=True,
    )

    reviewer = _validate_reviewer(
        reviewer_user_id,
        clinic_id,
    )

    if excuse.status != ExcuseStatus.PENDING:
        raise ConflictError(
            f"Excuse {excuse.id} is already "
            f"'{excuse.status.value}' and cannot be rejected"
        )

    reason = _validate_rejection_reason(reason)

    now = _db_now()

    old_status = excuse.status

    excuse.status = ExcuseStatus.REJECTED
    excuse.rejection_reason = reason
    excuse.reviewed_by_user_id = reviewer.id
    excuse.reviewed_at = now

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Excuse",
        entity_id=excuse.id,
        description=(
            f"Excuse {excuse.id} rejected by "
            f"administrator {reviewer.id}"
        ),
        old_value={
            "status": old_status.value,
            "rejection_reason": None,
        },
        new_value={
            "status": excuse.status.value,
            "reviewed_by_user_id": reviewer.id,
            "reviewed_at": now.isoformat(),
            "rejection_reason": reason,
        },
        user_id=reviewer.id,
    )

    return excuse