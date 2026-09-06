from datetime import date, timedelta

import pytest

from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.patient.services import patient_service as svc


class TestPatientCreation:
    def test_create_patient_happy_path(self, db, clinic):
        patient = svc.create_patient(
            clinic.id,
            {"first_name": "Jane", "last_name": "Doe"},
        )
        assert patient.patient_number is not None
        assert patient.is_active is True

    def test_create_patient_requires_active_clinic(self, db, suspended_clinic):
        with pytest.raises(Exception):
            svc.create_patient(
                suspended_clinic.id,
                {"first_name": "A", "last_name": "B"},
            )

    def test_create_patient_rejects_blank_first_name(self, db, clinic):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {"first_name": "  ", "last_name": "B"},
            )

    def test_create_patient_rejects_unknown_field(self, db, clinic):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {
                    "first_name": "A",
                    "last_name": "B",
                    "made_up": 1,
                },
            )

    def test_create_patient_rejects_future_dob(self, db, clinic):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {
                    "first_name": "A",
                    "last_name": "B",
                    "date_of_birth": date.today() + timedelta(days=1),
                },
            )

    def test_create_patient_generates_unique_numbers(self, db, clinic):
        p1 = svc.create_patient(
            clinic.id,
            {"first_name": "A", "last_name": "B"},
        )
        p2 = svc.create_patient(
            clinic.id,
            {"first_name": "C", "last_name": "D"},
        )

        assert p1.patient_number != p2.patient_number


class TestPatientRetrievalAndUpdate:
    def test_get_patient_not_found(self, db):
        with pytest.raises(NotFoundError):
            svc.get_patient(999999)

    def test_get_patient_works_for_suspended_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
    ):
        p = make_patient(suspended_clinic)

        assert svc.get_patient(p.id).id == p.id

    def test_list_patients_filters_by_clinic_active_and_search(
        self,
        db,
        clinic,
        make_clinic,
    ):
        other = make_clinic(name="Other")

        svc.create_patient(
            clinic.id,
            {"first_name": "Alice", "last_name": "Zephyr"},
        )
        svc.create_patient(
            other.id,
            {"first_name": "Bob", "last_name": "Young"},
        )

        by_clinic = svc.list_patients(clinic_id=clinic.id)
        assert {p.first_name for p in by_clinic} == {"Alice"}

        by_search = svc.list_patients(search="alice")
        assert {p.first_name for p in by_search} == {"Alice"}

    def test_update_patient_rejects_unknown_field(self, db, patient):
        with pytest.raises(ValidationError):
            svc.update_patient(
                patient.id,
                {"bogus": 1},
            )

    def test_update_patient_rejects_blank_name(self, db, patient):
        with pytest.raises(ValidationError):
            svc.update_patient(
                patient.id,
                {"first_name": "   "},
            )

    def test_update_patient_happy_path(self, db, patient):
        updated = svc.update_patient(
            patient.id,
            {"first_name": "  Renamed  "},
        )

        assert updated.first_name == "Renamed"

    def test_set_active_status_noop_when_same(self, db, patient):
        result = svc.set_active_status(patient.id, True)

        assert result.is_active is True

    def test_set_active_status_toggles(self, db, patient):
        result = svc.set_active_status(patient.id, False)

        assert result.is_active is False


class TestFamilyMembers:
    def test_add_family_member_happy_path(self, db, patient):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "John Doe",
                "relation": "spouse",
            },
        )

        assert member.full_name == "John Doe"

    def test_add_family_member_rejects_blank_name(self, db, patient):
        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "  ",
                    "relation": "spouse",
                },
            )

    def test_add_family_member_rejects_self_relation(self, db, patient):
        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "X",
                    "relation": "spouse",
                    "related_patient_id": patient.id,
                },
            )

    def test_add_family_member_rejects_related_patient_other_clinic(
        self,
        db,
        clinic,
        make_clinic,
        patient,
        make_patient,
    ):
        other_clinic = make_clinic(name="Other")
        other_patient = make_patient(other_clinic)

        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "X",
                    "relation": "spouse",
                    "related_patient_id": other_patient.id,
                },
            )

    def test_update_family_member_happy_path(self, db, patient):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "Old",
                "relation": "child",
            },
        )

        updated = svc.update_family_member(
            patient.id,
            member.id,
            {"full_name": "New"},
        )

        assert updated.full_name == "New"

    def test_update_family_member_not_found(self, db, patient):
        with pytest.raises(NotFoundError):
            svc.update_family_member(
                patient.id,
                999999,
                {"full_name": "X"},
            )

    def test_remove_family_member_happy_path(self, db, patient):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "X",
                "relation": "child",
            },
        )

        svc.remove_family_member(patient.id, member.id)

        with pytest.raises(NotFoundError):
            svc.remove_family_member(patient.id, member.id)

    def test_list_family_members_ordering_emergency_first(
        self,
        db,
        patient,
    ):
        svc.add_family_member(
            patient.id,
            {
                "full_name": "Zed",
                "relation": "child",
            },
        )

        svc.add_family_member(
            patient.id,
            {
                "full_name": "Alice",
                "relation": "spouse",
                "is_emergency_contact": True,
            },
        )

        members = svc.list_family_members(patient.id)

        assert members[0].full_name == "Alice"


