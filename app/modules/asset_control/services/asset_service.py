from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlalchemy import or_

from app.extensions import db
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.asset_enums import AssetStatus
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
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.staff.models.staff_model import Staff


# ============================================================================
# CONSTANTS
# ============================================================================


DEFAULT_PAGE = 1
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 500


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def _validate_positive_id(
    value,
    field_name: str,
) -> int:
    """
    Validate that an identifier is a positive integer.
    """
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
    """
    Validate that the clinic exists and is active for write operations.
    """
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


def _get_asset(
    *,
    asset_id: int,
    clinic_id: int,
) -> Asset:
    """
    Fetch an asset within the authenticated clinic boundary.
    """
    asset_id = _validate_positive_id(
        asset_id,
        "asset_id",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "clinic_id",
    )

    asset = db.session.get(
        Asset,
        asset_id,
    )

    if asset is None or asset.clinic_id != clinic_id:
        raise NotFoundError(
            f"Asset {asset_id} not found"
        )

    return asset


def _validate_actor_user_id(
    actor_user_id: int,
) -> int:
    """
    Validate the audit actor identifier.
    """
    return _validate_positive_id(
        actor_user_id,
        "actor_user_id",
    )


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    """
    Normalize optional text fields.
    """
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            "Text field must be a string"
        )

    value = value.strip()

    return value or None


# ============================================================================
# AUDIT HELPERS
# ============================================================================


def _audit_value(value):
    """
    Convert model values into JSON-safe audit values.
    """
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
    """
    Convert old/new values into audit-safe dictionaries.
    """
    old_audit = {
        field_name: _audit_value(value)
        for field_name, value in old_values.items()
    }

    new_audit = {
        field_name: _audit_value(value)
        for field_name, value in new_values.items()
    }

    return old_audit, new_audit


# ============================================================================
# DATE VALIDATION
# ============================================================================


def _validate_dates(
    *,
    purchase_date: date | None,
    warranty_expiry: date | None,
    last_maintenance_date: date | None,
    next_maintenance_date: date | None,
    retirement_date: date | None,
    disposal_date: date | None,
) -> None:
    """
    Validate chronological relationships between asset dates.
    """

    if (
        purchase_date is not None
        and warranty_expiry is not None
        and warranty_expiry < purchase_date
    ):
        raise ValidationError(
            "warranty_expiry cannot be before purchase_date"
        )

    if (
        last_maintenance_date is not None
        and next_maintenance_date is not None
        and next_maintenance_date < last_maintenance_date
    ):
        raise ValidationError(
            "next_maintenance_date cannot be before "
            "last_maintenance_date"
        )

    if (
        purchase_date is not None
        and retirement_date is not None
        and retirement_date < purchase_date
    ):
        raise ValidationError(
            "retirement_date cannot be before purchase_date"
        )

    if (
        retirement_date is not None
        and disposal_date is not None
        and disposal_date < retirement_date
    ):
        raise ValidationError(
            "disposal_date cannot be before retirement_date"
        )


# ============================================================================
# STAFF ASSIGNMENT VALIDATION
# ============================================================================


def _validate_assigned_staff(
    *,
    assigned_to_id: int | None,
    clinic_id: int,
) -> Staff | None:
    """
    Validate an assigned staff member.

    Staff must:
    - exist
    - belong to the same clinic
    - be active
    """
    if assigned_to_id is None:
        return None

    assigned_to_id = _validate_positive_id(
        assigned_to_id,
        "assigned_to_id",
    )

    staff = db.session.get(
        Staff,
        assigned_to_id,
    )

    if staff is None:
        raise NotFoundError(
            f"Staff {assigned_to_id} not found"
        )

    if staff.clinic_id != clinic_id:
        raise NotFoundError(
            f"Staff {assigned_to_id} not found"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff {assigned_to_id} is not active"
        )

    return staff


# ============================================================================
# ASSET TAG UNIQUENESS
# ============================================================================


