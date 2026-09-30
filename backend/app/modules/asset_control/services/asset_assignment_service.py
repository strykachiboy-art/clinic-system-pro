from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.asset_enums import AssetHistoryEventType, AssetStatus
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import ConflictError, NotFoundError
from app.core.utils.decorators import transactional
from app.modules.asset_control.models.asset_assignment_model import (
    AssetAssignment,
)
from app.modules.asset_control.schemas.asset_assignment_schema import (
    AssetAssignmentCreateSchema,
    AssetAssignmentListQuerySchema,
    AssetAssignmentReturnSchema,
)
from app.modules.asset_control.services.asset_history_service import (
    record_asset_history,
)
from app.modules.asset_control.services.asset_service import (
    _get_asset,
    _validate_actor_user,
    _validate_assigned_staff,
    _validate_clinic_for_write,
    _validate_asset_available_for_assignment,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_assignment(
    *,
    assignment_id: int,
    clinic_id: int,
    for_update: bool = False,
) -> AssetAssignment:
    statement = db.select(
        AssetAssignment
    ).where(
        AssetAssignment.id == assignment_id,
        AssetAssignment.clinic_id == clinic_id,
    )

    if for_update:
        statement = statement.with_for_update()

    assignment = db.session.execute(
        statement
    ).scalar_one_or_none()

    if assignment is None:
        raise NotFoundError(
            f"Asset assignment {assignment_id} not found"
        )

    return assignment


def _get_active_assignment_for_asset(
    *,
    asset_id: int,
    clinic_id: int,
    for_update: bool = False,
) -> AssetAssignment | None:
    statement = db.select(
        AssetAssignment
    ).where(
        AssetAssignment.asset_id == asset_id,
        AssetAssignment.clinic_id == clinic_id,
        AssetAssignment.returned_at.is_(None),
    ).order_by(
        AssetAssignment.assigned_at.desc(),
        AssetAssignment.id.desc(),
    ).limit(1)

    if for_update:
        statement = statement.with_for_update()

    return db.session.execute(
        statement
    ).scalar_one_or_none()


@transactional
def assign_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetAssignmentCreateSchema | dict,
) -> AssetAssignment:
    clinic = _validate_clinic_for_write(
        clinic_id
    )

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if isinstance(data, dict):
        data = AssetAssignmentCreateSchema.model_validate(
            data
        )

    _validate_asset_available_for_assignment(
        asset
    )

    if asset.assigned_to_id is not None:
        raise ConflictError(
            f"Asset {asset.id} is already assigned"
        )

    active_assignment = _get_active_assignment_for_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if active_assignment is not None:
        raise ConflictError(
            f"Asset {asset.id} already has an active assignment"
        )

    staff = _validate_assigned_staff(
        staff_id=data.staff_id,
        clinic_id=clinic.id,
    )

    old_status = asset.status

    assignment = AssetAssignment(
        clinic_id=clinic.id,
        asset_id=asset.id,
        staff_id=staff.id,
        assigned_at=_utcnow(),
        assigned_by_user_id=actor.id,
        notes=data.notes,
    )

    db.session.add(assignment)

    asset.assigned_to_id = staff.id
    asset.status = AssetStatus.ASSIGNED
    asset.updated_at = _utcnow()

    db.session.flush()

    record_asset_history(
        clinic_id=clinic.id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.ASSIGNED,
        actor_user_id=actor.id,
        previous_status=old_status,
        new_status=asset.status,
        previous_assigned_to_id=None,
        new_assigned_to_id=staff.id,
        event_metadata={
            "assignment_id": assignment.id,
            "staff_id": staff.id,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=(
            f"Asset '{asset.asset_tag}' assigned "
            f"to staff {staff.id}"
        ),
        old_value={
            "status": old_status.value,
            "assigned_to_id": None,
        },
        new_value={
            "status": asset.status.value,
            "assigned_to_id": staff.id,
        },
    )

    return assignment


@transactional
def return_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetAssignmentReturnSchema | dict | None = None,
) -> AssetAssignment:
    clinic = _validate_clinic_for_write(
        clinic_id
    )

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if data is None:
        data = AssetAssignmentReturnSchema()

    elif isinstance(data, dict):
        data = AssetAssignmentReturnSchema.model_validate(
            data
        )

    assignment = _get_active_assignment_for_asset(
        asset_id=asset.id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if assignment is None:
        raise NotFoundError(
            f"No active assignment found for asset {asset.id}"
        )

    if asset.assigned_to_id != assignment.staff_id:
        raise ConflictError(
            f"Asset {asset.id} assignment state is inconsistent"
        )

    old_status = asset.status
    old_staff_id = asset.assigned_to_id

    returned_at = _utcnow()

    assignment.returned_at = returned_at
    assignment.returned_by_user_id = actor.id

    if data.notes is not None:
        assignment.notes = data.notes

    asset.assigned_to_id = None
    asset.status = AssetStatus.ACTIVE
    asset.updated_at = returned_at

    db.session.flush()

    record_asset_history(
        clinic_id=clinic.id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.UNASSIGNED,
        actor_user_id=actor.id,
        previous_status=old_status,
        new_status=asset.status,
        previous_assigned_to_id=old_staff_id,
        new_assigned_to_id=None,
        event_metadata={
            "assignment_id": assignment.id,
            "staff_id": old_staff_id,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=(
            f"Asset '{asset.asset_tag}' returned "
            f"from staff {old_staff_id}"
        ),
        old_value={
            "status": old_status.value,
            "assigned_to_id": old_staff_id,
        },
        new_value={
            "status": asset.status.value,
            "assigned_to_id": None,
        },
    )

    return assignment


def get_asset_assignment(
    *,
    assignment_id: int,
    clinic_id: int,
) -> AssetAssignment:
    return _get_assignment(
        assignment_id=assignment_id,
        clinic_id=clinic_id,
    )


def list_asset_assignments(
    *,
    clinic_id: int,
    query: AssetAssignmentListQuerySchema | dict | None = None,
) -> dict:
    clinic_id = _validate_clinic_for_write(
        clinic_id
    ).id

    if query is None:
        query = AssetAssignmentListQuerySchema()

    elif isinstance(query, dict):
        query = AssetAssignmentListQuerySchema.model_validate(
            query
        )

    statement = db.select(
        AssetAssignment
    ).where(
        AssetAssignment.clinic_id == clinic_id
    )

    if query.asset_id is not None:
        statement = statement.where(
            AssetAssignment.asset_id == query.asset_id
        )

    if query.staff_id is not None:
        statement = statement.where(
            AssetAssignment.staff_id == query.staff_id
        )

    if query.active_only:
        statement = statement.where(
            AssetAssignment.returned_at.is_(None)
        )

    if query.assigned_from is not None:
        statement = statement.where(
            AssetAssignment.assigned_at
            >= query.assigned_from
        )

    if query.assigned_to is not None:
        statement = statement.where(
            AssetAssignment.assigned_at
            <= query.assigned_to
        )

    statement = statement.order_by(
        AssetAssignment.assigned_at.desc(),
        AssetAssignment.id.desc(),
    )

    pagination = db.paginate(
        statement,
        page=query.page,
        per_page=query.per_page,
        error_out=False,
    )

    return {
        "items": pagination.items,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }