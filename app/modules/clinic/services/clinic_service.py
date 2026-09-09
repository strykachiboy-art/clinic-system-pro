import secrets
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.extensions import celery, db
from app.core.utils.decorators import transactional
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)
from app.core.audit.services.audit_service import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import (
    ClinicStatus,
    ClinicType,
)
from app.modules.clinic.models.clinic_model import Clinic


# =====================================================================
# HELPERS
# =====================================================================

def _enum_value(value):
    """Return the underlying value when given an enum."""
    return value.value if hasattr(value, "value") else value


def _audit_value(value):
    """
    Convert a value into a JSON-safe representation for audit logs.

    Enum values are reduced to their underlying values and time objects
    are serialized using ISO-8601 format.
    """
    value = _enum_value(value)

    if isinstance(value, time):
        return value.isoformat()

    return value


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _validate_name(name: str) -> str:
    """Validate and normalize a clinic name."""
    if not isinstance(name, str):
        raise ValidationError("Clinic name must be a string")

    name = name.strip()

    if not name:
        raise ValidationError("Clinic name is required")

    return name


def _validate_operating_hours(
    opening_time: time | None,
    closing_time: time | None,
):
    """
    Validate clinic operating hours.
    """
    if (
        opening_time is not None
        and closing_time is not None
        and opening_time >= closing_time
    ):
        raise ValidationError(
            "Opening time must be earlier than closing time"
        )


def _validate_timezone(timezone: str) -> str:
    """Validate that a timezone is a real IANA timezone."""
    if not isinstance(timezone, str):
        raise ValidationError("Timezone must be a string")

    timezone = timezone.strip()

    if not timezone:
        raise ValidationError("Timezone is required")

    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise ValidationError(
            f"Invalid timezone '{timezone}'"
        )

    return timezone


def _get_parent_clinic(
    parent_clinic_id: int,
    *,
    for_update: bool = False,
) -> Clinic:
    """
    Resolve a parent clinic.
    """
    if parent_clinic_id <= 0:
        raise ValidationError("Invalid parent clinic ID")

    query = Clinic.query.filter(
        Clinic.id == parent_clinic_id
    )

    if for_update:
        query = query.with_for_update()

    parent = query.first()

    if parent is None:
        raise NotFoundError(
            f"Parent clinic {parent_clinic_id} not found"
        )

    return parent


def _check_name_conflict(
    name: str,
    parent_clinic_id: int | None,
    exclude_clinic_id: int | None = None,
):
    """
    Prevent duplicate clinic names within the same hierarchy.
    """
    query = Clinic.query.filter(
        Clinic.name == name,
        Clinic.parent_clinic_id == parent_clinic_id,
    )

    if exclude_clinic_id is not None:
        query = query.filter(
            Clinic.id != exclude_clinic_id
        )

    existing = query.first()

    if existing is not None:
        raise ConflictError(
            f"A clinic named '{name}' already exists under "
            "this parent clinic"
        )


def _ensure_active_clinic(clinic: Clinic):
    """Ensure a clinic can participate in operational writes."""
    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic.id} is not active"
        )


def _ensure_no_hierarchy_cycle(
    clinic: Clinic,
    proposed_parent: Clinic,
):
    """
    Ensure assigning proposed_parent cannot create a cycle.

    Example:

        A -> B -> C

    C cannot become the parent of A.
    """
    current = proposed_parent

    visited = set()

    while current is not None:
        if current.id in visited:
            raise ConflictError(
                "Existing clinic hierarchy contains a cycle"
            )

        visited.add(current.id)

        if current.id == clinic.id:
            raise ConflictError(
                "This parent assignment would create "
                "a circular clinic hierarchy"
            )

        current = current.parent_clinic


# =====================================================================
# GET CLINIC
# =====================================================================

def get_clinic(
    clinic_id: int,
    *,
    for_update: bool = False,
) -> Clinic:
    """
    Retrieve a clinic by ID.

    Args:
        clinic_id: Clinic primary key.
        for_update: Lock the row for transactional mutation.
    """
    if clinic_id <= 0:
        raise ValidationError("Invalid clinic ID")

    query = Clinic.query.filter(
        Clinic.id == clinic_id
    )

    if for_update:
        query = query.with_for_update()

    clinic = query.first()

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