def _validate_asset_tag_unique(
    *,
    clinic_id: int,
    asset_tag: str,
    exclude_asset_id: int | None = None,
) -> None:
    """
    Enforce clinic-scoped asset-tag uniqueness.
    """
    statement = db.select(
        Asset.id
    ).where(
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


# ============================================================================
# CREATE ASSET
# ============================================================================


@transactional
def create_asset(
    *,
    clinic_id: int,
    actor_user_id: int,
    data: AssetCreateSchema | dict,
) -> Asset:
    """
    Create a new asset for an active clinic.

    Status and is_active are controlled by the service.
    """

    clinic = _validate_clinic_for_write(
        clinic_id
    )

    actor_user_id = _validate_actor_user_id(
        actor_user_id
    )

    if isinstance(data, dict):
        data = AssetCreateSchema.model_validate(
            data
        )

    _validate_asset_tag_unique(
        clinic_id=clinic.id,
        asset_tag=data.asset_tag,
    )

    _validate_assigned_staff(
        assigned_to_id=data.assigned_to_id,
        clinic_id=clinic.id,
    )

    _validate_dates(
        purchase_date=data.purchase_date,
        warranty_expiry=data.warranty_expiry,
        last_maintenance_date=data.last_maintenance_date,
        next_maintenance_date=data.next_maintenance_date,
        retirement_date=None,
        disposal_date=None,
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
        assigned_to_id=data.assigned_to_id,
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
        maintenance_status=data.maintenance_status,
        last_maintenance_date=data.last_maintenance_date,
        next_maintenance_date=data.next_maintenance_date,
        notes=_normalize_optional_text(
            data.notes
        ),
        is_active=True,
    )

    db.session.add(asset)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor_user_id,
        description=(
            f"Asset '{asset.asset_tag}' created"
        ),
        new_value={
            "clinic_id": asset.clinic_id,
            "asset_tag": asset.asset_tag,
            "name": asset.name,
            "category": _audit_value(
                asset.category
            ),
            "status": _audit_value(
                asset.status
            ),
            "condition": _audit_value(
                asset.condition
            ),
            "ownership": _audit_value(
                asset.ownership
            ),
            "assigned_to_id": asset.assigned_to_id,
        },
    )

    return asset


# ============================================================================
# GET SINGLE ASSET
# ============================================================================


def get_asset(
    *,
    asset_id: int,
    clinic_id: int,
) -> Asset:
    """
    Return one asset within the clinic boundary.
    """
    return _get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )


# ============================================================================
# LIST ASSETS
# ============================================================================


def list_assets(
    *,
    clinic_id: int,
    query: AssetListQuerySchema | dict | None = None,
) -> dict:
    """
    List assets with clinic isolation, filtering, searching,
    deterministic ordering, and pagination.
    """

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

    statement = db.select(
        Asset
    ).where(
        Asset.clinic_id == clinic_id
    )

    # ------------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # FILTERS
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # DETERMINISTIC ORDERING
    # ------------------------------------------------------------------------

    statement = statement.order_by(
        Asset.created_at.desc(),
        Asset.id.desc(),
    )

    # ------------------------------------------------------------------------
    # PAGINATION
    # ------------------------------------------------------------------------

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


# ============================================================================
# UPDATE ASSET
# ============================================================================


@transactional
def update_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    data: AssetUpdateSchema | dict,
) -> Asset:
    """
    Update ordinary mutable asset fields.

    Lifecycle fields such as:
    - status
    - is_active
    - retirement_date
    - disposal_date
    - disposal_reason

    are intentionally NOT handled here. They belong to the
    dedicated lifecycle operations.
    """

    _validate_clinic_for_write(
        clinic_id
    )

    actor_user_id = _validate_actor_user_id(
        actor_user_id
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    if isinstance(data, dict):
        data = AssetUpdateSchema.model_validate(
            data
        )

    updates = data.model_dump(
        exclude_unset=True
    )

    if not updates:
        raise ValidationError(
            "No fields provided for update"
        )

    # ------------------------------------------------------------------------
    # DATE VALIDATION
    # ------------------------------------------------------------------------

    next_purchase_date = updates.get(
        "purchase_date",
        asset.purchase_date,
    )

    next_warranty_expiry = updates.get(
        "warranty_expiry",
        asset.warranty_expiry,
    )

    next_last_maintenance_date = updates.get(
        "last_maintenance_date",
        asset.last_maintenance_date,
    )

    next_next_maintenance_date = updates.get(
        "next_maintenance_date",
        asset.next_maintenance_date,
    )

    _validate_dates(
        purchase_date=next_purchase_date,
        warranty_expiry=next_warranty_expiry,
        last_maintenance_date=next_last_maintenance_date,
        next_maintenance_date=next_next_maintenance_date,
        retirement_date=asset.retirement_date,
        disposal_date=asset.disposal_date,
    )

    # ------------------------------------------------------------------------
    # ASSET TAG
    # ------------------------------------------------------------------------

    if "asset_tag" in updates:
        _validate_asset_tag_unique(
            clinic_id=clinic_id,
            asset_tag=updates["asset_tag"],
            exclude_asset_id=asset.id,
        )

    # ------------------------------------------------------------------------
    # STAFF ASSIGNMENT
    # ------------------------------------------------------------------------

    if "assigned_to_id" in updates:
        _validate_assigned_staff(
            assigned_to_id=updates["assigned_to_id"],
            clinic_id=clinic_id,
        )

    # ------------------------------------------------------------------------
    # MUTABLE TEXT FIELDS
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # NO-OP UPDATE
    # ------------------------------------------------------------------------

    if not new_values:
        return asset

    asset.updated_at = datetime.now(
        timezone.utc
    )

    db.session.flush()

    old_audit, new_audit = _build_audit_changes(
        old_values=old_values,
        new_values=new_values,
    )

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor_user_id,
        description=(
            f"Asset '{asset.asset_tag}' updated"
        ),
        old_value=old_audit,
        new_value=new_audit,
    )

    return asset


