from __future__ import annotations

from app.core.emergency_access.models.consent_guard_model import (
    ConsentGuardEvaluation,
)
from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
)


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
    raise NotImplementedError