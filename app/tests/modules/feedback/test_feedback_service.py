import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.feedback.services import feedback_service


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