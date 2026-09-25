import pytest

from app.core.clinical_safety.models.clinical_rule_model import ClinicalRule

from app.core.exceptions import NotFoundError, ValidationError
from app.core.enums.clinical_safety_enums import (
    ClinicalRuleAction,
    ClinicalRuleScope,
    ClinicalRuleSeverity,
    ClinicalRuleType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.feedback_enums import FeedbackStatus, FeedbackSource, FeedbackType, FeedbackCategory
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.ward.models.ward_model import Admission, Bed, Ward
from app.modules.feedback.services import feedback_service
from app.modules.feedback.schemas.feedback_schema import FeedbackCreateSchema


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (StaffStatus.ACTIVE, True),
        (StaffStatus.ON_LEAVE, False),
        (StaffStatus.SUSPENDED, False),
        (StaffStatus.TERMINATED, False),
    ],
)
def test_is_active_staff_requires_active_staff_status(
    clinic,
    make_staff,
    status,
    expected,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=status,
    )

    result = feedback_service._is_active_staff(
        user_id=staff.user_id,
        clinic_id=clinic.id,
    )

    assert result is expected


@pytest.mark.parametrize(
    "status",
    [
        StaffStatus.ON_LEAVE,
        StaffStatus.SUSPENDED,
        StaffStatus.TERMINATED,
    ],
)
def test_validate_assignment_rejects_non_active_staff(
    clinic,
    make_staff,
    status,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=status,
    )

    with pytest.raises(
        ValidationError,
        match="Assigned user must be active clinic staff",
    ):
        feedback_service._validate_assignment(
            clinic_id=clinic.id,
            assigned_to_user_id=staff.user_id,
        )


def test_validate_assignment_rejects_active_non_staff_user(
    clinic,
    make_user,
):
    user = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    with pytest.raises(
        ValidationError,
        match="Assigned user must be active clinic staff",
    ):
        feedback_service._validate_assignment(
            clinic_id=clinic.id,
            assigned_to_user_id=user.id,
        )


def test_validate_assignment_rejects_user_from_another_clinic(
    clinic,
    make_clinic,
    make_staff,
):
    other_clinic = make_clinic()

    staff = make_staff(
        other_clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    with pytest.raises(NotFoundError):
        feedback_service._validate_assignment(
            clinic_id=clinic.id,
            assigned_to_user_id=staff.user_id,
        )


def test_validate_assignment_allows_active_clinic_staff(
    clinic,
    make_staff,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    result = feedback_service._validate_assignment(
        clinic_id=clinic.id,
        assigned_to_user_id=staff.user_id,
    )

    assert result is None


def test_patient_can_target_own_patient_record(
    clinic,
    make_user,
    make_patient,
):
    patient_user = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    patient = make_patient(
        clinic,
        user_id=patient_user.id,
    )

    result = feedback_service._validate_target(
        actor_user_id=patient_user.id,
        clinic_id=clinic.id,
        target_module="patient",
        target_resource_type="patient",
        target_resource_id=patient.id,
    )

    assert result is None


def test_patient_cannot_target_another_patient_record(
    clinic,
    make_user,
    make_patient,
):
    patient_user_a = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )
    patient_user_b = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    make_patient(
        clinic,
        user_id=patient_user_a.id,
    )

    patient_b = make_patient(
        clinic,
        user_id=patient_user_b.id,
    )

    with pytest.raises(NotFoundError):
        feedback_service._validate_target(
            actor_user_id=patient_user_a.id,
            clinic_id=clinic.id,
            target_module="patient",
            target_resource_type="patient",
            target_resource_id=patient_b.id,
        )


def test_active_staff_can_target_clinic_patient(
    clinic,
    make_staff,
    make_patient,
):
    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    patient = make_patient(
        clinic,
    )

    result = feedback_service._validate_target(
        actor_user_id=staff.user_id,
        clinic_id=clinic.id,
        target_module="patient",
        target_resource_type="patient",
        target_resource_id=patient.id,
    )

    assert result is None


def test_admin_can_target_clinic_patient(
    clinic,
    feedback_admin,
    make_patient,
):
    patient = make_patient(
        clinic,
    )

    result = feedback_service._validate_target(
        actor_user_id=feedback_admin.id,
        clinic_id=clinic.id,
        target_module="patient",
        target_resource_type="patient",
        target_resource_id=patient.id,
    )

    assert result is None


def test_cross_clinic_target_is_rejected(
    clinic,
    make_clinic,
    feedback_admin,
    make_patient,
):
    other_clinic = make_clinic()

    patient = make_patient(
        other_clinic,
    )

    with pytest.raises(NotFoundError):
        feedback_service._validate_target(
            actor_user_id=feedback_admin.id,
            clinic_id=clinic.id,
            target_module="patient",
            target_resource_type="patient",
            target_resource_id=patient.id,
        )


def test_patient_can_target_own_appointment(
    clinic,
    make_user,
    make_patient,
    make_staff,
    make_appointment,
):
    patient_user = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    patient = make_patient(
        clinic,
        user_id=patient_user.id,
    )

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    appointment = make_appointment(
        clinic=clinic,
        patient=patient,
        staff=staff,
    )

    result = feedback_service._validate_target(
        actor_user_id=patient_user.id,
        clinic_id=clinic.id,
        target_module="appointment",
        target_resource_type="appointment",
        target_resource_id=appointment.id,
    )

    assert result is None


def test_patient_cannot_target_another_patient_appointment(
    clinic,
    make_user,
    make_patient,
    make_staff,
    make_appointment,
):
    patient_user_a = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )
    patient_user_b = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    patient_a = make_patient(
        clinic,
        user_id=patient_user_a.id,
    )

    patient_b = make_patient(
        clinic,
        user_id=patient_user_b.id,
    )

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    appointment_b = make_appointment(
        clinic=clinic,
        patient=patient_b,
        staff=staff,
    )

    with pytest.raises(NotFoundError):
        feedback_service._validate_target(
            actor_user_id=patient_user_a.id,
            clinic_id=clinic.id,
            target_module="appointment",
            target_resource_type="appointment",
            target_resource_id=appointment_b.id,
        )