# ============================================================================
# RETIRE ASSET
# ============================================================================


@transactional
def retire_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    retirement_date: date | None = None,
) -> Asset:
    """
    Retire an asset.

    A retired asset:
    - has RETIRED status
    - is inactive
    - receives a retirement date
    """

    _validate_clinic_for_write(
        clinic_id
    )

    actor_user_id = _validate_actor_user_id(
        actor_user_id
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    if asset.status == AssetStatus.RETIRED:
        raise ConflictError(
            f"Asset {asset.id} is already retired"
        )

    if asset.status == AssetStatus.DISPOSED:
        raise ConflictError(
            f"Asset {asset.id} has already been disposed"
        )

    retirement_date = (
        retirement_date
        or date.today()
    )

    _validate_dates(
        purchase_date=asset.purchase_date,
        warranty_expiry=asset.warranty_expiry,
        last_maintenance_date=asset.last_maintenance_date,
        next_maintenance_date=asset.next_maintenance_date,
        retirement_date=retirement_date,
        disposal_date=None,
    )

    old_status = asset.status
    old_is_active = asset.is_active
    old_retirement_date = asset.retirement_date

    asset.status = AssetStatus.RETIRED
    asset.retirement_date = retirement_date
    asset.is_active = False
    asset.updated_at = datetime.now(
        timezone.utc
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor_user_id,
        description=(
            f"Asset '{asset.asset_tag}' retired"
        ),
        old_value={
            "status": _audit_value(
                old_status
            ),
            "is_active": old_is_active,
            "retirement_date": _audit_value(
                old_retirement_date
            ),
        },
        new_value={
            "status": _audit_value(
                asset.status
            ),
            "is_active": asset.is_active,
            "retirement_date": _audit_value(
                asset.retirement_date
            ),
        },
    )

    return asset


# ============================================================================
# DISPOSE ASSET
# ============================================================================


@transactional
def dispose_asset(
    *,
    asset_id: int,
    clinic_id: int,
    actor_user_id: int,
    disposal_reason: str,
    disposal_date: date | None = None,
) -> Asset:
    """
    Dispose a previously retired asset.

    Disposal:
    - requires retirement
    - sets DISPOSED status
    - marks asset inactive
    - stores disposal reason/date
    - clears staff assignment
    """

    _validate_clinic_for_write(
        clinic_id
    )

    actor_user_id = _validate_actor_user_id(
        actor_user_id
    )

    asset = _get_asset(
        asset_id=asset_id,
        clinic_id=clinic_id,
    )

    if asset.status == AssetStatus.DISPOSED:
        raise ConflictError(
            f"Asset {asset.id} is already disposed"
        )

    if asset.retirement_date is None:
        raise ValidationError(
            "Asset must be retired before disposal"
        )

    if not isinstance(disposal_reason, str):
        raise ValidationError(
            "disposal_reason is required"
        )

    disposal_reason = disposal_reason.strip()

    if not disposal_reason:
        raise ValidationError(
            "disposal_reason is required"
        )

    if len(disposal_reason) > 500:
        raise ValidationError(
            "disposal_reason must not exceed 500 characters"
        )

    disposal_date = (
        disposal_date
        or date.today()
    )

    _validate_dates(
        purchase_date=asset.purchase_date,
        warranty_expiry=asset.warranty_expiry,
        last_maintenance_date=asset.last_maintenance_date,
        next_maintenance_date=asset.next_maintenance_date,
        retirement_date=asset.retirement_date,
        disposal_date=disposal_date,
    )

    old_status = asset.status
    old_is_active = asset.is_active
    old_disposal_date = asset.disposal_date
    old_disposal_reason = asset.disposal_reason
    old_assigned_to_id = asset.assigned_to_id

    asset.status = AssetStatus.DISPOSED
    asset.disposal_date = disposal_date
    asset.disposal_reason = disposal_reason
    asset.is_active = False
    asset.assigned_to_id = None
    asset.updated_at = datetime.now(
        timezone.utc
    )

    db.session.flush()

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Asset",
        entity_id=asset.id,
        user_id=actor_user_id,
        description=(
            f"Asset '{asset.asset_tag}' disposed"
        ),
        old_value={
            "status": _audit_value(
                old_status
            ),
            "is_active": old_is_active,
            "disposal_date": _audit_value(
                old_disposal_date
            ),
            "disposal_reason": old_disposal_reason,
            "assigned_to_id": old_assigned_to_id,
        },
        new_value={
            "status": _audit_value(
                asset.status
            ),
            "is_active": asset.is_active,
            "disposal_date": _audit_value(
                asset.disposal_date
            ),
            "disposal_reason": asset.disposal_reason,
            "assigned_to_id": asset.assigned_to_id,
        },
    )
    return asset