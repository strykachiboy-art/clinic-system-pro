import secrets

from app.extensions import db, celery

from app.core.utils.decorators import transactional

from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    InsufficientCreditsError,
)

from app.core.audit.services.audit_services import (
    create_audit_log,
)

from app.core.enums.audit_enums import AuditAction

from app.core.enums.clinic_enums import (
    ClinicStatus,
    ClinicType,
)

from app.modules.clinic.models.clinic_model import Clinic


# ============================================================
# Constants
# ============================================================

_EDITABLE_FIELDS = {
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

_UNSET = object()


# ============================================================
# Retrieval
# ============================================================

def get_clinic(clinic_id: int) -> Clinic:
    """
    Retrieve a clinic regardless of its status.

    IMPORTANT:
    This method intentionally does NOT require the clinic
    to be active because historical data must remain accessible
    after a clinic is suspended or deactivated.
    """
    clinic = db.session.get(Clinic, clinic_id)

    if clinic is None:
        raise NotFoundError(
            f"Clinic {clinic_id} not found"
        )

    return clinic


def list_clinics(
    status: ClinicStatus | None = None,
) -> list[Clinic]:
    """
    List clinics.

    If status is provided, only clinics with that status
    are returned.
    """
    query = Clinic.query

    if status is not None:
        query = query.filter(
            Clinic.status == status
        )

    return (
        query
        .order_by(Clinic.name.asc())
        .all()
    )


def list_branches(
    clinic_id: int,
) -> list[Clinic]:
    """
    Return all direct branches belonging to a clinic.

    The parent clinic can be active, suspended, or inactive.
    Existing branch relationships are historical configuration
    and should not disappear when a parent becomes inactive.
    """
    get_clinic(clinic_id)

    return (
        Clinic.query
        .filter(
            Clinic.parent_clinic_id == clinic_id
        )
        .order_by(Clinic.name.asc())
        .all()
    )


# ============================================================
# Clinic lifecycle helpers
# ============================================================

def ensure_clinic_active(
    clinic_id: int,
) -> Clinic:
    """
    Ensure that a clinic is currently active.

    Use this helper before operational WRITE actions.

    READ operations should continue using get_clinic()
    so historical records remain accessible.
    """
    clinic = get_clinic(clinic_id)

    if clinic.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            f"Clinic {clinic_id} is not active"
        )

    return clinic


# ============================================================
# Validation helpers
# ============================================================

def _validate_parent_clinic(
    parent_clinic_id: int,
    *,
    clinic_id: int | None = None,
) -> Clinic:
    """
    Validate a proposed parent clinic.

    A clinic cannot be its own parent, and a branch can only
    be assigned to an ACTIVE parent.
    """
    if (
        clinic_id is not None
        and parent_clinic_id == clinic_id
    ):
        raise ValidationError(
            "A clinic cannot be its own parent"
        )

    parent = get_clinic(parent_clinic_id)

    if parent.status != ClinicStatus.ACTIVE:
        raise ValidationError(
            "A branch can only belong to an active parent clinic"
        )

    return parent


def _validate_branch_configuration(
    *,
    parent_clinic_id: int | None,
    is_headquarters: bool,
    clinic_id: int | None = None,
):
    """
    Validate parent/headquarters configuration.

    Rules:

    - Headquarters cannot have a parent.
    - A parent must exist and be active.
    - A clinic may be detached by setting parent_clinic_id=None.
    - A detached clinic may remain non-headquarters.
    """
    if (
        is_headquarters
        and parent_clinic_id is not None
    ):
        raise ValidationError(
            "A headquarters clinic cannot have a parent clinic"
        )

    if parent_clinic_id is not None:
        _validate_parent_clinic(
            parent_clinic_id,
            clinic_id=clinic_id,
        )


def _validate_update_fields(
    fields: dict,
):
    """
    Prevent callers from modifying protected clinic fields
    through the general clinic update operation.
    """
    unknown = set(fields) - _EDITABLE_FIELDS

    if unknown:
        raise ValidationError(
            "Unknown clinic field(s): "
            + ", ".join(sorted(unknown))
        )


def _validate_operating_hours(
    *,
    opening_time,
    closing_time,
):
    """
    Validate clinic operating hours.

    If both values are provided, closing_time must be later
    than opening_time.

    Overnight clinics are intentionally not supported by this
    validation. If overnight operation is required later,
    this rule can be expanded.
    """
    if (
        opening_time is not None
        and closing_time is not None
        and closing_time <= opening_time
    ):
        raise ValidationError(
            "Closing time must be later than opening time"
        )


# ============================================================
# Internal clinic creation
# ============================================================

