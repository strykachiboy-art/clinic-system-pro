from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.asset_enums import (
    AssetHistoryEventType,
    AssetStatus,
    MaintenanceStatus,
)
from app.core.enums.audit_enums import AuditAction
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
)
from app.core.utils.decorators import transactional
from app.modules.asset_control.models.asset_maintenance_model import (
    AssetMaintenance,
)
from app.modules.asset_control.schemas.asset_maintenance_schema import (
    AssetMaintenanceCancelSchema,
    AssetMaintenanceCompleteSchema,
    AssetMaintenanceListQuerySchema,
    AssetMaintenanceScheduleSchema,
    AssetMaintenanceStartSchema,
)
from app.modules.asset_control.services.asset_history_service import (
    get_latest_maintenance_start,
    record_asset_history,
)
from app.modules.asset_control.services.asset_service import (
    _get_asset,
    _validate_actor_user,
    _validate_clinic_for_write,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_maintenance(
    *,
    maintenance_id: int,
    clinic_id: int,
    for_update: bool = False,
) -> AssetMaintenance:
    statement = db.select(
        AssetMaintenance
    ).where(
        AssetMaintenance.id == maintenance_id,
        AssetMaintenance.clinic_id == clinic_id,
    )

    if for_update:
        statement = statement.with_for_update()

    maintenance = db.session.execute(
        statement
    ).scalar_one_or_none()

    if maintenance is None:
        raise NotFoundError(
            f"Asset maintenance {maintenance_id} not found"
        )

    return maintenance


def _get_active_maintenance(
    *,
    asset_id: int,
    clinic_id: int,
    for_update: bool = False,
) -> AssetMaintenance | None:
    statement = db.select(
        AssetMaintenance
    ).where(
        AssetMaintenance.asset_id == asset_id,
        AssetMaintenance.clinic_id == clinic_id,
        AssetMaintenance.status.in_(
            (
                MaintenanceStatus.SCHEDULED,
                MaintenanceStatus.DUE,
                MaintenanceStatus.IN_PROGRESS,
                MaintenanceStatus.OVERDUE,
            )
        ),
    ).order_by(
        AssetMaintenance.created_at.desc(),
        AssetMaintenance.id.desc(),
    ).limit(1)

    if for_update:
        statement = statement.with_for_update()

    return db.session.execute(
        statement
    ).scalar_one_or_none()


def _restore_asset_status(
    *,
    asset,
    clinic_id: int,
) -> AssetStatus:
    history = get_latest_maintenance_start(
        clinic_id=clinic_id,
        asset_id=asset.id,
    )

    if history is not None:
        metadata = history.event_metadata or {}
        previous_status = metadata.get(
            "previous_asset_status"
        )

        if previous_status:
            try:
                return AssetStatus(
                    previous_status
                )
            except ValueError:
                pass

    if asset.assigned_to_id is not None:
        return AssetStatus.ASSIGNED

    return AssetStatus.ACTIVE


@transactional
def schedule_maintenance(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetMaintenanceScheduleSchema | dict,
) -> AssetMaintenance:
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
        data = AssetMaintenanceScheduleSchema.model_validate(
            data
        )

    if asset.status in (
        AssetStatus.RETIRED,
        AssetStatus.DISPOSED,
        AssetStatus.LOST,
    ):
        raise ConflictError(
            f"Asset {asset.id} cannot be scheduled for maintenance"
        )

    active_maintenance = _get_active_maintenance(
        asset_id=asset.id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if active_maintenance is not None:
        raise ConflictError(
            f"Asset {asset.id} already has active maintenance"
        )

    maintenance = AssetMaintenance(
        clinic_id=clinic.id,
        asset_id=asset.id,
        status=MaintenanceStatus.SCHEDULED,
        scheduled_date=data.scheduled_date,
        description=data.description,
        notes=data.notes,
    )

    db.session.add(maintenance)

    asset.maintenance_status = MaintenanceStatus.SCHEDULED

    if data.scheduled_date is not None:
        asset.next_maintenance_date = data.scheduled_date

    asset.updated_at = _utcnow()

    db.session.flush()

    record_asset_history(
        clinic_id=clinic.id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.UPDATED,
        actor_user_id=actor.id,
        event_metadata={
            "maintenance_id": maintenance.id,
            "maintenance_status": (
                MaintenanceStatus.SCHEDULED.value
            ),
            "scheduled_date": (
                data.scheduled_date.isoformat()
                if data.scheduled_date
                else None
            ),
        },
    )

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="AssetMaintenance",
        entity_id=maintenance.id,
        user_id=actor.id,
        description=(
            f"Maintenance scheduled for asset "
            f"'{asset.asset_tag}'"
        ),
        new_value={
            "asset_id": asset.id,
            "status": maintenance.status.value,
            "scheduled_date": (
                data.scheduled_date.isoformat()
                if data.scheduled_date
                else None
            ),
        },
    )

    return maintenance


@transactional
def start_maintenance(
    *,
    maintenance_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetMaintenanceStartSchema | dict | None = None,
) -> AssetMaintenance:
    clinic = _validate_clinic_for_write(
        clinic_id
    )

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    maintenance = _get_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    asset = _get_asset(
        asset_id=maintenance.asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if data is None:
        data = AssetMaintenanceStartSchema()

    elif isinstance(data, dict):
        data = AssetMaintenanceStartSchema.model_validate(
            data
        )

    if maintenance.status not in (
        MaintenanceStatus.SCHEDULED,
        MaintenanceStatus.DUE,
        MaintenanceStatus.OVERDUE,
    ):
        raise ConflictError(
            f"Maintenance {maintenance.id} cannot be started "
            f"from status {maintenance.status.value}"
        )

    if asset.status in (
        AssetStatus.RETIRED,
        AssetStatus.DISPOSED,
        AssetStatus.LOST,
    ):
        raise ConflictError(
            f"Asset {asset.id} cannot enter maintenance"
        )

    old_asset_status = asset.status
    old_maintenance_status = maintenance.status

    maintenance.status = MaintenanceStatus.IN_PROGRESS
    maintenance.started_at = _utcnow()
    maintenance.performed_by_user_id = actor.id

    if data.notes is not None:
        maintenance.notes = data.notes

    asset.status = AssetStatus.UNDER_MAINTENANCE
    asset.maintenance_status = MaintenanceStatus.IN_PROGRESS
    asset.updated_at = _utcnow()

    db.session.flush()

    record_asset_history(
        clinic_id=clinic.id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.MAINTENANCE_STARTED,
        actor_user_id=actor.id,
        previous_status=old_asset_status,
        new_status=asset.status,
        event_metadata={
            "maintenance_id": maintenance.id,
            "previous_asset_status": old_asset_status.value,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=(
            f"Maintenance {maintenance.id} started "
            f"for asset '{asset.asset_tag}'"
        ),
        old_value={
            "status": old_asset_status.value,
            "maintenance_status": (
                old_maintenance_status.value
            ),
        },
        new_value={
            "status": asset.status.value,
            "maintenance_status": (
                MaintenanceStatus.IN_PROGRESS.value
            ),
        },
    )

    return maintenance


@transactional
def complete_maintenance(
    *,
    maintenance_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetMaintenanceCompleteSchema | dict | None = None,
) -> AssetMaintenance:
    clinic = _validate_clinic_for_write(
        clinic_id
    )

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    maintenance = _get_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    asset = _get_asset(
        asset_id=maintenance.asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if data is None:
        data = AssetMaintenanceCompleteSchema()

    elif isinstance(data, dict):
        data = AssetMaintenanceCompleteSchema.model_validate(
            data
        )

    if maintenance.status != MaintenanceStatus.IN_PROGRESS:
        raise ConflictError(
            f"Maintenance {maintenance.id} cannot be completed "
            f"from status {maintenance.status.value}"
        )

    completed_at = _utcnow()

    maintenance.status = MaintenanceStatus.COMPLETED
    maintenance.completed_at = completed_at
    maintenance.performed_by_user_id = actor.id

    if data.cost is not None:
        maintenance.cost = data.cost

    if data.notes is not None:
        maintenance.notes = data.notes

    restored_status = _restore_asset_status(
        asset=asset,
        clinic_id=clinic.id,
    )

    asset.status = restored_status
    asset.maintenance_status = MaintenanceStatus.COMPLETED
    asset.last_maintenance_date = completed_at.date()
    asset.updated_at = completed_at

    db.session.flush()

    record_asset_history(
        clinic_id=clinic.id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.MAINTENANCE_COMPLETED,
        actor_user_id=actor.id,
        previous_status=AssetStatus.UNDER_MAINTENANCE,
        new_status=restored_status,
        event_metadata={
            "maintenance_id": maintenance.id,
            "completed_at": completed_at.isoformat(),
            "cost": (
                str(maintenance.cost)
                if maintenance.cost is not None
                else None
            ),
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=(
            f"Maintenance {maintenance.id} completed "
            f"for asset '{asset.asset_tag}'"
        ),
        old_value={
            "status": AssetStatus.UNDER_MAINTENANCE.value,
            "maintenance_status": (
                MaintenanceStatus.IN_PROGRESS.value
            ),
        },
        new_value={
            "status": asset.status.value,
            "maintenance_status": (
                MaintenanceStatus.COMPLETED.value
            ),
        },
    )

    return maintenance


@transactional
def cancel_maintenance(
    *,
    maintenance_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetMaintenanceCancelSchema | dict,
) -> AssetMaintenance:
    clinic = _validate_clinic_for_write(
        clinic_id
    )

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    maintenance = _get_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    asset = _get_asset(
        asset_id=maintenance.asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if isinstance(data, dict):
        data = AssetMaintenanceCancelSchema.model_validate(
            data
        )

    if maintenance.status not in (
        MaintenanceStatus.SCHEDULED,
        MaintenanceStatus.DUE,
        MaintenanceStatus.IN_PROGRESS,
        MaintenanceStatus.OVERDUE,
    ):
        raise ConflictError(
            f"Maintenance {maintenance.id} cannot be cancelled "
            f"from status {maintenance.status.value}"
        )

    old_asset_status = asset.status
    old_maintenance_status = maintenance.status

    maintenance.status = MaintenanceStatus.CANCELLED
    maintenance.notes = (
        f"Cancelled: {data.reason}"
    )

    if old_asset_status == AssetStatus.UNDER_MAINTENANCE:
        asset.status = _restore_asset_status(
            asset=asset,
            clinic_id=clinic.id,
        )

    asset.maintenance_status = MaintenanceStatus.CANCELLED
    asset.updated_at = _utcnow()

    db.session.flush()

    record_asset_history(
        clinic_id=clinic.id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.MAINTENANCE_CANCELLED,
        actor_user_id=actor.id,
        previous_status=old_asset_status,
        new_status=asset.status,
        reason=data.reason,
        event_metadata={
            "maintenance_id": maintenance.id,
        },
    )

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=(
            f"Maintenance {maintenance.id} cancelled "
            f"for asset '{asset.asset_tag}'"
        ),
        old_value={
            "asset_status": old_asset_status.value,
            "maintenance_status": (
                old_maintenance_status.value
            ),
        },
        new_value={
            "asset_status": asset.status.value,
            "maintenance_status": (
                MaintenanceStatus.CANCELLED.value
            ),
        },
    )

    return maintenance


def get_asset_maintenance(
    *,
    maintenance_id: int,
    clinic_id: int,
) -> AssetMaintenance:
    return _get_maintenance(
        maintenance_id=maintenance_id,
        clinic_id=clinic_id,
    )


def list_asset_maintenance(
    *,
    clinic_id: int,
    query: AssetMaintenanceListQuerySchema | dict | None = None,
) -> dict:
    clinic_id = _validate_clinic_for_write(
        clinic_id
    ).id

    if query is None:
        query = AssetMaintenanceListQuerySchema()

    elif isinstance(query, dict):
        query = AssetMaintenanceListQuerySchema.model_validate(
            query
        )

    statement = db.select(
        AssetMaintenance
    ).where(
        AssetMaintenance.clinic_id == clinic_id
    )

    if query.asset_id is not None:
        statement = statement.where(
            AssetMaintenance.asset_id == query.asset_id
        )

    if query.status is not None:
        statement = statement.where(
            AssetMaintenance.status == query.status
        )

    if query.scheduled_from is not None:
        statement = statement.where(
            AssetMaintenance.scheduled_date
            >= query.scheduled_from
        )

    if query.scheduled_to is not None:
        statement = statement.where(
            AssetMaintenance.scheduled_date
            <= query.scheduled_to
        )

    if query.performed_by_user_id is not None:
        statement = statement.where(
            AssetMaintenance.performed_by_user_id
            == query.performed_by_user_id
        )

    statement = statement.order_by(
        AssetMaintenance.created_at.desc(),
        AssetMaintenance.id.desc(),
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