def test_patient_can_target_own_consultation(
    db,
    clinic,
    make_user,
    make_patient,
    make_staff,
):
    patient_user = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    patient = make_patient(
        clinic,
        user_id=patient_user.id,
    )

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    consultation = Consultation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
    )

    db.session.add(consultation)
    db.session.flush()

    result = feedback_service._validate_target(
        actor_user_id=patient_user.id,
        clinic_id=clinic.id,
        target_module="consultation",
        target_resource_type="consultation",
        target_resource_id=consultation.id,
    )

    assert result is None


def test_patient_cannot_target_another_patient_consultation(
    db,
    clinic,
    make_user,
    make_patient,
    make_staff,
):
    patient_user_a = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )
    patient_user_b = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    make_patient(
        clinic,
        user_id=patient_user_a.id,
    )

    patient_b = make_patient(
        clinic,
        user_id=patient_user_b.id,
    )

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    consultation_b = Consultation(
        clinic_id=clinic.id,
        patient_id=patient_b.id,
        staff_id=staff.id,
    )

    db.session.add(consultation_b)
    db.session.flush()

    with pytest.raises(NotFoundError):
        feedback_service._validate_target(
            actor_user_id=patient_user_a.id,
            clinic_id=clinic.id,
            target_module="consultation",
            target_resource_type="consultation",
            target_resource_id=consultation_b.id,
        )

@pytest.mark.parametrize(
    "feedback_fixture",
    [
        "feedback_resolved",
        "feedback_rejected",
    ],
)
def test_reopen_feedback_clears_resolution_state(
    request,
    feedback_admin,
    feedback_fixture,
):
    feedback = request.getfixturevalue(feedback_fixture)

    result = feedback_service.reopen_feedback(
        actor_user_id=feedback_admin.id,
        feedback_id=feedback.id,
        clinic_id=feedback.clinic_id,
    )

    assert result.status == FeedbackStatus.REOPENED
    assert result.resolution_note is None
    assert result.resolved_at is None
    assert result.closed_at is None