# =====================================================================
# LIST CLINICS
# =====================================================================

def list_clinics(
    status: ClinicStatus | None = None,
) -> list[Clinic]:
    """
    List clinics optionally filtered by status.

    Read-only operation.
    """
    query = Clinic.query

    if status is not None:
        query = query.filter(
            Clinic.status == status
        )

    return query.order_by(
        Clinic.name.asc(),
        Clinic.id.asc(),
    ).all()


# =====================================================================
# LIST BRANCHES
# =====================================================================

def list_branches(
    clinic_id: int,
) -> list[Clinic]:
    """
    Return all direct branches belonging to a clinic.
    """
    get_clinic(clinic_id)

    return (
        Clinic.query
        .filter(
            Clinic.parent_clinic_id == clinic_id
        )
        .order_by(
            Clinic.name.asc(),
            Clinic.id.asc(),
        )
        .all()
    )


# =====================================================================
# CREATE CLINIC
# =====================================================================

@transactional
def create_clinic(
    name: str,
    clinic_type: ClinicType = ClinicType.GENERAL,
    parent_clinic_id: int | None = None,
    is_headquarters: bool = False,
    address: str | None = None,
    city: str | None = None,
    country: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    timezone: str = "UTC",
    opening_time=None,
    closing_time=None,
) -> Clinic:
    """
    Create a root clinic or a clinic attached to an existing parent.
    """
    name = _validate_name(name)
    timezone = _validate_timezone(timezone)

    _validate_operating_hours(
        opening_time,
        closing_time,
    )

    if parent_clinic_id is not None and parent_clinic_id <= 0:
        raise ValidationError(
            "Invalid parent clinic ID"
        )

    if is_headquarters and parent_clinic_id is not None:
        raise ValidationError(
            "A headquarters clinic cannot have a parent clinic"
        )

    parent = None

    if parent_clinic_id is not None:
        parent = _get_parent_clinic(
            parent_clinic_id,
            for_update=True,
        )

        _ensure_active_clinic(parent)

    _check_name_conflict(
        name=name,
        parent_clinic_id=parent_clinic_id,
    )

    clinic = Clinic(
        name=name,
        clinic_type=clinic_type,
        status=ClinicStatus.ACTIVE,
        parent_clinic_id=(
            parent.id
            if parent is not None
            else None
        ),
        is_headquarters=is_headquarters,
        address=address,
        city=city,
        country=country,
        phone=phone,
        email=email,
        timezone=timezone,
        opening_time=opening_time,
        closing_time=closing_time,
        ai_credits=0,
        ai_requests_this_month=0,
    )

    db.session.add(clinic)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"Clinic '{clinic.name}' created"
        ),
        new_value={
            "name": clinic.name,
            "clinic_type": _enum_value(
                clinic.clinic_type
            ),
            "status": _enum_value(
                clinic.status
            ),
            "parent_clinic_id": clinic.parent_clinic_id,
            "is_headquarters": clinic.is_headquarters,
        },
    )

    return clinic


# =====================================================================
# CREATE BRANCH
# =====================================================================

@transactional
def create_branch(
    parent_clinic_id: int,
    name: str,
    clinic_type: ClinicType = ClinicType.GENERAL,
    address: str | None = None,
    city: str | None = None,
    country: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    timezone: str = "UTC",
    opening_time=None,
    closing_time=None,
) -> Clinic:
    """
    Create an active non-headquarters branch under an active clinic.
    """
    parent = _get_parent_clinic(
        parent_clinic_id,
        for_update=True,
    )

    _ensure_active_clinic(parent)

    name = _validate_name(name)
    timezone = _validate_timezone(timezone)

    _validate_operating_hours(
        opening_time,
        closing_time,
    )

    _check_name_conflict(
        name=name,
        parent_clinic_id=parent.id,
    )

    branch = Clinic(
        name=name,
        clinic_type=clinic_type,
        status=ClinicStatus.ACTIVE,
        parent_clinic_id=parent.id,
        is_headquarters=False,
        address=address,
        city=city,
        country=country,
        phone=phone,
        email=email,
        timezone=timezone,
        opening_time=opening_time,
        closing_time=closing_time,
        ai_credits=0,
        ai_requests_this_month=0,
    )

    db.session.add(branch)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Clinic",
        entity_id=branch.id,
        description=(
            f"Branch '{branch.name}' created under "
            f"clinic {parent.id}"
        ),
        new_value={
            "name": branch.name,
            "clinic_type": _enum_value(
                branch.clinic_type
            ),
            "parent_clinic_id": branch.parent_clinic_id,
            "is_headquarters": False,
        },
    )

    return branch