class TestInsurance:
    def test_add_insurance_happy_path(self, db, patient):
        insurance = svc.add_insurance(
            patient.id,
            {
                "provider_name": "Acme",
                "policy_number": "P1",
            },
        )

        assert insurance.is_primary is False

    def test_add_insurance_rejects_missing_policy_number(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.add_insurance(
                patient.id,
                {
                    "provider_name": "Acme",
                    "policy_number": "",
                },
            )

    def test_add_insurance_rejects_coverage_end_before_start(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.add_insurance(
                patient.id,
                {
                    "provider_name": "Acme",
                    "policy_number": "P1",
                    "coverage_start": date(2026, 6, 1),
                    "coverage_end": date(2026, 1, 1),
                },
            )

    def test_add_insurance_only_one_primary_at_a_time(
        self,
        db,
        patient,
    ):
        first = svc.add_insurance(
            patient.id,
            {
                "provider_name": "A",
                "policy_number": "P1",
                "is_primary": True,
            },
        )

        second = svc.add_insurance(
            patient.id,
            {
                "provider_name": "B",
                "policy_number": "P2",
                "is_primary": True,
            },
        )

        assert svc.list_insurances(patient.id)[0].id == second.id

        refreshed_first = [
            i
            for i in svc.list_insurances(patient.id)
            if i.id == first.id
        ][0]

        assert refreshed_first.is_primary is False

    def test_update_insurance_rejects_blank_provider_name(
        self,
        db,
        patient,
    ):
        insurance = svc.add_insurance(
            patient.id,
            {
                "provider_name": "A",
                "policy_number": "P1",
            },
        )

        with pytest.raises(ValidationError):
            svc.update_insurance(
                patient.id,
                insurance.id,
                {"provider_name": "   "},
            )


class TestVitals:
    def test_record_vitals_happy_path(self, db, patient):
        vitals = svc.record_vitals(
            patient.id,
            {
                "heart_rate": 72,
                "temperature": 37,
            },
        )

        assert vitals.heart_rate_bpm == 72
        assert vitals.temperature_c == 37

    def test_record_vitals_rejects_empty_data(self, db, patient):
        with pytest.raises(ValidationError):
            svc.record_vitals(patient.id, {})

    def test_record_vitals_rejects_all_none_values(self, db, patient):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {"heart_rate": None},
            )

    def test_record_vitals_rejects_unknown_field(self, db, patient):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {"made_up_vital": 1},
            )

    def test_record_vitals_validates_recording_staff(
        self,
        db,
        clinic,
        patient,
        make_staff,
    ):
        inactive_staff = make_staff(
            clinic,
            status=StaffStatus.SUSPENDED,
        )

        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {"heart_rate": 80},
                recorded_by_id=inactive_staff.id,
            )

    def test_get_latest_vitals_returns_most_recent(
        self,
        db,
        patient,
    ):
        svc.record_vitals(
            patient.id,
            {"heart_rate": 60},
        )

        latest = svc.record_vitals(
            patient.id,
            {"heart_rate": 90},
        )

        assert svc.get_latest_vitals(patient.id).id == latest.id

    def test_get_latest_vitals_none_when_no_records(
        self,
        db,
        patient,
    ):
        assert svc.get_latest_vitals(patient.id) is None

    def test_get_vitals_history_returns_all(
        self,
        db,
        patient,
    ):
        svc.record_vitals(
            patient.id,
            {"heart_rate": 60},
        )

        svc.record_vitals(
            patient.id,
            {"heart_rate": 90},
        )

        assert len(svc.get_vitals_history(patient.id)) == 2