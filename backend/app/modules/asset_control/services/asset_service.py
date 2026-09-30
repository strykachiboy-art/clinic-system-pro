from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import or_

from app.extensions import db
from app.core.audit.services.audit_service import create_audit_log
from app.core.auth.user.models.user_model import User
from app.core.enums.asset_enums import (
    AssetHistoryEventType,
    AssetStatus,
    MaintenanceStatus,
)
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.modules.asset_control.models.asset_model import Asset
from app.modules.asset_control.schemas.asset_schema import (
    AssetCreateSchema,
    AssetListQuerySchema,
    AssetUpdateSchema,
)
from app.modules.asset_control.services.asset_history_service import (
    record_asset_history,
)
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.staff.models.staff_model import Staff


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_positive_id(
    value,
    field_name: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValidationError(
            f"{field_name} must be a positive integer"
        )

    return value


def _validate_clinic_for_write(
    clinic_id: int,
) -> Clinic:
    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic_id} is not active"
        )

    return clinic


def _validate_actor_user(
    *,
    actor_user_id: int,
    clinic_id: int,
) -> User:
    actor_user_id = _validate_positive_id(
        actor_user_id,
        "actor_user_id",
    )

    user = db.session.get(
        User,
        actor_user_id,
    )

    if user is None:
        raise NotFoundError(
            "Authenticated user not found"
        )

    if not user.is_active:
        raise ValidationError(
            f"Authenticated user {user.id} is inactive"
        )

    if user.clinic_id != clinic_id:
        raise NotFoundError(
            "Authenticated user not found"
        )

    return user


def _get_asset(
    *,
    asset_id: int,
    clinic_id: int,
    for_update: bool = False,
) -> Asset:
    asset_id = _validate_positive_id(
        asset_id,
        "asset_id",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    statement = db.select(Asset).where(
        Asset.id == asset_id,
        Asset.clinic_id == clinic_id,
    )

    if for_update:
        statement = statement.with_for_update()

    asset = db.session.execute(
        statement
    ).scalar_one_or_none()

    if asset is None:
        raise NotFoundError(
            f"Asset {asset_id} not found"
        )

    return asset


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            "Text field must be a string"
        )

    value = value.strip()

    return value or None


def _audit_value(value):
    if value is None:
        return None

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return value


def _build_audit_changes(
    *,
    old_values: dict,
    new_values: dict,
) -> tuple[dict, dict]:
    return (
        {
            field: _audit_value(value)
            for field, value in old_values.items()
        },
        {
            field: _audit_value(value)
            for field, value in new_values.items()
        },
    )


def _validate_purchase_dates(
    *,
    purchase_date: date | None,
    warranty_expiry: date | None,
) -> None:
    if (
        purchase_date is not None
        and warranty_expiry is not None
        and warranty_expiry < purchase_date
    ):
        raise ValidationError(
            "warranty_expiry cannot be before purchase_date"
        )


def _validate_assigned_staff(
    *,
    staff_id: int,
    clinic_id: int,
) -> Staff:
    staff_id = _validate_positive_id(
        staff_id,
        "staff_id",
    )

    staff = db.session.get(
        Staff,
        staff_id,
    )

    if staff is None:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    if staff.clinic_id != clinic_id:
        raise NotFoundError(
            f"Staff {staff_id} not found"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff {staff_id} is not active"
        )

    return staff


def _validate_asset_tag_unique(
    *,
    clinic_id: int,
    asset_tag: str,
    exclude_asset_id: int | None = None,
) -> None:
    statement = db.select(Asset.id).where(
        Asset.clinic_id == clinic_id,
        Asset.asset_tag == asset_tag,
    )

    if exclude_asset_id is not None:
        exclude_asset_id = _validate_positive_id(
            exclude_asset_id,
            "asset_id",
        )

        statement = statement.where(
            Asset.id != exclude_asset_id
        )

    existing_id = db.session.execute(
        statement.limit(1)
    ).scalar_one_or_none()

    if existing_id is not None:
        raise ConflictError(
            f"Asset tag '{asset_tag}' is already in use"
        )


