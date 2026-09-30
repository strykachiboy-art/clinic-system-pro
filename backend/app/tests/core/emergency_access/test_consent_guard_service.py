from __future__ import annotations

import pytest

from app.core.enums.emergency_access_enums import (
    ConsentGuardDecision,
)
from app.core.enums.role_enums import Role
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
)

from app.core.emergency_access.services import (
    consent_guard_service,
)


class TestEvaluateConsentGuard:
    def test_patient_can_access_own_record(
        self,
        clinic,
        emergency_patient_account,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=(
                    emergency_patient_account.user_id
                ),
                patient_id=emergency_patient_account.id,
                clinic_id=clinic.id,
                recipient_role=Role.PATIENT.value,
                purpose=(
                    "View personal medical information."
                ),
                emergency_exception=False,
            )
        )

        assert result.id is not None
        assert (
            result.decision
            == ConsentGuardDecision.ALLOW
        )
        assert (
            result.emergency_access_id
            is None
        )
        assert result.emergency_exception is False

    def test_consent_reference_allows_access(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                consent_reference="CONSENT-001",
            )
        )

        assert (
            result.decision
            == ConsentGuardDecision.ALLOW
        )
        assert (
            result.consent_reference
            == "CONSENT-001"
        )
        assert result.emergency_exception is False

    def test_denies_access_without_consent(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
            )
        )

        assert (
            result.decision
            == ConsentGuardDecision.DENY
        )
        assert result.emergency_access_id is None
        assert result.emergency_exception is False

    def test_emergency_exception_allows_active_grant(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        emergency_active_grant,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose=(
                    "Immediate emergency treatment."
                ),
                emergency_exception=True,
            )
        )

        assert (
            result.decision
            == ConsentGuardDecision.EMERGENCY_EXCEPTION
        )
        assert (
            result.emergency_access_id
            == emergency_active_grant.id
        )
        assert result.emergency_exception is True
        assert (
            result.effective_from
            == emergency_active_grant.granted_at
        )
        assert (
            result.effective_until
            == emergency_active_grant.expires_at
        )

    def test_emergency_exception_without_active_grant_is_denied(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose=(
                    "Immediate emergency treatment."
                ),
                emergency_exception=True,
            )
        )

        assert (
            result.decision
            == ConsentGuardDecision.DENY
        )
        assert result.emergency_access_id is None
        assert result.emergency_exception is False

    def test_expired_grant_cannot_create_exception(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        emergency_expired_grant,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose=(
                    "Immediate emergency treatment."
                ),
                emergency_exception=True,
            )
        )

        assert (
            result.decision
            == ConsentGuardDecision.DENY
        )
        assert result.emergency_access_id is None
        assert result.emergency_exception is False

    def test_foreign_patient_is_hidden(
        self,
        clinic,
        emergency_other_patient,
        emergency_staff,
    ):
        with pytest.raises(
            NotFoundError,
            match=(
                f"Patient {emergency_other_patient.id} not found"
            ),
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_other_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
            )

    def test_stores_policy_context(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
    ):
        policy_context = {
            "policy_version": "v1",
            "source": "clinic-policy",
            "department": "emergency",
        }

        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                policy_context=policy_context,
            )
        )

        assert result.policy_context == policy_context

    def test_strips_optional_consent_reference(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                consent_reference="  CONSENT-002  ",
            )
        )

        assert result.consent_reference == "CONSENT-002"

    def test_blank_optional_consent_reference_becomes_none(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
    ):
        result = (
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                consent_reference="   ",
            )
        )

        assert result.consent_reference is None
        assert (
            result.decision
            == ConsentGuardDecision.DENY
        )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("actor_id", 0),
            ("patient_id", 0),
            ("clinic_id", 0),
        ],
    )
    def test_rejects_invalid_ids(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        field,
        value,
    ):
        kwargs = {
            "actor_id": emergency_staff.user.id,
            "patient_id": emergency_patient.id,
            "clinic_id": clinic.id,
            "recipient_role": Role.DOCTOR.value,
            "purpose": "Review patient record.",
            "emergency_exception": False,
        }

        kwargs[field] = value

        with pytest.raises(
            ValidationError,
        ):
            consent_guard_service.evaluate_consent_guard(
                **kwargs
            )

    @pytest.mark.parametrize(
        "recipient_role",
        [
            "",
            "   ",
            None,
            "not-a-role",
        ],
    )
    def test_rejects_invalid_recipient_role(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        recipient_role,
    ):
        with pytest.raises(
            ValidationError,
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=recipient_role,
                purpose="Review patient record.",
                emergency_exception=False,
            )

    @pytest.mark.parametrize(
        "purpose",
        [
            "",
            "   ",
            None,
            123,
            "x" * 256,
        ],
    )
    def test_rejects_invalid_purpose(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        purpose,
    ):
        with pytest.raises(
            ValidationError,
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose=purpose,
                emergency_exception=False,
            )

    @pytest.mark.parametrize(
        "emergency_exception",
        [
            None,
            0,
            1,
            "true",
            "false",
        ],
    )
    def test_rejects_non_boolean_emergency_exception(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        emergency_exception,
    ):
        with pytest.raises(
            ValidationError,
            match="Emergency exception must be a boolean",
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Emergency care.",
                emergency_exception=emergency_exception,
            )

    @pytest.mark.parametrize(
        "policy_context",
        [
            [],
            "invalid",
            123,
            True,
        ],
    )
    def test_rejects_non_object_policy_context(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        policy_context,
    ):
        with pytest.raises(
            ValidationError,
            match="Policy context must be an object",
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Emergency care.",
                emergency_exception=False,
                policy_context=policy_context,
            )


class TestConsentGuardSecurity:
    def test_unknown_actor_must_not_be_allowed_by_consent_reference(
        self,
        clinic,
        emergency_patient,
    ):
        with pytest.raises(
            NotFoundError,
            match="User 999999 not found",
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=999999,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                consent_reference="CONSENT-999",
            )

    def test_foreign_actor_must_not_be_allowed_by_consent_reference(
        self,
        clinic,
        emergency_patient,
        emergency_other_staff,
    ):
        with pytest.raises(
            NotFoundError,
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_other_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                consent_reference="CONSENT-FOREIGN",
            )

    def test_inactive_actor_must_not_be_allowed(
        self,
        clinic,
        emergency_patient,
        emergency_staff,
        db_session,
    ):
        emergency_staff.user.is_active = False
        db_session.flush()

        with pytest.raises(
            ValidationError,
            match="inactive",
        ):
            consent_guard_service.evaluate_consent_guard(
                actor_id=emergency_staff.user.id,
                patient_id=emergency_patient.id,
                clinic_id=clinic.id,
                recipient_role=Role.DOCTOR.value,
                purpose="Review patient record.",
                emergency_exception=False,
                consent_reference="CONSENT-INACTIVE",
            )