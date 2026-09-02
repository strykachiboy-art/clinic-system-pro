import secrets
from app.extensions import db, celery
from app.core.utils.decorators import transactional
from app.core.exceptions import NotFoundError, ValidationError, InsufficientCreditsError
from app.core.audit.services.audit_services import create_audit_log
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus, ClinicType
from app.modules.clinic.models.clinic_model import Clinic

# Explicit whitelist so a route can't push arbitrary kwargs (e.g.
# ai_credits, api_token) through the generic update path.
_EDITABLE_FIELDS = {
    "name", "clinic_type", "address", "city", "country",
    "phone", "email", "timezone", "opening_time", "closing_time",
}


def get_clinic(clinic_id: int) -> Clinic:
    clinic = Clinic.query.get(clinic_id)
    if clinic is None:
        raise NotFoundError(f"Clinic {clinic_id} not found")
    return clinic


def list_clinics(status: ClinicStatus | None = None) -> list[Clinic]:
    query = Clinic.query
    if status is not None:
        query = query.filter_by(status=status)
    return query.order_by(Clinic.name).all()


def list_branches(clinic_id: int) -> list[Clinic]:
    get_clinic(clinic_id)  # raises NotFoundError if parent doesn't exist
    return Clinic.query.filter_by(parent_clinic_id=clinic_id).order_by(Clinic.name).all()


@transactional
def create_clinic(name: str, clinic_type: ClinicType = ClinicType.GENERAL,
                   is_headquarters: bool = False, parent_clinic_id: int | None = None,
                   **fields) -> Clinic:
    if not name or not name.strip():
        raise ValidationError("Clinic name is required")

    if parent_clinic_id is not None:
        get_clinic(parent_clinic_id)  # 404s if parent doesn't exist
        if is_headquarters:
            raise ValidationError("A branch clinic cannot also be marked as headquarters")

    unknown = set(fields) - _EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unknown clinic field(s): {', '.join(sorted(unknown))}")

    clinic = Clinic(
        name=name.strip(),
        clinic_type=clinic_type,
        is_headquarters=is_headquarters,
        parent_clinic_id=parent_clinic_id,
        **fields,
    )
    db.session.add(clinic)
    db.session.flush()  # get clinic.id before logging

    create_audit_log(
        action=AuditAction.CREATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=f"Clinic '{clinic.name}' created",
        new_value={"name": clinic.name, "clinic_type": clinic.clinic_type.value},
    )
    return clinic


def create_branch(parent_clinic_id: int, name: str, **fields) -> Clinic:
    """Convenience wrapper — a branch is just a clinic with a parent set."""
    return create_clinic(
        name=name,
        parent_clinic_id=parent_clinic_id,
        is_headquarters=False,
        **fields,
    )


@transactional
def update_clinic(clinic_id: int, **fields) -> Clinic:
    clinic = get_clinic(clinic_id)

    unknown = set(fields) - _EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unknown clinic field(s): {', '.join(sorted(unknown))}")

    # Only record what actually changed, not a full dump on every edit.
    old_value, new_value = {}, {}
    for key, new_val in fields.items():
        current_val = getattr(clinic, key)
        if current_val != new_val:
            old_value[key] = current_val.value if hasattr(current_val, "value") else current_val
            new_value[key] = new_val.value if hasattr(new_val, "value") else new_val
            setattr(clinic, key, new_val)

    if not new_value:
        return clinic  # nothing changed, nothing to log

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=f"Clinic '{clinic.name}' updated",
        old_value=old_value,
        new_value=new_value,
    )
    return clinic


@transactional
def change_status(clinic_id: int, new_status: ClinicStatus) -> Clinic:
    clinic = get_clinic(clinic_id)

    if clinic.status == new_status:
        return clinic

    old_status = clinic.status.value
    clinic.status = new_status

    create_audit_log(
        action=AuditAction.STATUS_CHANGE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=f"Clinic '{clinic.name}' status changed",
        old_value={"status": old_status},
        new_value={"status": new_status.value},
    )
    return clinic


# ---------------------------------------------------------------------
# AI credit metering — Clinic carries ai_credits / ai_requests_this_month
# since billing for AI usage is per-clinic, not per-AI-module-record.
# ---------------------------------------------------------------------

@transactional
def add_ai_credits(clinic_id: int, amount: int) -> Clinic:
    if amount <= 0:
        raise ValidationError("Credit amount must be positive")

    clinic = get_clinic(clinic_id)
    old_credits = clinic.ai_credits
    clinic.ai_credits += amount

    create_audit_log(
        action=AuditAction.UPDATE,
        entity_type="Clinic",
        entity_id=clinic.id,
        description=f"{amount} AI credits added",
        old_value={"ai_credits": old_credits},
        new_value={"ai_credits": clinic.ai_credits},
    )
    return clinic


@transactional
def consume_ai_credit(clinic_id: int, amount: int = 1) -> Clinic:
    """
    Call this BEFORE making a billable AI call, not after — a failed
    credit check should never cost a real OpenAI request.
    No audit log here: the AI module logs every individual AI call
    itself per spec, so this would just be redundant noise.
    """
    clinic = get_clinic(clinic_id)
    if clinic.ai_credits < amount:
        raise InsufficientCreditsError(
            f"Clinic {clinic_id} has {clinic.ai_credits} credits, needs {amount}"
        )
    clinic.ai_credits -= amount
    clinic.ai_requests_this_month += amount
    return clinic


@celery.task(name="reset_monthly_ai_usage")
def reset_monthly_ai_usage():
    """Run monthly via celery beat. Resets usage counter, not credit balance."""
    clinics = Clinic.query.filter(Clinic.ai_requests_this_month > 0).all()
    for clinic in clinics:
        clinic.ai_requests_this_month = 0
    db.session.commit()
    return len(clinics)


@transactional
def regenerate_api_token(clinic_id: int) -> str:
    """
    Returns the raw token ONCE.
    TODO: Clinic.api_token is currently a plain String column — before
    this goes anywhere near production, switch to storing a hash
    (hashlib.sha256) and compare hashes on verification, same as a
    password. Returning the raw value here is fine either way, since
    that's the only moment the caller ever sees it.
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