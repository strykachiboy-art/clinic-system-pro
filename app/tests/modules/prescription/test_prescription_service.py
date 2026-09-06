from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums.prescription_enums import DrugInteractionSeverity, PrescriptionStatus
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.prescription.services import prescription_service as svc


class TestDrugInteractions:
    def test_create_drug_interaction_happy_path(self, db, make_drug):
        a = make_drug(None)
        b = make_drug(None)

        interaction = svc.create_drug_interaction(
            drug_a_id=a.id, drug_b_id=b.id, severity=DrugInteractionSeverity.SEVERE
        )
        assert interaction.id is not None

    def test_create_drug_interaction_rejects_self(self, db, make_drug):
        a = make_drug(None)
        with pytest.raises(ValidationError):
            svc.create_drug_interaction(
                drug_a_id=a.id, drug_b_id=a.id, severity=DrugInteractionSeverity.MILD
            )

    def test_create_drug_interaction_rejects_clinic_specific_drug(self, db, clinic, make_drug):
        a = make_drug(clinic)  # clinic-specific, not global
        b = make_drug(None)

        with pytest.raises(ValidationError):
            svc.create_drug_interaction(
                drug_a_id=a.id, drug_b_id=b.id, severity=DrugInteractionSeverity.MILD
            )

    def test_create_drug_interaction_rejects_duplicate_either_order(self, db, make_drug):
        a = make_drug(None)
        b = make_drug(None)
        svc.create_drug_interaction(drug_a_id=a.id, drug_b_id=b.id, severity=DrugInteractionSeverity.MILD)

        with pytest.raises(ConflictError):
            svc.create_drug_interaction(drug_a_id=b.id, drug_b_id=a.id, severity=DrugInteractionSeverity.SEVERE)

    def test_check_interactions_finds_known_pair(self, db, make_drug):
        a = make_drug(None)
        b = make_drug(None)
        c = make_drug(None)
        svc.create_drug_interaction(drug_a_id=a.id, drug_b_id=b.id, severity=DrugInteractionSeverity.MODERATE)

        results = svc.check_interactions([a.id, b.id, c.id])
        assert len(results) == 1
        assert results[0]["severity"] == "moderate"

    def test_check_interactions_returns_empty_for_single_drug(self, db, make_drug):
        a = make_drug(None)
        assert svc.check_interactions([a.id]) == []


class TestPrescriptionCreation:
    def _doctor(self, clinic, make_staff):
        return make_staff(clinic, role=Role.DOCTOR)

    def test_create_prescription_happy_path(self, db, clinic, make_patient, make_drug, make_staff):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        prescription, warnings = svc.create_prescription(
            clinic_id=clinic.id,
            patient_id=patient.id,
            prescribed_by_id=doctor.id,
            items=[{"drug_id": drug.id, "quantity": 10}],
        )

        assert prescription.status == PrescriptionStatus.ACTIVE
        assert len(prescription.items) == 1
        assert warnings == []

    def test_create_prescription_reports_interaction_warnings(self, db, clinic, make_patient, make_staff, make_drug):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)
        drug_a = make_drug(None)
        drug_b = make_drug(None)
        svc.create_drug_interaction(drug_a_id=drug_a.id, drug_b_id=drug_b.id, severity=DrugInteractionSeverity.SEVERE)

        prescription, warnings = svc.create_prescription(
            clinic_id=clinic.id,
            patient_id=patient.id,
            prescribed_by_id=doctor.id,
            items=[{"drug_id": drug_a.id}, {"drug_id": drug_b.id}],
        )

        assert len(warnings) == 1
        assert warnings[0]["severity"] == "severe"

    def test_create_prescription_requires_active_clinic(self, db, suspended_clinic, make_patient, make_staff, make_drug):
        with pytest.raises(Exception):
            svc.create_prescription(
                clinic_id=suspended_clinic.id,
                patient_id=1,
                prescribed_by_id=1,
                items=[{"drug_id": 1}],
            )

    def test_create_prescription_rejects_patient_from_other_clinic(
        self, db, clinic, make_clinic, make_patient, make_staff, make_drug
    ):
        doctor = self._doctor(clinic, make_staff)
        other_clinic = make_clinic(name="Other")
        patient = make_patient(other_clinic)
        drug = make_drug(clinic)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[{"drug_id": drug.id}],
            )

    def test_create_prescription_rejects_non_doctor_prescriber(self, db, clinic, make_patient, make_staff, make_drug):
        nurse = make_staff(clinic, role=Role.NURSE)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=nurse.id,
                items=[{"drug_id": drug.id}],
            )

    def test_create_prescription_rejects_inactive_prescriber_status(self, db, clinic, make_patient, make_staff, make_drug):
        doctor = make_staff(clinic, role=Role.DOCTOR, status=StaffStatus.SUSPENDED)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[{"drug_id": drug.id}],
            )

    def test_create_prescription_rejects_consultation_from_other_patient(
        self, db, clinic, make_patient, make_staff, make_drug, make_consultation
    ):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)
        other_patient = make_patient(clinic)
        drug = make_drug(clinic)
        consultation = make_consultation(clinic, other_patient, doctor)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[{"drug_id": drug.id}],
                consultation_id=consultation.id,
            )

    def test_create_prescription_rejects_inactive_drug(self, db, clinic, make_patient, make_staff, make_drug):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)
        drug = make_drug(clinic, is_active=False)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[{"drug_id": drug.id}],
            )

    def test_create_prescription_rejects_duplicate_drug_in_items(self, db, clinic, make_patient, make_staff, make_drug):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[{"drug_id": drug.id}, {"drug_id": drug.id}],
            )

    def test_create_prescription_rejects_empty_items(self, db, clinic, make_patient, make_staff):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[],
            )

    def test_create_prescription_rejects_past_expiry(self, db, clinic, make_patient, make_staff, make_drug):
        doctor = self._doctor(clinic, make_staff)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        with pytest.raises(ValidationError):
            svc.create_prescription(
                clinic_id=clinic.id,
                patient_id=patient.id,
                prescribed_by_id=doctor.id,
                items=[{"drug_id": drug.id}],
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )


class TestPrescriptionLifecycle:
    def _prescription(self, clinic, make_patient, make_staff, make_drug):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)
        prescription, _ = svc.create_prescription(
            clinic_id=clinic.id,
            patient_id=patient.id,
            prescribed_by_id=doctor.id,
            items=[{"drug_id": drug.id}],
        )
        return prescription

    def test_cancel_prescription_happy_path(self, db, clinic, make_patient, make_staff, make_drug):
        prescription = self._prescription(clinic, make_patient, make_staff, make_drug)
        cancelled = svc.cancel_prescription(prescription.id, reason="Adverse reaction")

        assert cancelled.status == PrescriptionStatus.CANCELLED
        assert "Adverse reaction" in cancelled.notes

    def test_cancel_prescription_rejects_non_active(self, db, clinic, make_patient, make_staff, make_drug):
        prescription = self._prescription(clinic, make_patient, make_staff, make_drug)
        svc.cancel_prescription(prescription.id)

        with pytest.raises(ConflictError):
            svc.cancel_prescription(prescription.id)

    def test_complete_prescription_happy_path(self, db, clinic, make_patient, make_staff, make_drug):
        prescription = self._prescription(clinic, make_patient, make_staff, make_drug)
        completed = svc.complete_prescription(prescription.id)
        assert completed.status == PrescriptionStatus.COMPLETED

    def test_get_prescription_not_found(self, db):
        with pytest.raises(NotFoundError):
            svc.get_prescription(999999)

    def test_list_prescriptions_for_patient_active_only(self, db, clinic, make_patient, make_staff, make_drug):
        doctor = make_staff(clinic, role=Role.DOCTOR)
        patient = make_patient(clinic)
        drug = make_drug(clinic)

        p1, _ = svc.create_prescription(
            clinic_id=clinic.id, patient_id=patient.id, prescribed_by_id=doctor.id,
            items=[{"drug_id": drug.id}],
        )
        p2, _ = svc.create_prescription(
            clinic_id=clinic.id, patient_id=patient.id, prescribed_by_id=doctor.id,
            items=[{"drug_id": drug.id}],
        )
        svc.cancel_prescription(p2.id)

        active = svc.list_prescriptions_for_patient(patient.id, active_only=True)
        assert {p.id for p in active} == {p1.id}

        all_rx = svc.list_prescriptions_for_patient(patient.id, active_only=False)
        assert {p.id for p in all_rx} == {p1.id, p2.id}

    def test_expire_stale_prescriptions(self, db, clinic, make_patient, make_staff, make_drug):
        prescription = self._prescription(clinic, make_patient, make_staff, make_drug)
        # Force it into an already-expired state directly (create_prescription
        # itself rejects a past expires_at, so this simulates time passing).
        prescription.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.session.commit()

        count = svc.expire_stale_prescriptions()

        assert count == 1
        assert svc.get_prescription(prescription.id).status == PrescriptionStatus.EXPIRED