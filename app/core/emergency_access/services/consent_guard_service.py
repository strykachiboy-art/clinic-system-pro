from __future__ import annotations

from datetime import datetime, timezone

from app.core.emergency_access.models.consent_guard_model import (
    ConsentGuardEvaluation,
)
from app.core.emergency_access.models.emergency_access_model import (
    EmergencyAccessGrant,
)
from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
    EmergencyAccessStatus,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from app.core.utils.decorators import transactional
from app.extensions import db


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


def _normalize_required_string(
    value,
    field_name: str,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        raise ValidationError(
            f"{field_name} is required"
        )

    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_optional_string(
    value,
    field_name: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"{field_name} must be a string"
        )

    value = value.strip()

    if not value:
        return None

    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed "
            f"{max_length} characters"
        )

    return value


def _normalize_role(
    role,
) -> Role:
    if isinstance(role, Role):
        return role

    try:
        return Role(role)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Invalid recipient role"
        ) from exc


@transactional
def evaluate_consent_guard(
    *,
    actor_id: int,
    patient_id: int,
    clinic_id: int,
    recipient_role: str,
    purpose: str,
    emergency_exception: bool,
    consent_reference: str | None = None,
    policy_context: dict | None = None,
) -> ConsentGuardEvaluation:
    actor_id = _validate_positive_id(
        actor_id,
        "Actor ID",
    )

    patient_id = _validate_positive_id(
        patient_id,
        "Patient ID",
    )

    clinic_id = _validate_positive_id(
        clinic_id,
        "Clinic ID",
    )

    recipient_role = _normalize_required_string(
        recipient_role,
        "Recipient role",
        50,
    )

    purpose = _normalize_required_string(
        purpose,
        "Purpose",
        255,
    )

    consent_reference = _normalize_optional_string(
        consent_reference,
        "Consent reference",
        255,
    )

    if not isinstance(
        emergency_exception,
        bool,
    ):
        raise ValidationError(
            "Emergency exception must be a boolean"
        )

    if policy_context is not None and not isinstance(
        policy_context,
        dict,
    ):
        raise ValidationError(
            "Policy context must be an object"
        )

    role = _normalize_role(
        recipient_role,
    )

    decision = ConsentGuardDecision.DENY
    effective_from = None
    effective_until = None
    emergency_access_id = None

    from app.modules.patient.models.patient_model import (
        Patient,
    )

    patient = db.session.execute(
        db.select(Patient)
        .where(
            Patient.id == patient_id,
            Patient.clinic_id == clinic_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if patient is None:
        raise NotFoundError(
            f"Patient {patient_id} not found"
        )

    if emergency_exception:
        active_grant = db.session.execute(
            db.select(EmergencyAccessGrant)
            .where(
                EmergencyAccessGrant.patient_id
                == patient_id,
                EmergencyAccessGrant.clinic_id
                == clinic_id,
                EmergencyAccessGrant.requester_user_id
                == actor_id,
                EmergencyAccessGrant.status
                == EmergencyAccessStatus.ACTIVE,
                EmergencyAccessGrant.expires_at
                > _utcnow(),
            )
            .order_by(
                EmergencyAccessGrant.granted_at.desc(),
                EmergencyAccessGrant.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()

        if active_grant is not None:
            decision = (
                ConsentGuardDecision.EMERGENCY_EXCEPTION
            )
            emergency_access_id = (
                active_grant.id
            )
            effective_from = (
                active_grant.granted_at
            )
            effective_until = (
                active_grant.expires_at
            )
        else:
            decision = ConsentGuardDecision.DENY
    else:
        if (
            role == Role.PATIENT
            and patient.user_id == actor_id
        ):
            decision = ConsentGuardDecision.ALLOW
        elif consent_reference:
            decision = ConsentGuardDecision.ALLOW
        else:
            decision = ConsentGuardDecision.DENY

    evaluation = ConsentGuardEvaluation(
        emergency_access_id=(
            emergency_access_id
        ),
        clinic_id=clinic_id,
        patient_id=patient_id,
        requester_user_id=actor_id,
        recipient_role=role.value,
        purpose=purpose,
        decision=decision,
        consent_reference=consent_reference,
        policy_context=policy_context,
        emergency_exception=(
            decision
            == ConsentGuardDecision.EMERGENCY_EXCEPTION
        ),
        effective_from=effective_from,
        effective_until=effective_until,
    )

    db.session.add(
        evaluation
    )

    return evaluation