# =====================================================================
# UPDATE CLINIC
# =====================================================================

@transactional
def update_clinic(
    clinic_id: int,
    **fields,
) -> Clinic:
    """
    Update editable clinic profile fields.

    Relationship configuration, status, AI credits and API tokens
    are handled by dedicated operations.
    """
    clinic = get_clinic(
        clinic_id,
        for_update=True,
    )

    allowed_fields = {
        "name",
        "clinic_type",
        "address",
        "city",
        "country",
        "phone",
        "email",
        "timezone",
        "opening_time",
        "closing_time",
    }

    unknown_fields = set(fields) - allowed_fields

    if unknown_fields:
        raise ValidationError(
            "Unsupported clinic fields: "
            + ", ".join(sorted(unknown_fields))
        )

    if "name" in fields:
        fields["name"] = _validate_name(
            fields["name"]
        )

    if "timezone" in fields:
        fields["timezone"] = _validate_timezone(
            fields["timezone"]
        )

    opening_time = fields.get(
        "opening_time",
        clinic.opening_time,
    )

    closing_time = fields.get(
        "closing_time",
        clinic.closing_time,
    )

    _validate_operating_hours(
        opening_time,
        closing_time,
    )

    if (
        "name" in fields
        and fields["name"] != clinic.name
    ):
        _check_name_conflict(
            name=fields["name"],
            parent_clinic_id=clinic.parent_clinic_id,
            exclude_clinic_id=clinic.id,
        )

    old_value = {}
    new_value = {}

    for key, new_value_raw in fields.items():
        current_value = getattr(
            clinic,
            key,
        )

        if current_value == new_value_raw:
            continue

        old_value[key] = _audit_value(
            current_value
        )

        new_value[key] = _audit_value(
            new_value_raw
        )

        setattr(
            clinic,
            key,
            new_value_raw,
        )

    if new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Clinic",
            entity_id=clinic.id,
            description=(
                f"Clinic '{clinic.name}' profile updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return clinic


# =====================================================================
# UPDATE BRANCH CONFIGURATION
# =====================================================================

@transactional
def update_branch_configuration(
    clinic_id: int,
    **fields,
) -> Clinic:
    """
    Update parent/headquarters configuration.
    """
    clinic = get_clinic(
        clinic_id,
        for_update=True,
    )

    allowed_fields = {
        "parent_clinic_id",
        "is_headquarters",
    }

    unknown_fields = set(fields) - allowed_fields

    if unknown_fields:
        raise ValidationError(
            "Unsupported branch configuration fields: "
            + ", ".join(sorted(unknown_fields))
        )

    old_parent_id = clinic.parent_clinic_id
    old_is_headquarters = clinic.is_headquarters

    new_parent_id = fields.get(
        "parent_clinic_id",
        clinic.parent_clinic_id,
    )

    new_is_headquarters = fields.get(
        "is_headquarters",
        clinic.is_headquarters,
    )

    if new_parent_id is not None:
        if new_parent_id <= 0:
            raise ValidationError(
                "Invalid parent clinic ID"
            )

        if new_parent_id == clinic.id:
            raise ValidationError(
                "A clinic cannot be its own parent"
            )

    new_parent = None

    if new_parent_id is not None:
        new_parent = _get_parent_clinic(
            new_parent_id,
            for_update=True,
        )

        _ensure_active_clinic(new_parent)

        _ensure_no_hierarchy_cycle(
            clinic,
            new_parent,
        )

        _check_name_conflict(
            name=clinic.name,
            parent_clinic_id=new_parent.id,
            exclude_clinic_id=clinic.id,
        )

    if new_is_headquarters and new_parent_id is not None:
        raise ValidationError(
            "A headquarters clinic cannot have a parent clinic"
        )

    # If a clinic is detached from a parent, it becomes a root.
    clinic.parent_clinic_id = new_parent_id
    clinic.is_headquarters = new_is_headquarters

    old_value = {
        "parent_clinic_id": old_parent_id,
        "is_headquarters": old_is_headquarters,
    }

    new_value = {
        "parent_clinic_id": clinic.parent_clinic_id,
        "is_headquarters": clinic.is_headquarters,
    }

    if old_value != new_value:
        create_audit_log(
            action=AuditAction.UPDATE,
            entity_type="Clinic",
            entity_id=clinic.id,
            description=(
                f"Clinic '{clinic.name}' branch configuration updated"
            ),
            old_value=old_value,
            new_value=new_value,
        )

    return clinic


# =====================================================================
# CHANGE STATUS
# =====================================================================

@transactional
def change_status(
    clinic_id: int,
    new_status: ClinicStatus,
) -> Clinic:
    """
    Change clinic status.
    """
    clinic = get_clinic(
        clinic_id,
        for_update=True,
    )

    if clinic.status == new_status:
        return clinic

    old_status = clinic.status

    clinic.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"Clinic '{clinic.name}' status changed "
            f"to '{new_status.value}'"
        ),
        old_value={
            "status": old_status.value,
        },
        new_value={
            "status": new_status.value,
        },
    )

    return clinic