def _make_global_clinical_rule(db):
    rule = ClinicalRule(
        clinic_id=None,
        rule_code="FEEDBACK_GLOBAL_RULE",
        name="Feedback Global Rule",
        scope=ClinicalRuleScope.GLOBAL,
        rule_type=ClinicalRuleType.DRUG_INTERACTION,
        severity=ClinicalRuleSeverity.HIGH,
        action=ClinicalRuleAction.ALERT,
        conditions={},
        configuration={},
        version=1,
    )

    db.session.add(rule)
    db.session.flush()

    return rule


def _make_admission_target(
    db,
    clinic,
    patient,
    staff,
):
    ward = Ward(
        clinic_id=clinic.id,
        name="Feedback Test Ward",
    )

    db.session.add(ward)
    db.session.flush()

    bed = Bed(
        ward_id=ward.id,
        bed_number="FB-01",
    )

    db.session.add(bed)
    db.session.flush()

    admission = Admission(
        patient_id=patient.id,
        bed_id=bed.id,
        admitted_by_id=staff.id,
    )

    db.session.add(admission)
    db.session.flush()

    return admission


def test_patient_cannot_target_global_clinical_rule(
    db,
    clinic,
    feedback_submitter,
):
    rule = _make_global_clinical_rule(db)

    with pytest.raises(NotFoundError):
        feedback_service._validate_target(
            actor_user_id=feedback_submitter.id,
            clinic_id=clinic.id,
            target_module="clinical_safety",
            target_resource_type="clinical_rule",
            target_resource_id=rule.id,
        )


def test_active_staff_can_target_global_clinical_rule(
    db,
    clinic,
    feedback_staff,
):
    rule = _make_global_clinical_rule(db)

    result = feedback_service._validate_target(
        actor_user_id=feedback_staff.user_id,
        clinic_id=clinic.id,
        target_module="clinical_safety",
        target_resource_type="clinical_rule",
        target_resource_id=rule.id,
    )

    assert result is None


def test_patient_can_target_own_admission(
    db,
    clinic,
    make_user,
    make_patient,
    make_staff,
):
    patient_user = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    patient = make_patient(
        clinic,
        user_id=patient_user.id,
    )

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    admission = _make_admission_target(
        db,
        clinic,
        patient,
        staff,
    )

    result = feedback_service._validate_target(
        actor_user_id=patient_user.id,
        clinic_id=clinic.id,
        target_module="ward",
        target_resource_type="admission",
        target_resource_id=admission.id,
    )

    assert result is None


def test_patient_cannot_target_another_patient_admission(
    db,
    clinic,
    make_user,
    make_patient,
    make_staff,
):
    patient_user_a = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    patient_user_b = make_user(
        clinic,
        role=Role.PATIENT,
        is_active=True,
    )

    make_patient(
        clinic,
        user_id=patient_user_a.id,
    )

    patient_b = make_patient(
        clinic,
        user_id=patient_user_b.id,
    )

    staff = make_staff(
        clinic,
        role=Role.DOCTOR,
        status=StaffStatus.ACTIVE,
    )

    admission_b = _make_admission_target(
        db,
        clinic,
        patient_b,
        staff,
    )

    with pytest.raises(NotFoundError):
        feedback_service._validate_target(
            actor_user_id=patient_user_a.id,
            clinic_id=clinic.id,
            target_module="ward",
            target_resource_type="admission",
            target_resource_id=admission_b.id,
        )

def _make_source_test_payload():
    return FeedbackCreateSchema(
        feedback_type=FeedbackType.BUG_REPORT,
        category=FeedbackCategory.USABILITY,
        subject="System source boundary test",
        message="Verify system source is restricted.",
    )


def test_create_feedback_rejects_system_source(
    feedback_submitter,
):
    payload = _make_source_test_payload()

    with pytest.raises(
        ValidationError,
        match="System feedback must use create_system_feedback",
    ):
        feedback_service.create_feedback(
            actor_user_id=feedback_submitter.id,
            payload=payload,
            clinic_id=feedback_submitter.clinic_id,
            source=FeedbackSource.SYSTEM,
        )


def test_create_system_feedback_uses_system_source(
    feedback_submitter,
):
    payload = _make_source_test_payload()

    feedback = feedback_service.create_system_feedback(
        actor_user_id=feedback_submitter.id,
        payload=payload,
        clinic_id=feedback_submitter.clinic_id,
    )

    assert feedback.source == FeedbackSource.SYSTEM