def _create_clinic(
    *,
    name: str,
    clinic_type: ClinicType = ClinicType.GENERAL,
    is_headquarters: bool = False,
    parent_clinic_id: int | None = None,
    **fields,
) -> Clinic:
    """
    Internal clinic creation implementation.

    This function intentionally has NO @transactional decorator.
    Public transaction boundaries are defined by create_clinic()
    and create_branch().
    """
    if not name or not name.strip():
        raise ValidationError(
            "Clinic name is required"
        )

    _validate_update_fields(fields)

    _validate_branch_configuration(
        parent_clinic_id=parent_clinic_id,
        is_headquarters=is_headquarters,
    )

    _validate_operating_hours(
        opening_time=fields.get("opening_time"),
        closing_time=fields.get("closing_time"),
    )

    clinic = Clinic(
        name=name.strip(),
        clinic_type=clinic_type,
        status=ClinicStatus.ACTIVE,
        is_headquarters=is_headquarters,
        parent_clinic_id=parent_clinic_id,
        **fields,
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
            "clinic_type": clinic.clinic_type.value,
            "status": clinic.status.value,
            "is_headquarters": clinic.is_headquarters,
            "parent_clinic_id": clinic.parent_clinic_id,
        },
    )

    return clinic


# ============================================================
# Clinic creation
# ============================================================

@transactional
def create_clinic(
    name: str,
    clinic_type: ClinicType = ClinicType.GENERAL,
    is_headquarters: bool = False,
    parent_clinic_id: int | None = None,
    **fields,
) -> Clinic:
    """
    Create a new clinic.

    New clinics are always created ACTIVE.

    This is a top-level transaction boundary.
    """
    return _create_clinic(
        name=name,
        clinic_type=clinic_type,
        is_headquarters=is_headquarters,
        parent_clinic_id=parent_clinic_id,
        **fields,
    )


# ============================================================
# Branch creation
# ============================================================

@transactional
def create_branch(
    parent_clinic_id: int,
    name: str,
    **fields,
) -> Clinic:
    """
    Create a new branch under an active parent clinic.

    This uses the internal _create_clinic() function instead
    of calling the transactional create_clinic() function,
    preventing nested transaction decorators.
    """
    _validate_parent_clinic(
        parent_clinic_id
    )

    return _create_clinic(
        name=name,
        parent_clinic_id=parent_clinic_id,
        is_headquarters=False,
        **fields,
    )


# ============================================================
# Clinic profile update
# ============================================================

@transactional
def update_clinic(
    clinic_id: int,
    **fields,
) -> Clinic:
    """
    Update editable clinic profile information.

    This operation intentionally does not modify:

    - status
    - parent_clinic_id
    - is_headquarters
    - ai_credits
    - api_token
    - ai_requests_this_month

    Those concerns have dedicated service operations.
    """
    clinic = get_clinic(clinic_id)

    _validate_update_fields(fields)

    # Validate resulting operating hours, not merely
    # the values supplied in this request.
    new_opening_time = (
        clinic.opening_time
        if "opening_time" not in fields
        else fields["opening_time"]
    )

    new_closing_time = (
        clinic.closing_time
        if "closing_time" not in fields
        else fields["closing_time"]
    )

    _validate_operating_hours(
        opening_time=new_opening_time,
        closing_time=new_closing_time,
    )

    old_value = {}
    new_value = {}

    for key, new_val in fields.items():
        current_val = getattr(
            clinic,
            key,
        )

        if current_val == new_val:
            continue

        old_value[key] = (
            current_val.value
            if hasattr(current_val, "value")
            else current_val
        )

        new_value[key] = (
            new_val.value
            if hasattr(new_val, "value")
            else new_val
        )

        setattr(
            clinic,
            key,
            new_val,
        )

    if not new_value:
        return clinic

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"Clinic '{clinic.name}' updated"
        ),
        old_value=old_value,
        new_value=new_value,
    )

    return clinic


# ============================================================
# Branch configuration
# ============================================================

@transactional
def update_branch_configuration(
    clinic_id: int,
    parent_clinic_id=_UNSET,
    is_headquarters=_UNSET,
) -> Clinic:
    """
    Update a clinic's branch/headquarters configuration.

    Supported operations:

    - Assign an active parent.
    - Detach from the current parent with None.
    - Mark a clinic as headquarters.
    - Remove headquarters status.

    A headquarters clinic cannot have a parent.
    """
    clinic = get_clinic(clinic_id)

    new_parent_id = (
        clinic.parent_clinic_id
        if parent_clinic_id is _UNSET
        else parent_clinic_id
    )

    new_is_headquarters = (
        clinic.is_headquarters
        if is_headquarters is _UNSET
        else is_headquarters
    )

    _validate_branch_configuration(
        parent_clinic_id=new_parent_id,
        is_headquarters=new_is_headquarters,
        clinic_id=clinic.id,
    )

    old_value = {
        "parent_clinic_id": clinic.parent_clinic_id,
        "is_headquarters": clinic.is_headquarters,
    }

    if (
        old_value["parent_clinic_id"]
        == new_parent_id
        and
        old_value["is_headquarters"]
        == new_is_headquarters
    ):
        return clinic

    clinic.parent_clinic_id = new_parent_id
    clinic.is_headquarters = new_is_headquarters

    new_value = {
        "parent_clinic_id": clinic.parent_clinic_id,
        "is_headquarters": clinic.is_headquarters,
    }

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"Clinic '{clinic.name}' "
            "branch configuration updated"
        ),
        old_value=old_value,
        new_value=new_value,
    )

    return clinic