def _asset_is_terminal(
    asset: Asset,
) -> bool:
    return asset.status in (
        AssetStatus.RETIRED,
        AssetStatus.DISPOSED,
    )


def _validate_asset_available_for_assignment(
    asset: Asset,
) -> None:
    if _asset_is_terminal(asset):
        raise ConflictError(
            f"Asset {asset.id} is no longer assignable"
        )

    if asset.status in (
        AssetStatus.UNDER_MAINTENANCE,
        AssetStatus.OUT_OF_SERVICE,
        AssetStatus.LOST,
    ):
        raise ConflictError(
            f"Asset {asset.id} is not available for assignment"
        )

    if not asset.is_active:
        raise ConflictError(
            f"Asset {asset.id} is inactive"
        )


@transactional
def create_asset(
    *,
    clinic_id: int,
    actor_user_id: int,
    data: AssetCreateSchema | dict,
) -> Asset:
    clinic = _validate_clinic_for_write(clinic_id)

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    if isinstance(data, dict):
        data = AssetCreateSchema.model_validate(data)

    _validate_asset_tag_unique(
        clinic_id=clinic.id,
        asset_tag=data.asset_tag,
    )

    _validate_purchase_dates(
        purchase_date=data.purchase_date,
        warranty_expiry=data.warranty_expiry,
    )

    asset = Asset(
        clinic_id=clinic.id,
        asset_tag=data.asset_tag,
        name=data.name,
        description=_normalize_optional_text(
            data.description
        ),
        category=data.category,
        status=AssetStatus.ACTIVE,
        condition=data.condition,
        ownership=data.ownership,
        location=_normalize_optional_text(
            data.location
        ),
        serial_number=_normalize_optional_text(
            data.serial_number
        ),
        manufacturer=_normalize_optional_text(
            data.manufacturer
        ),
        model_number=_normalize_optional_text(
            data.model_number
        ),
        purchase_date=data.purchase_date,
        purchase_cost=data.purchase_cost,
        supplier=_normalize_optional_text(
            data.supplier
        ),
        warranty_expiry=data.warranty_expiry,
        maintenance_status=(
            MaintenanceStatus.NOT_REQUIRED
        ),
        is_active=True,
        notes=_normalize_optional_text(
            data.notes
        ),
    )

    db.session.add(asset)
    db.session.flush()

    record_asset_history(
        clinic_id=asset.clinic_id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.CREATED,
        actor_user_id=actor.id,
        new_status=asset.status,
        new_condition=asset.condition,
        new_assigned_to_id=asset.assigned_to_id,
        new_location=asset.location,
        event_metadata={
            "asset_tag": asset.asset_tag,
            "name": asset.name,
        },
    )

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=f"Asset '{asset.asset_tag}' created",
        new_value={
            "clinic_id": asset.clinic_id,
            "asset_tag": asset.asset_tag,
            "name": asset.name,
            "category": _audit_value(asset.category),
            "status": _audit_value(asset.status),
            "condition": _audit_value(asset.condition),
            "ownership": _audit_value(asset.ownership),
        },
    )

    return asset


def get_asset(
    *,
    asset_id: int,
    clinic_id: int,
) -> Asset:
    return _get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )


def list_assets(
    *,
    clinic_id: int,
    query: AssetListQuerySchema | dict | None = None,
) -> dict:
    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    if query is None:
        query = AssetListQuerySchema()

    elif isinstance(query, dict):
        query = AssetListQuerySchema.model_validate(
            query
        )

    statement = db.select(Asset).where(
        Asset.clinic_id == clinic_id
    )

    if query.search:
        search = f"%{query.search}%"

        statement = statement.where(
            or_(
                Asset.asset_tag.ilike(search),
                Asset.name.ilike(search),
                Asset.serial_number.ilike(search),
                Asset.manufacturer.ilike(search),
                Asset.model_number.ilike(search),
                Asset.location.ilike(search),
            )
        )

    if query.category is not None:
        statement = statement.where(
            Asset.category == query.category
        )

    if query.status is not None:
        statement = statement.where(
            Asset.status == query.status
        )

    if query.condition is not None:
        statement = statement.where(
            Asset.condition == query.condition
        )

    if query.ownership is not None:
        statement = statement.where(
            Asset.ownership == query.ownership
        )

    if query.maintenance_status is not None:
        statement = statement.where(
            Asset.maintenance_status
            == query.maintenance_status
        )

    if query.assigned_to_id is not None:
        statement = statement.where(
            Asset.assigned_to_id
            == query.assigned_to_id
        )

    if query.is_active is not None:
        statement = statement.where(
            Asset.is_active == query.is_active
        )

    statement = statement.order_by(
        Asset.created_at.desc(),
        Asset.id.desc(),
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


@transactional
def update_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetUpdateSchema | dict,
) -> Asset:
    clinic = _validate_clinic_for_write(clinic_id)

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
        data = AssetUpdateSchema.model_validate(data)

    updates = data.model_dump(
        exclude_unset=True
    )

    if not updates:
        raise ValidationError(
            "No fields provided for update"
        )

    if _asset_is_terminal(asset):
        raise ConflictError(
            f"Asset {asset.id} is no longer editable"
        )

    _validate_purchase_dates(
        purchase_date=updates.get(
            "purchase_date",
            asset.purchase_date,
        ),
        warranty_expiry=updates.get(
            "warranty_expiry",
            asset.warranty_expiry,
        ),
    )

    if "asset_tag" in updates:
        _validate_asset_tag_unique(
            clinic_id=clinic.id,
            asset_tag=updates["asset_tag"],
            exclude_asset_id=asset.id,
        )

    text_fields = {
        "asset_tag",
        "name",
        "description",
        "location",
        "serial_number",
        "manufacturer",
        "model_number",
        "supplier",
        "notes",
    }

    old_values = {}
    new_values = {}

    for field_name, raw_value in updates.items():
        value = raw_value

        if field_name in text_fields:
            value = _normalize_optional_text(
                value
            )

        current_value = getattr(
            asset,
            field_name,
        )

        if current_value == value:
            continue

        old_values[field_name] = current_value
        new_values[field_name] = value

        setattr(
            asset,
            field_name,
            value,
        )

    if not new_values:
        return asset

    asset.updated_at = _utcnow()

    db.session.flush()

    old_audit, new_audit = _build_audit_changes(
        old_values=old_values,
        new_values=new_values,
    )

    if "condition" in new_values:
        record_asset_history(
            clinic_id=asset.clinic_id,
            asset_id=asset.id,
            event_type=(
                AssetHistoryEventType.CONDITION_CHANGED
            ),
            actor_user_id=actor.id,
            previous_condition=old_values[
                "condition"
            ],
            new_condition=new_values[
                "condition"
            ],
        )

    if "location" in new_values:
        record_asset_history(
            clinic_id=asset.clinic_id,
            asset_id=asset.id,
            event_type=(
                AssetHistoryEventType.LOCATION_CHANGED
            ),
            actor_user_id=actor.id,
            previous_location=old_values[
                "location"
            ],
            new_location=new_values[
                "location"
            ],
        )

    general_changes = {
        key: value
        for key, value in old_values.items()
        if key not in {
            "condition",
            "location",
        }
    }

    if general_changes:
        record_asset_history(
            clinic_id=asset.clinic_id,
            asset_id=asset.id,
            event_type=AssetHistoryEventType.UPDATED,
            actor_user_id=actor.id,
            event_metadata={
                "old": {
                    key: old_audit[key]
                    for key in general_changes
                },
                "new": {
                    key: new_audit[key]
                    for key in general_changes
                },
            },
        )

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=f"Asset '{asset.asset_tag}' updated",
        old_value=old_audit,
        new_value=new_audit,
    )

    return asset


