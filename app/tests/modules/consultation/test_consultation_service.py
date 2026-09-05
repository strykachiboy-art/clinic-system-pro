from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums.appointment_enums import AppointmentStatus
from app.core.enums.clinic_enums import ClinicStatus
from app.core.enums.consultation_enums import (
    ConsultationStatus,
    ConsultationType,
)
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.consultation.models.consultation_model import (
    Consultation,
    ConsultationTemplate,
)
from app.modules.consultation.services import consultation_service


# ============================================================================
# HELPERS
# ============================================================================


def make_appointment(
    db,
    clinic,
    patient,
    staff,
    *,
    status=AppointmentStatus.SCHEDULED,
    scheduled_start=None,
    scheduled_end=None,
    **overrides,
):
    """Create a real Appointment row for consultation tests."""

    if scheduled_start is None:
        scheduled_start = datetime.now(timezone.utc) + timedelta(hours=1)

    if scheduled_end is None:
        scheduled_end = scheduled_start + timedelta(hours=1)

    appointment = Appointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        status=status,
        **overrides,
    )

    db.session.add(appointment)
    db.session.commit()

    return appointment


def make_consultation(
    db,
    clinic,
    patient,
    staff,
    *,
    status=ConsultationStatus.IN_PROGRESS,
    consultation_type=ConsultationType.GENERAL,
    appointment_id=None,
    template_id=None,
    started_at=None,
    ended_at=None,
    **overrides,
):
    """Create a raw Consultation row for state/history tests."""

    consultation = Consultation(
        clinic_id=clinic.id,
        patient_id=patient.id,
        staff_id=staff.id,
        appointment_id=appointment_id,
        template_id=template_id,
        consultation_type=consultation_type,
        status=status,
        started_at=started_at or datetime.now(timezone.utc),
        ended_at=ended_at,
        **overrides,
    )

    db.session.add(consultation)
    db.session.commit()

    return consultation


def make_template(
    db,
    *,
    clinic_id=None,
    name="General Consultation",
    specialty="General Medicine",
    structure=None,
    is_active=True,
):
    """Create a real ConsultationTemplate row."""

    template = ConsultationTemplate(
        clinic_id=clinic_id,
        name=name,
        specialty=specialty,
        structure=structure
        or {
            "sections": [
                "chief_complaint",
                "symptoms",
                "diagnosis",
                "treatment_plan",
            ]
        },
        is_active=is_active,
    )

    db.session.add(template)
    db.session.commit()

    return template


@pytest.fixture()
def audit_log_spy(monkeypatch):
    """
    Prevent consultation tests from depending on the audit implementation
    while still allowing us to verify that the service records audits.
    """

    calls = []

    def _fake_create_audit_log(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        consultation_service,
        "create_audit_log",
        _fake_create_audit_log,
    )

    return calls


# ============================================================================
# GET CONSULTATION
# ============================================================================