# =====================================================================
# ADD AI CREDITS
# =====================================================================

@transactional
def add_ai_credits(
    clinic_id: int,
    amount: int,
) -> Clinic:
    """
    Add AI credits to a clinic.

    The clinic row is locked so concurrent credit operations cannot
    overwrite one another.
    """
    if not isinstance(amount, int):
        raise ValidationError(
            "AI credit amount must be an integer"
        )

    if amount <= 0:
        raise ValidationError(
            "AI credit amount must be greater than zero"
        )

    clinic = get_clinic(
        clinic_id,
        for_update=True,
    )

    old_credits = clinic.ai_credits

    clinic.ai_credits += amount

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"{amount} AI credits added to clinic "
            f"'{clinic.name}'"
        ),
        old_value={
            "ai_credits": old_credits,
        },
        new_value={
            "ai_credits": clinic.ai_credits,
        },
    )

    return clinic


# =====================================================================
# REGENERATE API TOKEN
# =====================================================================

@transactional
def regenerate_api_token(
    clinic_id: int,
) -> str:
    """
    Generate and store a new API token.

    The previous token becomes invalid once the transaction commits.
    """
    clinic = get_clinic(
        clinic_id,
        for_update=True,
    )

    old_token_exists = clinic.api_token is not None

    new_token = secrets.token_urlsafe(48)

    clinic.api_token = new_token

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"API token regenerated for clinic "
            f"'{clinic.name}'"
        ),
        old_value={
            "api_token": (
                "present"
                if old_token_exists
                else None
            ),
        },
        new_value={
            "api_token": "present",
        },
    )

    return new_token


# =====================================================================
# CONSUME AI CREDIT
# =====================================================================

def _consume_ai_credit(
    clinic_id: int,
) -> Clinic:
    clinic = get_clinic(
        clinic_id,
        for_update=True,
    )

    _ensure_active_clinic(clinic)

    if clinic.ai_credits <= 0:
        raise ValidationError(
            "Insufficient AI credits"
        )

    old_credits = clinic.ai_credits
    old_requests = clinic.ai_requests_this_month

    clinic.ai_credits -= 1
    clinic.ai_requests_this_month += 1

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"AI credit consumed by clinic "
            f"'{clinic.name}'"
        ),
        old_value={
            "ai_credits": old_credits,
            "ai_requests_this_month": old_requests,
        },
        new_value={
            "ai_credits": clinic.ai_credits,
            "ai_requests_this_month": (
                clinic.ai_requests_this_month
            ),
        },
    )

    return clinic


@transactional
def consume_ai_credit(
    clinic_id: int,
) -> Clinic:
    return _consume_ai_credit(clinic_id)


# =====================================================================
# ENSURE CLINIC ACTIVE
# =====================================================================

def ensure_clinic_active(
    clinic_id: int,
) -> Clinic:
    """
    Return a clinic only when it is active for operational writes.
    """
    clinic = get_clinic(clinic_id)

    _ensure_active_clinic(clinic)

    return clinic