@transactional
def retire_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    retirement_date: date | None = None,
) -> Asset:
    clinic = _validate_clinic_for_write(clinic_id)

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if asset.status == AssetStatus.RETIRED:
        raise ConflictError(
            f"Asset {asset.id} is already retired"
        )

    if asset.status == AssetStatus.DISPOSED:
        raise ConflictError(
            f"Asset {asset.id} has already been disposed"
        )

    if asset.assigned_to_id is not None:
        raise ConflictError(
            "Assigned assets must be returned before retirement"
        )

    if asset.maintenance_status in (
        MaintenanceStatus.SCHEDULED,
        MaintenanceStatus.DUE,
        MaintenanceStatus.IN_PROGRESS,
        MaintenanceStatus.OVERDUE,
    ):
        raise ConflictError(
            "Active maintenance must be resolved before retirement"
        )

    retirement_date = (
        retirement_date or date.today()
    )

    _validate_purchase_dates(
        purchase_date=asset.purchase_date,
        warranty_expiry=asset.warranty_expiry,
    )

    if (
        asset.purchase_date is not None
        and retirement_date < asset.purchase_date
    ):
        raise ValidationError(
            "retirement_date cannot be before purchase_date"
        )

    old_status = asset.status

    asset.status = AssetStatus.RETIRED
    asset.retirement_date = retirement_date
    asset.is_active = False
    asset.updated_at = _utcnow()

    db.session.flush()

    record_asset_history(
        clinic_id=asset.clinic_id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.RETIRED,
        actor_user_id=actor.id,
        previous_status=old_status,
        new_status=asset.status,
        reason="Asset retired",
        event_metadata={
            "retirement_date": retirement_date.isoformat()
        },
    )

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=f"Asset '{asset.asset_tag}' retired",
        old_value={
            "status": _audit_value(old_status),
            "is_active": True,
            "retirement_date": None,
        },
        new_value={
            "status": _audit_value(asset.status),
            "is_active": False,
            "retirement_date": (
                retirement_date.isoformat()
            ),
        },
    )

    return asset


@transactional
def dispose_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    disposal_reason: str,
    disposal_date: date | None = None,
) -> Asset:
    clinic = _validate_clinic_for_write(clinic_id)

    actor = _validate_actor_user(
        actor_user_id=actor_user_id,
        clinic_id=clinic.id,
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic.id,
        for_update=True,
    )

    if asset.status == AssetStatus.DISPOSED:
        raise ConflictError(
            f"Asset {asset.id} is already disposed"
        )

    if asset.retirement_date is None:
        raise ValidationError(
            "Asset must be retired before disposal"
        )

    disposal_reason = _normalize_optional_text(
        disposal_reason
    )

    if disposal_reason is None:
        raise ValidationError(
            "disposal_reason is required"
        )

    if asset.assigned_to_id is not None:
        raise ConflictError(
            "Assigned assets must be returned before disposal"
        )

    if asset.maintenance_status in (
        MaintenanceStatus.SCHEDULED,
        MaintenanceStatus.DUE,
        MaintenanceStatus.IN_PROGRESS,
        MaintenanceStatus.OVERDUE,
    ):
        raise ConflictError(
            "Active maintenance must be resolved before disposal"
        )

    disposal_date = (
        disposal_date or date.today()
    )

    if disposal_date < asset.retirement_date:
        raise ValidationError(
            "disposal_date cannot be before retirement_date"
        )

    old_status = asset.status

    asset.status = AssetStatus.DISPOSED
    asset.disposal_date = disposal_date
    asset.disposal_reason = disposal_reason
    asset.is_active = False
    asset.updated_at = _utcnow()

    db.session.flush()

    record_asset_history(
        clinic_id=asset.clinic_id,
        asset_id=asset.id,
        event_type=AssetHistoryEventType.DISPOSED,
        actor_user_id=actor.id,
        previous_status=old_status,
        new_status=asset.status,
        reason=disposal_reason,
        event_metadata={
            "disposal_date": disposal_date.isoformat(),
        },
    )

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor.id,
        description=f"Asset '{asset.asset_tag}' disposed",
        old_value={
            "status": _audit_value(old_status),
            "is_active": False,
            "disposal_date": None,
            "disposal_reason": None,
        },
        new_value={
            "status": _audit_value(asset.status),
            "is_active": False,
            "disposal_date": disposal_date.isoformat(),
            "disposal_reason": disposal_reason,
        },
    )

    return asset