# ============================================================
# Clinic status
# ============================================================

@transactional
def change_status(
    clinic_id: int,
    new_status: ClinicStatus,
) -> Clinic:
    """
    Change clinic lifecycle status.

    Allowed transitions:

        ACTIVE
            -> INACTIVE
            -> SUSPENDED

        INACTIVE
            -> ACTIVE

        SUSPENDED
            -> ACTIVE

    Deactivation/suspension does NOT delete historical data.
    """
    clinic = get_clinic(clinic_id)

    if clinic.status == new_status:
        return clinic

    allowed_transitions = {
        ClinicStatus.ACTIVE: {
            ClinicStatus.INACTIVE,
            ClinicStatus.SUSPENDED,
        },
        ClinicStatus.INACTIVE: {
            ClinicStatus.ACTIVE,
        },
        ClinicStatus.SUSPENDED: {
            ClinicStatus.ACTIVE,
        },
    }

    allowed = allowed_transitions.get(
        clinic.status,
        set(),
    )

    if new_status not in allowed:
        raise ValidationError(
            "Cannot change clinic status from "
            f"{clinic.status.value} "
            f"to {new_status.value}"
        )

    old_status = clinic.status.value

    clinic.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"Clinic '{clinic.name}' status changed "
            f"from {old_status} "
            f"to {new_status.value}"
        ),
        old_value={
            "status": old_status,
        },
        new_value={
            "status": new_status.value,
        },
    )

    return clinic


# ============================================================
# AI credits
# ============================================================

@transactional
def add_ai_credits(
    clinic_id: int,
    amount: int,
) -> Clinic:
    """
    Add AI credits to a clinic.

    This is an administrative operation and therefore does
    not require the clinic to be active.
    """
    if amount <= 0:
        raise ValidationError(
            "Credit amount must be positive"
        )

    clinic = get_clinic(clinic_id)

    old_credits = clinic.ai_credits

    clinic.ai_credits += amount

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"{amount} AI credits added"
        ),
        old_value={
            "ai_credits": old_credits,
        },
        new_value={
            "ai_credits": clinic.ai_credits,
        },
    )

    return clinic


@transactional
def consume_ai_credit(
    clinic_id: int,
    amount: int = 1,
) -> Clinic:
    """
    Consume AI credits.

    AI operations are operational activity, so the clinic
    must be ACTIVE.
    """
    if amount <= 0:
        raise ValidationError(
            "Credit amount must be positive"
        )

    clinic = ensure_clinic_active(
        clinic_id
    )

    if clinic.ai_credits < amount:
        raise InsufficientCreditsError(
            f"Clinic {clinic_id} has "
            f"{clinic.ai_credits} credits, "
            f"needs {amount}"
        )

    old_credits = clinic.ai_credits
    old_monthly_usage = (
        clinic.ai_requests_this_month
    )

    clinic.ai_credits -= amount
    clinic.ai_requests_this_month += amount

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=(
            f"{amount} AI credit(s) consumed"
        ),
        old_value={
            "ai_credits": old_credits,
            "ai_requests_this_month": (
                old_monthly_usage
            ),
        },
        new_value={
            "ai_credits": clinic.ai_credits,
            "ai_requests_this_month": (
                clinic.ai_requests_this_month
            ),
        },
    )

    return clinic


# ============================================================
# Monthly AI usage reset
# ============================================================

@celery.task(
    name="reset_monthly_ai_usage"
)
def reset_monthly_ai_usage():
    """
    Reset monthly AI request counters.

    This is a maintenance task and does not depend on clinic
    status because usage history/counters are administrative
    data rather than operational clinic activity.
    """
    clinics = (
        Clinic.query
        .filter(
            Clinic.ai_requests_this_month > 0
        )
        .all()
    )

    for clinic in clinics:
        clinic.ai_requests_this_month = 0

    db.session.commit()

    return len(clinics)


# ============================================================
# API token
# ============================================================

@transactional
def regenerate_api_token(
    clinic_id: int,
) -> str:
    """
    Generate and store a new API token.

    The raw token is returned to the caller once.

    Token regeneration is an administrative operation and
    therefore does not require the clinic to be ACTIVE.
    """
    clinic = get_clinic(clinic_id)

    raw_token = secrets.token_urlsafe(32)

    clinic.api_token = raw_token

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description="API token regenerated",
    )

    return raw_token