class TestGetConsultation:

    def test_returns_existing_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.get_consultation(
            consultation.id
        )

        assert result.id == consultation.id
        assert result.clinic_id == clinic.id
        assert result.patient_id == patient.id
        assert result.staff_id == staff.id

    def test_raises_not_found_for_missing_consultation(self):
        with pytest.raises(
            NotFoundError,
            match=r"Consultation 999999 not found",
        ):
            consultation_service.get_consultation(999999)

    def test_historical_consultation_is_accessible_when_clinic_is_suspended(
        self,
        db,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        consultation = make_consultation(
            db,
            suspended_clinic,
            patient,
            staff,
        )

        result = consultation_service.get_consultation(
            consultation.id
        )

        assert result.id == consultation.id


# ============================================================================
# GET CONSULTATION TEMPLATE
# ============================================================================


class TestGetConsultationTemplate:

    def test_returns_existing_template(self, db):
        template = make_template(db)

        result = consultation_service.get_consultation_template(
            template.id
        )

        assert result.id == template.id
        assert result.name == template.name

    def test_returns_inactive_template(self, db):
        template = make_template(
            db,
            is_active=False,
        )

        result = consultation_service.get_consultation_template(
            template.id
        )

        assert result.id == template.id
        assert result.is_active is False

    def test_raises_not_found_for_missing_template(self):
        with pytest.raises(
            NotFoundError,
            match=r"Consultation template 999999 not found",
        ):
            consultation_service.get_consultation_template(999999)


# ============================================================================
# START CONSULTATION
# ============================================================================


class TestStartConsultation:

    def test_starts_general_consultation_successfully(
        self,
        db,
        clinic,
        patient,
        staff,
        audit_log_spy,
    ):
        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
        )

        assert result.id is not None
        assert result.clinic_id == clinic.id
        assert result.patient_id == patient.id
        assert result.staff_id == staff.id
        assert result.appointment_id is None
        assert result.template_id is None
        assert result.consultation_type == ConsultationType.GENERAL
        assert result.status == ConsultationStatus.IN_PROGRESS
        assert result.started_at is not None
        assert result.ended_at is None

        assert len(audit_log_spy) == 1
        assert audit_log_spy[0]["action"].value == "create"
        assert audit_log_spy[0]["entity_type"] == "Consultation"
        assert audit_log_spy[0]["entity_id"] == result.id

    @pytest.mark.parametrize(
        "consultation_type",
        [
            ConsultationType.GENERAL,
            ConsultationType.FOLLOW_UP,
            ConsultationType.SPECIALIST,
            ConsultationType.EMERGENCY,
        ],
    )
    def test_supports_all_consultation_types(
        self,
        db,
        clinic,
        patient,
        staff,
        consultation_type,
    ):
        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            consultation_type=consultation_type,
        )

        assert result.consultation_type == consultation_type
        assert result.status == ConsultationStatus.IN_PROGRESS

    def test_preserves_chief_complaint_and_symptoms(
        self,
        clinic,
        patient,
        staff,
    ):
        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            chief_complaint="Persistent headache",
            symptoms="Headache and dizziness",
        )

        assert result.chief_complaint == "Persistent headache"
        assert result.symptoms == "Headache and dizziness"

    def test_rejects_suspended_clinic(
        self,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        with pytest.raises(
            ValidationError,
            match=rf"Clinic {suspended_clinic.id} is not active",
        ):
            consultation_service.start_consultation(
                clinic_id=suspended_clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
            )

    def test_rejects_patient_from_different_clinic(
        self,
        clinic,
        make_clinic,
        make_patient,
        staff,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_patient = make_patient(other_clinic)

        with pytest.raises(
            ConflictError,
            match=rf"Patient {other_patient.id} does not belong "
            rf"to clinic {clinic.id}",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=other_patient.id,
                staff_id=staff.id,
            )

    def test_rejects_staff_from_different_clinic(
        self,
        clinic,
        make_clinic,
        make_staff,
        patient,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_staff = make_staff(other_clinic)

        with pytest.raises(
            ConflictError,
            match=rf"Staff {other_staff.id} does not belong "
            rf"to clinic {clinic.id}",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=other_staff.id,
            )

    def test_rejects_missing_patient(self, clinic, staff):
        with pytest.raises(
            NotFoundError,
            match=r"Patient 999999 not found",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=999999,
                staff_id=staff.id,
            )

    def test_rejects_missing_staff(self, clinic, patient):
        with pytest.raises(
            NotFoundError,
            match=r"Staff 999999 not found",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=999999,
            )

    # ------------------------------------------------------------------------
    # Appointment validation
    # ------------------------------------------------------------------------

    def test_starts_consultation_with_scheduled_appointment(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        appointment = make_appointment(
            db,
            clinic,
            patient,
            staff,
            status=AppointmentStatus.SCHEDULED,
        )

        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            appointment_id=appointment.id,
        )

        assert result.appointment_id == appointment.id

    def test_starts_consultation_with_confirmed_appointment(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        appointment = make_appointment(
            db,
            clinic,
            patient,
            staff,
            status=AppointmentStatus.CONFIRMED,
        )

        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            appointment_id=appointment.id,
        )

        assert result.appointment_id == appointment.id

    def test_rejects_missing_appointment(self, clinic, patient, staff):
        with pytest.raises(
            NotFoundError,
            match=r"Appointment 999999 not found",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                appointment_id=999999,
            )

    def test_rejects_appointment_from_different_clinic(
        self,
        db,
        clinic,
        patient,
        staff,
        make_clinic,
        make_patient,
        make_staff,
    ):
        other_clinic = make_clinic(name="Other Clinic")
        other_patient = make_patient(other_clinic)
        other_staff = make_staff(other_clinic)

        appointment = make_appointment(
            db,
            other_clinic,
            other_patient,
            other_staff,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Appointment {appointment.id} does not belong "
            rf"to clinic {clinic.id}",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                appointment_id=appointment.id,
            )

    def test_rejects_appointment_for_different_patient(
        self,
        db,
        clinic,
        patient,
        staff,
        make_patient,
    ):
        other_patient = make_patient(clinic)

        appointment = make_appointment(
            db,
            clinic,
            other_patient,
            staff,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Appointment {appointment.id} does not belong "
            rf"to patient {patient.id}",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                appointment_id=appointment.id,
            )

    def test_rejects_appointment_for_different_staff(
        self,
        db,
        clinic,
        patient,
        staff,
        make_staff,
    ):
        other_staff = make_staff(clinic)

        appointment = make_appointment(
            db,
            clinic,
            patient,
            other_staff,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Appointment {appointment.id} does not belong "
            rf"to staff member {staff.id}",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                appointment_id=appointment.id,
            )

    def test_rejects_appointment_with_invalid_status(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        invalid_status = next(
            status
            for status in AppointmentStatus
            if status
            not in (
                AppointmentStatus.SCHEDULED,
                AppointmentStatus.CONFIRMED,
            )
        )

        appointment = make_appointment(
            db,
            clinic,
            patient,
            staff,
            status=invalid_status,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Appointment {appointment.id} is currently "
            rf"'{invalid_status.value}' and cannot start "
            rf"a consultation",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                appointment_id=appointment.id,
            )

    # ------------------------------------------------------------------------
    # Template validation
    # ------------------------------------------------------------------------

    def test_starts_with_active_global_template(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        template = make_template(
            db,
            clinic_id=None,
            name="Global Template",
        )

        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            template_id=template.id,
        )

        assert result.template_id == template.id

    def test_starts_with_active_clinic_template(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        template = make_template(
            db,
            clinic_id=clinic.id,
            name="Clinic Template",
        )

        result = consultation_service.start_consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            template_id=template.id,
        )

        assert result.template_id == template.id

    def test_rejects_missing_template(
        self,
        clinic,
        patient,
        staff,
    ):
        with pytest.raises(
            NotFoundError,
            match=r"Consultation template 999999 not found",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                template_id=999999,
            )

    def test_rejects_inactive_template(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        template = make_template(
            db,
            clinic_id=clinic.id,
            name="Inactive Template",
            is_active=False,
        )

        with pytest.raises(
            ValidationError,
            match=rf"Consultation template {template.id} is not active",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                template_id=template.id,
            )

    def test_rejects_template_from_different_clinic(
        self,
        db,
        clinic,
        patient,
        staff,
        make_clinic,
    ):
        other_clinic = make_clinic(name="Other Clinic")

        template = make_template(
            db,
            clinic_id=other_clinic.id,
            name="Other Clinic Template",
        )

        with pytest.raises(
            ConflictError,
            match=rf"Consultation template {template.id} does not belong "
            rf"to clinic {clinic.id}",
        ):
            consultation_service.start_consultation(
                clinic_id=clinic.id,
                patient_id=patient.id,
                staff_id=staff.id,
                template_id=template.id,
            )


# ============================================================================
# UPDATE CONSULTATION NOTE
# ============================================================================


class TestUpdateConsultationNote:

    def test_updates_all_supported_fields(
        self,
        db,
        clinic,
        patient,
        staff,
        audit_log_spy,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.update_consultation_note(
            consultation.id,
            icd10_code="R51.9",
            chief_complaint="Headache",
            symptoms="Headache and dizziness",
            diagnosis="Tension headache",
            treatment_plan="Rest and hydration",
            notes="Follow up in one week",
            voice_note_url="https://example.com/voice.mp3",
            transcribed_text="Patient reports headache",
        )

        assert result.icd10_code == "R51.9"
        assert result.chief_complaint == "Headache"
        assert result.symptoms == "Headache and dizziness"
        assert result.diagnosis == "Tension headache"
        assert result.treatment_plan == "Rest and hydration"
        assert result.notes == "Follow up in one week"
        assert result.voice_note_url == "https://example.com/voice.mp3"
        assert result.transcribed_text == "Patient reports headache"

        assert len(audit_log_spy) == 1
        assert audit_log_spy[0]["action"].value == "update"
        assert audit_log_spy[0]["entity_type"] == "Consultation"

    def test_ignores_none_values(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            diagnosis="Existing diagnosis",
            notes="Existing notes",
        )

        result = consultation_service.update_consultation_note(
            consultation.id,
            diagnosis=None,
            notes=None,
        )

        assert result.diagnosis == "Existing diagnosis"
        assert result.notes == "Existing notes"

    def test_returns_without_audit_when_nothing_changes(
        self,
        db,
        clinic,
        patient,
        staff,
        audit_log_spy,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            diagnosis="Existing diagnosis",
        )

        result = consultation_service.update_consultation_note(
            consultation.id,
            diagnosis="Existing diagnosis",
        )

        assert result.diagnosis == "Existing diagnosis"
        assert audit_log_spy == []

    def test_rejects_unknown_fields(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=r"Unknown consultation field\(s\): invalid_field",
        ):
            consultation_service.update_consultation_note(
                consultation.id,
                invalid_field="value",
            )

    def test_rejects_multiple_unknown_fields_in_sorted_order(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=r"Unknown consultation field\(s\): aaa, zzz",
        ):
            consultation_service.update_consultation_note(
                consultation.id,
                zzz="value",
                aaa="value",
            )

    def test_allows_editing_completed_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.COMPLETED,
            diagnosis="Original diagnosis",
        )

        result = consultation_service.update_consultation_note(
            consultation.id,
            notes="Documentation correction",
        )

        assert result.notes == "Documentation correction"

    def test_rejects_editing_cancelled_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.CANCELLED,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Consultation {consultation.id} is cancelled "
            rf"and cannot be updated",
        ):
            consultation_service.update_consultation_note(
                consultation.id,
                notes="Attempted update",
            )

    def test_rejects_update_when_clinic_is_suspended(
        self,
        db,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        consultation = make_consultation(
            db,
            suspended_clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=rf"Clinic {suspended_clinic.id} is not active",
        ):
            consultation_service.update_consultation_note(
                consultation.id,
                notes="New notes",
            )

    def test_rejects_missing_consultation(self):
        with pytest.raises(
            NotFoundError,
            match=r"Consultation 999999 not found",
        ):
            consultation_service.update_consultation_note(
                999999,
                notes="New notes",
            )


# ============================================================================
# COMPLETE CONSULTATION
# ============================================================================


class TestCompleteConsultation:

    def test_completes_in_progress_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
        audit_log_spy,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        before = datetime.now(timezone.utc)

        result = consultation_service.complete_consultation(
            consultation.id,
            diagnosis="Acute tension headache",
            treatment_plan="Rest, hydration and follow-up",
            notes="Patient stable",
        )

        after = datetime.now(timezone.utc)

        assert result.status == ConsultationStatus.COMPLETED
        assert result.diagnosis == "Acute tension headache"
        assert result.treatment_plan == "Rest, hydration and follow-up"
        assert result.notes == "Patient stable"
        assert result.ended_at is not None

        ended_at = result.ended_at
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=timezone.utc)

        assert before <= ended_at <= after

        assert len(audit_log_spy) == 1
        assert audit_log_spy[0]["action"].value == "status_change"
        assert audit_log_spy[0]["entity_type"] == "Consultation"

    def test_strips_diagnosis(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.complete_consultation(
            consultation.id,
            diagnosis="  Migraine  ",
        )

        assert result.diagnosis == "Migraine"
        assert result.status == ConsultationStatus.COMPLETED

    def test_treatment_plan_is_optional(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.complete_consultation(
            consultation.id,
            diagnosis="Migraine",
        )

        assert result.diagnosis == "Migraine"
        assert result.treatment_plan is None
        assert result.notes is None

    def test_rejects_blank_diagnosis(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=r"Diagnosis is required to complete a consultation",
        ):
            consultation_service.complete_consultation(
                consultation.id,
                diagnosis="   ",
            )

        db.session.refresh(consultation)

        assert consultation.status == ConsultationStatus.IN_PROGRESS
        assert consultation.ended_at is None

    def test_rejects_empty_diagnosis(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=r"Diagnosis is required to complete a consultation",
        ):
            consultation_service.complete_consultation(
                consultation.id,
                diagnosis="",
            )

    def test_rejects_already_completed_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.COMPLETED,
            diagnosis="Existing diagnosis",
        )

        with pytest.raises(
            ConflictError,
            match=rf"Consultation {consultation.id} is already completed",
        ):
            consultation_service.complete_consultation(
                consultation.id,
                diagnosis="Another diagnosis",
            )

    def test_rejects_cancelled_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.CANCELLED,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Consultation {consultation.id} is cancelled "
            rf"and cannot be completed",
        ):
            consultation_service.complete_consultation(
                consultation.id,
                diagnosis="Diagnosis",
            )

    def test_rejects_completion_when_clinic_is_suspended(
        self,
        db,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        consultation = make_consultation(
            db,
            suspended_clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=rf"Clinic {suspended_clinic.id} is not active",
        ):
            consultation_service.complete_consultation(
                consultation.id,
                diagnosis="Diagnosis",
            )


# ============================================================================
# CANCEL CONSULTATION
# ============================================================================


class TestCancelConsultation:

    def test_cancels_in_progress_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
        audit_log_spy,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        before = datetime.now(timezone.utc)

        result = consultation_service.cancel_consultation(
            consultation.id,
            reason="Patient requested cancellation",
        )

        after = datetime.now(timezone.utc)

        assert result.status == ConsultationStatus.CANCELLED
        assert result.ended_at is not None
        assert result.notes == (
            "[Cancelled: Patient requested cancellation]"
        )

        ended_at = result.ended_at
        if ended_at.tzinfo is None:
            ended_at = ended_at.replace(tzinfo=timezone.utc)

        assert before <= ended_at <= after

        assert len(audit_log_spy) == 1
        assert audit_log_spy[0]["action"].value == "status_change"
        assert audit_log_spy[0]["entity_type"] == "Consultation"
        assert audit_log_spy[0]["new_value"]["reason"] == (
            "Patient requested cancellation"
        )

    def test_cancels_without_reason(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.cancel_consultation(
            consultation.id,
        )

        assert result.status == ConsultationStatus.CANCELLED
        assert result.notes is None
        assert result.ended_at is not None

    def test_blank_reason_does_not_create_cancellation_note(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.cancel_consultation(
            consultation.id,
            reason="   ",
        )

        assert result.status == ConsultationStatus.CANCELLED
        assert result.notes is None

    def test_strips_cancellation_reason(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        result = consultation_service.cancel_consultation(
            consultation.id,
            reason="  Patient unavailable  ",
        )

        assert result.notes == "[Cancelled: Patient unavailable]"

    def test_preserves_existing_notes_when_cancelled(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            notes="Original consultation note",
        )

        result = consultation_service.cancel_consultation(
            consultation.id,
            reason="Patient left before completion",
        )

        assert result.notes == (
            "Original consultation note\n"
            "[Cancelled: Patient left before completion]"
        )

    def test_existing_whitespace_notes_are_stripped_before_append(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            notes="  Existing note  ",
        )

        result = consultation_service.cancel_consultation(
            consultation.id,
            reason="No longer required",
        )

        assert result.notes == (
            "Existing note\n"
            "[Cancelled: No longer required]"
        )

    def test_rejects_already_cancelled_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.CANCELLED,
        )

        with pytest.raises(
            ConflictError,
            match=rf"Consultation {consultation.id} is already cancelled",
        ):
            consultation_service.cancel_consultation(
                consultation.id,
                reason="Another reason",
            )

    def test_rejects_completed_consultation(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        consultation = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.COMPLETED,
            diagnosis="Completed diagnosis",
        )

        with pytest.raises(
            ConflictError,
            match=rf"Consultation {consultation.id} is already "
            rf"completed and cannot be cancelled",
        ):
            consultation_service.cancel_consultation(
                consultation.id,
                reason="Attempted cancellation",
            )

    def test_rejects_cancellation_when_clinic_is_suspended(
        self,
        db,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        consultation = make_consultation(
            db,
            suspended_clinic,
            patient,
            staff,
        )

        with pytest.raises(
            ValidationError,
            match=rf"Clinic {suspended_clinic.id} is not active",
        ):
            consultation_service.cancel_consultation(
                consultation.id,
                reason="Reason",
            )


# ============================================================================
# PATIENT CONSULTATION HISTORY
# ============================================================================


class TestGetConsultationsForPatient:

    def test_returns_patient_consultation_history_newest_first(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        oldest = make_consultation(
            db,
            clinic,
            patient,
            staff,
            started_at=datetime(
                2026,
                1,
                1,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        newest = make_consultation(
            db,
            clinic,
            patient,
            staff,
            started_at=datetime(
                2026,
                1,
                3,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        middle = make_consultation(
            db,
            clinic,
            patient,
            staff,
            started_at=datetime(
                2026,
                1,
                2,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        result = consultation_service.get_consultations_for_patient(
            patient.id
        )

        assert [item.id for item in result] == [
            newest.id,
            middle.id,
            oldest.id,
        ]

    def test_returns_only_requested_patient_consultations(
        self,
        db,
        clinic,
        patient,
        staff,
        make_patient,
    ):
        other_patient = make_patient(clinic)

        requested = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        make_consultation(
            db,
            clinic,
            other_patient,
            staff,
        )

        result = consultation_service.get_consultations_for_patient(
            patient.id
        )

        assert [item.id for item in result] == [requested.id]

    def test_history_is_available_for_suspended_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        consultation = make_consultation(
            db,
            suspended_clinic,
            patient,
            staff,
        )

        result = consultation_service.get_consultations_for_patient(
            patient.id
        )

        assert [item.id for item in result] == [consultation.id]

    def test_raises_not_found_for_missing_patient(self):
        with pytest.raises(
            NotFoundError,
            match=r"Patient 999999 not found",
        ):
            consultation_service.get_consultations_for_patient(
                999999
            )


# ============================================================================
# STAFF CONSULTATION HISTORY
# ============================================================================


class TestGetConsultationsForStaff:

    def test_returns_staff_consultation_history_newest_first(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        oldest = make_consultation(
            db,
            clinic,
            patient,
            staff,
            started_at=datetime(
                2026,
                1,
                1,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        newest = make_consultation(
            db,
            clinic,
            patient,
            staff,
            started_at=datetime(
                2026,
                1,
                3,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        middle = make_consultation(
            db,
            clinic,
            patient,
            staff,
            started_at=datetime(
                2026,
                1,
                2,
                10,
                0,
                tzinfo=timezone.utc,
            ),
        )

        result = consultation_service.get_consultations_for_staff(
            staff.id
        )

        assert [item.id for item in result] == [
            newest.id,
            middle.id,
            oldest.id,
        ]

    def test_returns_only_requested_staff_consultations(
        self,
        db,
        clinic,
        patient,
        staff,
        make_staff,
    ):
        other_staff = make_staff(clinic)

        requested = make_consultation(
            db,
            clinic,
            patient,
            staff,
        )

        make_consultation(
            db,
            clinic,
            patient,
            other_staff,
        )

        result = consultation_service.get_consultations_for_staff(
            staff.id
        )

        assert [item.id for item in result] == [requested.id]

    @pytest.mark.parametrize(
        "status",
        [
            ConsultationStatus.IN_PROGRESS,
            ConsultationStatus.COMPLETED,
            ConsultationStatus.CANCELLED,
        ],
    )
    def test_filters_by_status(
        self,
        db,
        clinic,
        patient,
        staff,
        status,
    ):
        matching = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=status,
        )

        other_status = next(
            value
            for value in ConsultationStatus
            if value != status
        )

        make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=other_status,
        )

        result = consultation_service.get_consultations_for_staff(
            staff.id,
            status=status,
        )

        assert [item.id for item in result] == [matching.id]
        assert all(item.status == status for item in result)

    def test_without_status_returns_all_statuses(
        self,
        db,
        clinic,
        patient,
        staff,
    ):
        in_progress = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.IN_PROGRESS,
        )

        completed = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.COMPLETED,
        )

        cancelled = make_consultation(
            db,
            clinic,
            patient,
            staff,
            status=ConsultationStatus.CANCELLED,
        )

        result = consultation_service.get_consultations_for_staff(
            staff.id
        )

        result_ids = {item.id for item in result}

        assert result_ids == {
            in_progress.id,
            completed.id,
            cancelled.id,
        }

    def test_history_is_available_for_suspended_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
        make_staff,
    ):
        patient = make_patient(suspended_clinic)
        staff = make_staff(suspended_clinic)

        consultation = make_consultation(
            db,
            suspended_clinic,
            patient,
            staff,
        )

        result = consultation_service.get_consultations_for_staff(
            staff.id
        )

        assert [item.id for item in result] == [consultation.id]

    def test_raises_not_found_for_missing_staff(self):
        with pytest.raises(
            NotFoundError,
            match=r"Staff 999999 not found",
        ):
            consultation_service.get_consultations_for_staff(
                999999
            )


# ============================================================================
# CREATE CONSULTATION TEMPLATE
# ============================================================================


class TestCreateConsultationTemplate:

    def test_creates_global_template(
        self,
        db,
        audit_log_spy,
    ):
        structure = {
            "sections": [
                "chief_complaint",
                "diagnosis",
            ]
        }

        result = consultation_service.create_consultation_template(
            name="General Template",
            structure=structure,
        )

        assert result.id is not None
        assert result.clinic_id is None
        assert result.name == "General Template"
        assert result.specialty is None
        assert result.structure == structure
        assert result.is_active is True

        assert len(audit_log_spy) == 1
        assert audit_log_spy[0]["action"].value == "create"
        assert audit_log_spy[0]["entity_type"] == "ConsultationTemplate"

    def test_creates_clinic_specific_template(
        self,
        clinic,
    ):
        result = consultation_service.create_consultation_template(
            name="Cardiology Template",
            structure={"sections": ["cardiac_history"]},
            clinic_id=clinic.id,
            specialty="Cardiology",
        )

        assert result.clinic_id == clinic.id
        assert result.name == "Cardiology Template"
        assert result.specialty == "Cardiology"

    def test_strips_template_name(
        self,
        clinic,
    ):
        result = consultation_service.create_consultation_template(
            name="  General Template  ",
            structure={"sections": []},
            clinic_id=clinic.id,
        )

        assert result.name == "General Template"

    def test_accepts_inactive_template(
        self,
        db,
    ):
        result = consultation_service.create_consultation_template(
            name="Inactive Template",
            structure={"sections": []},
            is_active=False,
        )

        assert result.is_active is False

        persisted = db.session.get(
            ConsultationTemplate,
            result.id,
        )

        assert persisted.is_active is False

    def test_rejects_missing_name(
        self,
        db,
    ):
        with pytest.raises(
            ValidationError,
            match=r"Template name is required",
        ):
            consultation_service.create_consultation_template(
                name="",
                structure={"sections": []},
            )

    def test_rejects_whitespace_name(
        self,
        db,
    ):
        with pytest.raises(
            ValidationError,
            match=r"Template name is required",
        ):
            consultation_service.create_consultation_template(
                name="   ",
                structure={"sections": []},
            )

    @pytest.mark.parametrize(
        "structure",
        [
            [],
            "not an object",
            123,
            None,
        ],
    )
    def test_rejects_non_dict_structure(
        self,
        structure,
    ):
        with pytest.raises(
            ValidationError,
            match=r"Template structure must be an object",
        ):
            consultation_service.create_consultation_template(
                name="Invalid Template",
                structure=structure,
            )

    def test_rejects_template_for_suspended_clinic(
        self,
        suspended_clinic,
    ):
        with pytest.raises(
            ValidationError,
            match=rf"Clinic {suspended_clinic.id} is not active",
        ):
            consultation_service.create_consultation_template(
                name="Suspended Clinic Template",
                structure={"sections": []},
                clinic_id=suspended_clinic.id,
            )


# ============================================================================
# GET ACTIVE TEMPLATES
# ============================================================================


class TestGetActiveTemplates:

    def test_returns_all_active_templates_when_no_clinic_is_supplied(
        self,
        db,
    ):
        active_a = make_template(
            db,
            name="Alpha Template",
            is_active=True,
        )

        inactive = make_template(
            db,
            name="Inactive Template",
            is_active=False,
        )

        active_b = make_template(
            db,
            name="Beta Template",
            is_active=True,
        )

        result = consultation_service.get_active_templates()

        result_ids = [template.id for template in result]

        assert active_a.id in result_ids
        assert active_b.id in result_ids
        assert inactive.id not in result_ids

    def test_returns_global_and_matching_clinic_templates(
        self,
        db,
        clinic,
        make_clinic,
    ):
        global_template = make_template(
            db,
            clinic_id=None,
            name="Global Template",
        )

        clinic_template = make_template(
            db,
            clinic_id=clinic.id,
            name="Clinic Template",
        )

        other_clinic = make_clinic(name="Other Clinic")

        other_template = make_template(
            db,
            clinic_id=other_clinic.id,
            name="Other Clinic Template",
        )

        result = consultation_service.get_active_templates(
            clinic_id=clinic.id
        )

        result_ids = {template.id for template in result}

        assert global_template.id in result_ids
        assert clinic_template.id in result_ids
        assert other_template.id not in result_ids

    def test_excludes_inactive_global_template(
        self,
        db,
        clinic,
    ):
        inactive_global = make_template(
            db,
            clinic_id=None,
            name="Inactive Global",
            is_active=False,
        )

        active_global = make_template(
            db,
            clinic_id=None,
            name="Active Global",
            is_active=True,
        )

        result = consultation_service.get_active_templates(
            clinic_id=clinic.id
        )

        result_ids = {template.id for template in result}

        assert active_global.id in result_ids
        assert inactive_global.id not in result_ids

    def test_excludes_inactive_clinic_template(
        self,
        db,
        clinic,
    ):
        inactive_clinic = make_template(
            db,
            clinic_id=clinic.id,
            name="Inactive Clinic Template",
            is_active=False,
        )

        active_clinic = make_template(
            db,
            clinic_id=clinic.id,
            name="Active Clinic Template",
            is_active=True,
        )

        result = consultation_service.get_active_templates(
            clinic_id=clinic.id
        )

        result_ids = {template.id for template in result}

        assert active_clinic.id in result_ids
        assert inactive_clinic.id not in result_ids

    def test_orders_templates_alphabetically(
        self,
        db,
    ):
        make_template(
            db,
            name="Zebra Template",
        )

        make_template(
            db,
            name="Alpha Template",
        )

        make_template(
            db,
            name="Middle Template",
        )

        result = consultation_service.get_active_templates()

        names = [template.name for template in result]

        assert names == sorted(names)

    def test_returns_all_active_templates_when_clinic_id_is_none(
        self,
        db,
        clinic,
        make_clinic,
    ):
        global_template = make_template(
            db,
            clinic_id=None,
            name="Global",
        )

        clinic_template = make_template(
            db,
            clinic_id=clinic.id,
            name="Clinic",
        )

        other_clinic = make_clinic(name="Other Clinic")

        other_template = make_template(
            db,
            clinic_id=other_clinic.id,
            name="Other",
        )

        result = consultation_service.get_active_templates(
            clinic_id=None
        )

        result_ids = {template.id for template in result}

        assert global_template.id in result_ids
        assert clinic_template.id in result_ids
        assert other_template.id in result_ids