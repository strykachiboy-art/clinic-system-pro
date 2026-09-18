from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_

from app.extensions import db
from app.core.enums.asset_enums import (
    AssetCondition,
    AssetHistoryEventType,
    AssetStatus,
)
from app.core.exceptions import NotFoundError
from app.modules.asset_control.models.asset_history_model import AssetHistory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_asset_history(
    *,
    clinic_id: int,
    asset_id: int,
    event_type: AssetHistoryEventType,
    actor_user_id: int | None = None,
    previous_status: AssetStatus | None = None,
    new_status: AssetStatus | None = None,
    previous_condition: AssetCondition | None = None,
    new_condition: AssetCondition | None = None,
    previous_assigned_to_id: int | None = None,
    new_assigned_to_id: int | None = None,
    previous_location: str | None = None,
    new_location: str | None = None,
    reason: str | None = None,
    notes: str | None = None,
    event_metadata: dict[str, Any] | None = None,
    event_at: datetime | None = None,
) -> AssetHistory:
    history = AssetHistory(
        clinic_id=clinic_id,
        asset_id=asset_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=new_status,
        previous_condition=previous_condition,
        new_condition=new_condition,
        previous_assigned_to_id=previous_assigned_to_id,
        new_assigned_to_id=new_assigned_to_id,
        previous_location=previous_location,
        new_location=new_location,
        actor_user_id=actor_user_id,
        event_at=event_at or _utcnow(),
        reason=reason,
        notes=notes,
        event_metadata=event_metadata,
    )

    db.session.add(history)
    db.session.flush()

    return history


def get_asset_history(
    *,
    history_id: int,
    clinic_id: int,
) -> AssetHistory:
    statement = db.select(
        AssetHistory
    ).where(
        AssetHistory.id == history_id,
        AssetHistory.clinic_id == clinic_id,
    )

    history = db.session.execute(
        statement
    ).scalar_one_or_none()

    if history is None:
        raise NotFoundError(
            f"Asset history {history_id} not found"
        )

    return history


def list_asset_history(
    *,
    clinic_id: int,
    query,
) -> dict:
    statement = db.select(
        AssetHistory
    ).where(
        AssetHistory.clinic_id == clinic_id
    )

    if query.asset_id is not None:
        statement = statement.where(
            AssetHistory.asset_id == query.asset_id
        )

    if query.event_type is not None:
        statement = statement.where(
            AssetHistory.event_type == query.event_type
        )

    if query.actor_user_id is not None:
        statement = statement.where(
            AssetHistory.actor_user_id
            == query.actor_user_id
        )

    if query.event_from is not None:
        statement = statement.where(
            AssetHistory.event_at >= query.event_from
        )

    if query.event_to is not None:
        statement = statement.where(
            AssetHistory.event_at <= query.event_to
        )

    statement = statement.order_by(
        AssetHistory.event_at.desc(),
        AssetHistory.id.desc(),
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


def get_latest_maintenance_start(
    *,
    clinic_id: int,
    asset_id: int,
) -> AssetHistory | None:
    statement = db.select(
        AssetHistory
    ).where(
        and_(
            AssetHistory.clinic_id == clinic_id,
            AssetHistory.asset_id == asset_id,
            AssetHistory.event_type
            == AssetHistoryEventType.MAINTENANCE_STARTED,
        )
    ).order_by(
        AssetHistory.event_at.desc(),
        AssetHistory.id.desc(),
    ).limit(1)

    return db.session.execute(
        statement
    ).scalar_one_or_none()