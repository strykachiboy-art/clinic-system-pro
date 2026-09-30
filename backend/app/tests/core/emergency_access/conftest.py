from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
    EmergencyAccessStatus,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus


@pytest.fixture()
def make_emergency_staff(make_staff):
    def _make(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
        user_is_active=True,
        **overrides,
    ):
        return make_staff(
            clinic,
            role=role,
            status=status,
            user_is_active=user_is_active,
            **overrides,
        )

    return _make


@pytest.fixture()
def emergency_staff(make_emergency_staff, clinic):
    return make_emergency_staff(
        clinic,
        role=Role.DOCTOR,
    )


@pytest.fixture()
def emergency_nurse(make_emergency_staff, clinic):
    return make_emergency_staff(
        clinic,
        role=Role.NURSE,
    )


@pytest.fixture()
def emergency_reviewer(make_user, clinic):
    return make_user(
        clinic,
        role=Role.ADMIN,
        email="emergency.reviewer@test.com",
    )


@pytest.fixture()
def emergency_super_admin(make_user):
    return make_user(
        clinic=None,
        role=Role.SUPER_ADMIN,
        email="emergency.superadmin@test.com",
    )


@pytest.fixture()
def emergency_patient(make_patient, clinic):
    return make_patient(clinic)


@pytest.fixture()
def emergency_patient_user(make_user, clinic):
    return make_user(
        clinic,
        role=Role.PATIENT,
        email="emergency.patient@test.com",
    )


@pytest.fixture()
def emergency_patient_account(
    make_patient,
    emergency_patient_user,
    clinic,
):
    return make_patient(
        clinic,
        user_id=emergency_patient_user.id,
    )


@pytest.fixture()
def emergency_other_clinic(make_clinic):
    return make_clinic(
        name="Emergency Access Other Clinic",
    )


@pytest.fixture()
def emergency_other_staff(
    make_emergency_staff,
    emergency_other_clinic,
):
    return make_emergency_staff(
        emergency_other_clinic,
        role=Role.DOCTOR,
    )


@pytest.fixture()
def emergency_other_patient(
    make_patient,
    emergency_other_clinic,
):
    return make_patient(
        emergency_other_clinic,
    )


@pytest.fixture()
def make_emergency_grant(db_session):
    from app.core.emergency_access.models.emergency_access_model import (
        EmergencyAccessGrant,
    )

    def _make(
        clinic,
        patient,
        requester_user,
        requester_role=None,
        reason="Emergency treatment required.",
        purpose="Emergency clinical care.",
        scope=None,
        status=EmergencyAccessStatus.REQUESTED,
        requested_at=None,
        granted_at=None,
        expires_at=None,
        revoked_at=None,
        reviewed_at=None,
        reviewed_by_user_id=None,
        review_notes=None,
        **overrides,
    ):
        now = datetime.now(timezone.utc)

        grant = EmergencyAccessGrant(
            clinic_id=clinic.id,
            patient_id=patient.id,
            requester_user_id=requester_user.id,
            requester_role=(
                requester_role
                if requester_role is not None
                else (
                    requester_user.role.value
                    if hasattr(requester_user.role, "value")
                    else str(requester_user.role)
                )
            ),
            reason=reason,
            purpose=purpose,
            scope=(
                ["patient:read"]
                if scope is None
                else scope
            ),
            status=status,
            requested_at=(
                now
                if requested_at is None
                else requested_at
            ),
            granted_at=granted_at,
            expires_at=expires_at,
            revoked_at=revoked_at,
            reviewed_at=reviewed_at,
            reviewed_by_user_id=reviewed_by_user_id,
            review_notes=review_notes,
            **overrides,
        )

        db_session.add(grant)
        db_session.flush()

        return grant

    return _make


@pytest.fixture()
def emergency_requested_grant(
    make_emergency_grant,
    clinic,
    emergency_patient,
    emergency_staff,
):
    return make_emergency_grant(
        clinic=clinic,
        patient=emergency_patient,
        requester_user=emergency_staff.user,
        requester_role=Role.DOCTOR.value,
    )


@pytest.fixture()
def emergency_active_grant(
    make_emergency_grant,
    clinic,
    emergency_patient,
    emergency_staff,
    emergency_reviewer,
):
    now = datetime.now(timezone.utc)

    return make_emergency_grant(
        clinic=clinic,
        patient=emergency_patient,
        requester_user=emergency_staff.user,
        requester_role=Role.DOCTOR.value,
        status=EmergencyAccessStatus.ACTIVE,
        granted_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(minutes=30),
        reviewed_at=now - timedelta(minutes=5),
        reviewed_by_user_id=emergency_reviewer.id,
        review_notes="Emergency access approved.",
    )


@pytest.fixture()
def emergency_expired_grant(
    make_emergency_grant,
    clinic,
    emergency_patient,
    emergency_staff,
    emergency_reviewer,
):
    now = datetime.now(timezone.utc)

    return make_emergency_grant(
        clinic=clinic,
        patient=emergency_patient,
        requester_user=emergency_staff.user,
        requester_role=Role.DOCTOR.value,
        status=EmergencyAccessStatus.ACTIVE,
        granted_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
        reviewed_at=now - timedelta(hours=2),
        reviewed_by_user_id=emergency_reviewer.id,
        review_notes="Emergency access approved.",
    )


@pytest.fixture()
def make_consent_evaluation(db_session):
    from app.core.emergency_access.models.consent_guard_model import (
        ConsentGuardEvaluation,
    )

    def _make(
        clinic,
        patient,
        requester_user,
        recipient_role=Role.DOCTOR.value,
        purpose="Emergency clinical care.",
        decision=ConsentGuardDecision.DENY,
        consent_reference=None,
        policy_context=None,
        emergency_exception=False,
        effective_from=None,
        effective_until=None,
        emergency_access_id=None,
        **overrides,
    ):
        evaluation = ConsentGuardEvaluation(
            emergency_access_id=emergency_access_id,
            clinic_id=clinic.id,
            patient_id=patient.id,
            requester_user_id=requester_user.id,
            recipient_role=recipient_role,
            purpose=purpose,
            decision=decision,
            consent_reference=consent_reference,
            policy_context=policy_context,
            emergency_exception=emergency_exception,
            effective_from=effective_from,
            effective_until=effective_until,
            **overrides,
        )

        db_session.add(evaluation)
        db_session.flush()

        return evaluation

    return _make


@pytest.fixture()
def emergency_audit_mock(monkeypatch):
    import app.core.emergency_access.services.emergency_access_service as emergency_access_service

    audit = Mock()

    monkeypatch.setattr(
        emergency_access_service,
        "create_audit_log",
        audit,
    )

    return audit