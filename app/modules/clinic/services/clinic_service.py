import secrets

from app.extensions import db
from app.core.utils.decorators import transactional
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    ConflictError,
)
from app.core.audit.services.audit_services import create_audit_log
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


def _validate_name(name: str) -> str:
    """Validate and normalize a clinic name."""
    if not name or not name.strip():
        raise ValidationError("Clinic name is required")

    return name.strip()


def _validate_operating_hours(opening_time, closing_time):
    """
    Validate clinic operating hours.

    Both values are optional, but when supplied together the opening
    time must be earlier than the closing time.
    """
    if (
        opening_time is not None
        and closing_time is not None
        and opening_time >= closing_time
    ):
        raise ValidationError(
            "Opening time must be earlier than closing time"
        )


def _get_parent_clinic(parent_clinic_id: int) -> Clinic:
    """Resolve a parent clinic or raise 404."""
    parent = Clinic.query.get(parent_clinic_id)

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

    A headquarters/root clinic and a branch may technically have the
    same name under different parents, but two clinics under the same
    parent should not.
    """
    query = Clinic.query.filter_by(
        name=name,
        parent_clinic_id=parent_clinic_id,
    )

    if exclude_clinic_id is not None:
        query = query.filter(
            Clinic.id != exclude_clinic_id
        )

    existing = query.first()

    if existing is not None:
        raise ConflictError(
            f"A clinic named '{name}' already exists under "
            f"this parent clinic"
        )


# =====================================================================
# GET CLINIC
# =====================================================================

def get_clinic(clinic_id: int) -> Clinic:
    """
    Retrieve a clinic by ID.

    Raises:
        NotFoundError: when the clinic does not exist.
    """
    clinic = Clinic.query.get(clinic_id)

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
    """
    query = Clinic.query

    if status is not None:
        query = query.filter_by(
            status=status
        )

    return query.order_by(
        Clinic.name.asc()
    ).all()


# =====================================================================
# LIST BRANCHES
# =====================================================================

def list_branches(clinic_id: int) -> list[Clinic]:
    """
    Return all direct branches belonging to a clinic.

    The parent clinic must exist.
    """
    get_clinic(clinic_id)

    return (
        Clinic.query
        .filter_by(parent_clinic_id=clinic_id)
        .order_by(Clinic.name.asc())
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
    Create a clinic.

    This supports both:

        - a root/headquarters clinic
        - a clinic attached to an existing parent

    Branch-specific creation should normally go through create_branch().
    """
    name = _validate_name(name)

    _validate_operating_hours(
        opening_time,
        closing_time,
    )

    parent = None

    if parent_clinic_id is not None:
        parent = _get_parent_clinic(
            parent_clinic_id
        )

    # A clinic cannot be its own parent.
    # This is also protected at the DB level by:
    # ck_clinics_not_self_parent.
    #
    # This explicit check gives callers a clean application error.
    if parent_clinic_id is not None:
        if parent_clinic_id == 0:
            raise ValidationError(
                "Invalid parent clinic ID"
            )

    _check_name_conflict(
        name=name,
        parent_clinic_id=parent_clinic_id,
    )

    # A headquarters is expected to be a root clinic.
    if is_headquarters and parent_clinic_id is not None:
        raise ValidationError(
            "A headquarters clinic cannot have a parent clinic"
        )

    clinic = Clinic(
        name=name,
        clinic_type=clinic_type,
        status=ClinicStatus.ACTIVE,
        parent_clinic_id=parent_clinic_id,
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
    Create a branch under an existing clinic.

    Branches are always:
        - ACTIVE
        - non-headquarters
        - attached to parent_clinic_id
    """
    parent = _get_parent_clinic(
        parent_clinic_id
    )

    name = _validate_name(name)

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
    are intentionally handled by their dedicated services.
    """
    clinic = get_clinic(clinic_id)

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

        old_value[key] = _enum_value(
            current_value
        )

        new_value[key] = _enum_value(
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

    Supported fields:

        parent_clinic_id:
            - integer -> attach to parent
            - None -> detach from parent

        is_headquarters:
            - True -> make headquarters
            - False -> make non-headquarters
    """
    clinic = get_clinic(clinic_id)

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

    # -------------------------------------------------------------
    # Parent validation
    # -------------------------------------------------------------

    if new_parent_id == clinic.id:
        raise ValidationError(
            "A clinic cannot be its own parent"
        )

    new_parent = None

    if new_parent_id is not None:
        new_parent = _get_parent_clinic(
            new_parent_id
        )

        # Prevent circular hierarchy.
        #
        # Example:
        #
        # A -> B -> C
        #
        # C cannot become parent of A.
        #
        # Walk upward from the proposed parent and ensure that we
        # never encounter the clinic being modified.
        current = new_parent

        while current is not None:
            if current.id == clinic.id:
                raise ConflictError(
                    "This parent assignment would create "
                    "a circular clinic hierarchy"
                )

            current = current.parent_clinic

    # Headquarters must be a root clinic.
    if new_is_headquarters and new_parent_id is not None:
        raise ValidationError(
            "A headquarters clinic cannot have a parent clinic"
        )

    # If explicitly detaching a clinic, it is now a root.
    # is_headquarters remains whatever the caller requested.
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
    clinic = get_clinic(clinic_id)

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

    Credits can only be added in positive amounts.
    """
    clinic = get_clinic(clinic_id)

    if amount <= 0:
        raise ValidationError(
            "AI credit amount must be greater than zero"
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
    Generate and store a new API token for a clinic.

    The previous token is invalidated immediately.
    """
    clinic = get_clinic(clinic_id)

    old_token_exists = clinic.api_token is not None

    # secrets.token_urlsafe provides a cryptographically secure token.
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
            "api_token": "present"
            if old_token_exists
            else None,
        },
        new_value={
            "api_token": "present",
        },
    )

    return new_token


def consume_ai_credit(clinic_id: int) -> Clinic:
    clinic = get_clinic(clinic_id)

    if clinic.ai_credits <= 0:
        raise ValidationError("Insufficient AI credits")

    clinic.ai_credits -= 1
    clinic.ai_requests_this_month += 1

    return clinic


def ensure_clinic_active(clinic_id: int) -> Clinic:
    """Return a clinic only when it is active for operational writes."""
    clinic = get_clinic(clinic_id)

    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic_id} is not active"
        )

    return clinic