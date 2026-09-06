from datetime import date, timedelta

import pytest

from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.patient.services import patient_service as svc


class TestPatientCreation:
    def test_create_patient_happy_path(self, db, clinic):
        patient = svc.create_patient(
            clinic.id,
            {
                "first_name": "Jane",
                "last_name": "Doe",
            },
        )

        assert patient.patient_number is not None
        assert patient.is_active is True

    def test_create_patient_requires_active_clinic(
        self,
        db,
        suspended_clinic,
    ):
        with pytest.raises(ValidationError):
            svc.create_patient(
                suspended_clinic.id,
                {
                    "first_name": "A",
                    "last_name": "B",
                },
            )

    def test_create_patient_rejects_blank_first_name(
        self,
        db,
        clinic,
    ):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {
                    "first_name": "  ",
                    "last_name": "B",
                },
            )

    def test_create_patient_rejects_blank_last_name(
        self,
        db,
        clinic,
    ):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {
                    "first_name": "A",
                    "last_name": "   ",
                },
            )

    def test_create_patient_rejects_unknown_field(
        self,
        db,
        clinic,
    ):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {
                    "first_name": "A",
                    "last_name": "B",
                    "made_up": 1,
                },
            )

    def test_create_patient_rejects_future_dob(
        self,
        db,
        clinic,
    ):
        with pytest.raises(ValidationError):
            svc.create_patient(
                clinic.id,
                {
                    "first_name": "A",
                    "last_name": "B",
                    "date_of_birth": date.today() + timedelta(days=1),
                },
            )

    def test_create_patient_accepts_today_as_dob(
        self,
        db,
        clinic,
    ):
        patient = svc.create_patient(
            clinic.id,
            {
                "first_name": "A",
                "last_name": "B",
                "date_of_birth": date.today(),
            },
        )

        assert patient.date_of_birth == date.today()

    def test_create_patient_trims_names(
        self,
        db,
        clinic,
    ):
        patient = svc.create_patient(
            clinic.id,
            {
                "first_name": "  Jane  ",
                "last_name": "  Doe  ",
            },
        )

        assert patient.first_name == "Jane"
        assert patient.last_name == "Doe"

    def test_create_patient_generates_unique_numbers(
        self,
        db,
        clinic,
    ):
        p1 = svc.create_patient(
            clinic.id,
            {
                "first_name": "A",
                "last_name": "B",
            },
        )

        p2 = svc.create_patient(
            clinic.id,
            {
                "first_name": "C",
                "last_name": "D",
            },
        )

        assert p1.patient_number is not None
        assert p2.patient_number is not None
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
        patient = make_patient(suspended_clinic)

        assert svc.get_patient(patient.id).id == patient.id

    def test_list_patients_filters_by_clinic_active_and_search(
        self,
        db,
        clinic,
        make_clinic,
    ):
        other = make_clinic(name="Other")

        svc.create_patient(
            clinic.id,
            {
                "first_name": "Alice",
                "last_name": "Zephyr",
            },
        )

        svc.create_patient(
            other.id,
            {
                "first_name": "Bob",
                "last_name": "Young",
            },
        )

        by_clinic = svc.list_patients(
            clinic_id=clinic.id,
        )

        assert {p.first_name for p in by_clinic} == {"Alice"}

        by_search = svc.list_patients(
            search="alice",
        )

        assert {p.first_name for p in by_search} == {"Alice"}

    def test_list_patients_active_only_excludes_inactive(
        self,
        db,
        clinic,
    ):
        active = svc.create_patient(
            clinic.id,
            {
                "first_name": "Active",
                "last_name": "Patient",
            },
        )

        inactive = svc.create_patient(
            clinic.id,
            {
                "first_name": "Inactive",
                "last_name": "Patient",
            },
        )

        svc.set_active_status(
            inactive.id,
            False,
        )

        patients = svc.list_patients(
            clinic_id=clinic.id,
            active_only=True,
        )

        assert active.id in {p.id for p in patients}
        assert inactive.id not in {p.id for p in patients}

    def test_list_patients_can_include_inactive(
        self,
        db,
        clinic,
    ):
        patient = svc.create_patient(
            clinic.id,
            {
                "first_name": "Inactive",
                "last_name": "Patient",
            },
        )

        svc.set_active_status(
            patient.id,
            False,
        )

        patients = svc.list_patients(
            clinic_id=clinic.id,
            active_only=False,
        )

        assert patient.id in {p.id for p in patients}

    def test_update_patient_rejects_unknown_field(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.update_patient(
                patient.id,
                {
                    "bogus": 1,
                },
            )

    def test_update_patient_rejects_blank_name(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.update_patient(
                patient.id,
                {
                    "first_name": "   ",
                },
            )

    def test_update_patient_rejects_future_dob(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.update_patient(
                patient.id,
                {
                    "date_of_birth": date.today() + timedelta(days=1),
                },
            )

    def test_update_patient_happy_path(
        self,
        db,
        patient,
    ):
        updated = svc.update_patient(
            patient.id,
            {
                "first_name": "  Renamed  ",
            },
        )

        assert updated.first_name == "Renamed"

    def test_update_patient_updates_multiple_fields(
        self,
        db,
        patient,
    ):
        updated = svc.update_patient(
            patient.id,
            {
                "first_name": "Jane",
                "last_name": "Updated",
                "phone": "08012345678",
            },
        )

        assert updated.first_name == "Jane"
        assert updated.last_name == "Updated"
        assert updated.phone == "08012345678"

    def test_update_patient_not_found(
        self,
        db,
    ):
        with pytest.raises(NotFoundError):
            svc.update_patient(
                999999,
                {
                    "first_name": "Nobody",
                },
            )

    def test_update_patient_requires_active_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
    ):
        patient = make_patient(suspended_clinic)

        with pytest.raises(ValidationError):
            svc.update_patient(
                patient.id,
                {
                    "first_name": "Changed",
                },
            )

    def test_set_active_status_noop_when_same(
        self,
        db,
        patient,
    ):
        result = svc.set_active_status(
            patient.id,
            True,
        )

        assert result.is_active is True

    def test_set_active_status_toggles(
        self,
        db,
        patient,
    ):
        result = svc.set_active_status(
            patient.id,
            False,
        )

        assert result.is_active is False

    def test_set_active_status_can_reactivate(
        self,
        db,
        patient,
    ):
        svc.set_active_status(
            patient.id,
            False,
        )

        result = svc.set_active_status(
            patient.id,
            True,
        )

        assert result.is_active is True

    def test_set_active_status_not_found(
        self,
        db,
    ):
        with pytest.raises(NotFoundError):
            svc.set_active_status(
                999999,
                False,
            )

    def test_set_active_status_requires_active_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
    ):
        patient = make_patient(suspended_clinic)

        with pytest.raises(ValidationError):
            svc.set_active_status(
                patient.id,
                False,
            )


class TestFamilyMembers:
    def test_add_family_member_happy_path(
        self,
        db,
        patient,
    ):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "John Doe",
                "relation": "spouse",
            },
        )

        assert member.full_name == "John Doe"

    def test_add_family_member_rejects_blank_name(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "  ",
                    "relation": "spouse",
                },
            )

    def test_add_family_member_rejects_unknown_field(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "John",
                    "relation": "spouse",
                    "made_up": True,
                },
            )

    def test_add_family_member_rejects_self_relation(
        self,
        db,
        patient,
    ):
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
        other_clinic = make_clinic(
            name="Other",
        )

        other_patient = make_patient(
            other_clinic,
        )

        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "X",
                    "relation": "spouse",
                    "related_patient_id": other_patient.id,
                },
            )

    def test_add_family_member_patient_not_found(
        self,
        db,
    ):
        with pytest.raises(NotFoundError):
            svc.add_family_member(
                999999,
                {
                    "full_name": "X",
                    "relation": "spouse",
                },
            )

    def test_add_family_member_requires_active_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
    ):
        patient = make_patient(
            suspended_clinic,
        )

        with pytest.raises(ValidationError):
            svc.add_family_member(
                patient.id,
                {
                    "full_name": "X",
                    "relation": "spouse",
                },
            )

    def test_update_family_member_happy_path(
        self,
        db,
        patient,
    ):
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
            {
                "full_name": "New",
            },
        )

        assert updated.full_name == "New"

    def test_update_family_member_rejects_unknown_field(
        self,
        db,
        patient,
    ):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "Old",
                "relation": "child",
            },
        )

        with pytest.raises(ValidationError):
            svc.update_family_member(
                patient.id,
                member.id,
                {
                    "bogus": 1,
                },
            )

    def test_update_family_member_rejects_blank_name(
        self,
        db,
        patient,
    ):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "Old",
                "relation": "child",
            },
        )

        with pytest.raises(ValidationError):
            svc.update_family_member(
                patient.id,
                member.id,
                {
                    "full_name": "   ",
                },
            )

    def test_update_family_member_not_found(
        self,
        db,
        patient,
    ):
        with pytest.raises(NotFoundError):
            svc.update_family_member(
                patient.id,
                999999,
                {
                    "full_name": "X",
                },
            )

    def test_update_family_member_cannot_use_member_from_other_patient(
        self,
        db,
        patient,
        make_patient,
    ):
        other_patient = make_patient(
            patient.clinic_id,
        )

        member = svc.add_family_member(
            other_patient.id,
            {
                "full_name": "Other Member",
                "relation": "child",
            },
        )

        with pytest.raises(NotFoundError):
            svc.update_family_member(
                patient.id,
                member.id,
                {
                    "full_name": "Hijacked",
                },
            )

    def test_remove_family_member_happy_path(
        self,
        db,
        patient,
    ):
        member = svc.add_family_member(
            patient.id,
            {
                "full_name": "X",
                "relation": "child",
            },
        )

        svc.remove_family_member(
            patient.id,
            member.id,
        )

        with pytest.raises(NotFoundError):
            svc.remove_family_member(
                patient.id,
                member.id,
            )

    def test_remove_family_member_cannot_remove_other_patients_member(
        self,
        db,
        patient,
        make_patient,
    ):
        other_patient = make_patient(
            patient.clinic_id,
        )

        member = svc.add_family_member(
            other_patient.id,
            {
                "full_name": "Other Member",
                "relation": "child",
            },
        )

        with pytest.raises(NotFoundError):
            svc.remove_family_member(
                patient.id,
                member.id,
            )

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

        members = svc.list_family_members(
            patient.id,
        )

        assert members[0].full_name == "Alice"

    def test_list_family_members_empty(
        self,
        db,
        patient,
    ):
        assert svc.list_family_members(patient.id) == []


class TestInsurance:
    def test_add_insurance_happy_path(
        self,
        db,
        patient,
    ):
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

    def test_add_insurance_rejects_blank_provider_name(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.add_insurance(
                patient.id,
                {
                    "provider_name": "   ",
                    "policy_number": "P1",
                },
            )

    def test_add_insurance_rejects_unknown_field(
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
                    "bogus": 1,
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

        insurances = svc.list_insurances(
            patient.id,
        )

        assert any(
            insurance.id == second.id
            and insurance.is_primary
            for insurance in insurances
        )

        refreshed_first = next(
            insurance
            for insurance in insurances
            if insurance.id == first.id
        )

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
                {
                    "provider_name": "   ",
                },
            )

    def test_update_insurance_rejects_unknown_field(
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
                {
                    "bogus": 1,
                },
            )

    def test_update_insurance_cannot_update_other_patients_insurance(
        self,
        db,
        patient,
        make_patient,
    ):
        other_patient = make_patient(
            patient.clinic_id,
        )

        insurance = svc.add_insurance(
            other_patient.id,
            {
                "provider_name": "Other",
                "policy_number": "OTHER-1",
            },
        )

        with pytest.raises(NotFoundError):
            svc.update_insurance(
                patient.id,
                insurance.id,
                {
                    "provider_name": "Hijacked",
                },
            )

    def test_add_insurance_requires_active_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
    ):
        patient = make_patient(
            suspended_clinic,
        )

        with pytest.raises(ValidationError):
            svc.add_insurance(
                patient.id,
                {
                    "provider_name": "Acme",
                    "policy_number": "P1",
                },
            )


class TestVitals:
    def test_record_vitals_happy_path(
        self,
        db,
        patient,
    ):
        vitals = svc.record_vitals(
            patient.id,
            {
                "heart_rate": 72,
                "temperature": 37,
            },
        )

        assert vitals.heart_rate_bpm == 72
        assert vitals.temperature_c == 37
        assert vitals.recorded_at is not None

    def test_record_vitals_maps_api_heart_rate_to_bpm(
        self,
        db,
        patient,
    ):
        vitals = svc.record_vitals(
            patient.id,
            {
                "heart_rate": 88,
            },
        )

        assert vitals.heart_rate_bpm == 88

    def test_record_vitals_maps_all_measurements(
        self,
        db,
        patient,
    ):
        vitals = svc.record_vitals(
            patient.id,
            {
                "temperature": 37.2,
                "blood_pressure_systolic": 120,
                "blood_pressure_diastolic": 80,
                "heart_rate": 72,
                "respiratory_rate": 16,
                "oxygen_saturation": 98,
                "weight": 70,
                "height": 175,
            },
        )

        assert vitals.temperature_c == 37.2
        assert vitals.blood_pressure_systolic == 120
        assert vitals.blood_pressure_diastolic == 80
        assert vitals.heart_rate_bpm == 72
        assert vitals.respiratory_rate == 16
        assert vitals.oxygen_saturation == 98
        assert vitals.weight_kg == 70
        assert vitals.height_cm == 175

    def test_record_vitals_rejects_empty_data(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {},
            )

    def test_record_vitals_rejects_all_none_values(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "heart_rate": None,
                },
            )

    def test_record_vitals_rejects_unknown_field(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "made_up_vital": 1,
                },
            )

    def test_record_vitals_rejects_client_recorded_at(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "heart_rate": 72,
                    "recorded_at": date(2020, 1, 1),
                },
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
                {
                    "heart_rate": 80,
                },
                recorded_by_id=inactive_staff.id,
            )

    def test_record_vitals_rejects_staff_from_other_clinic(
        self,
        db,
        clinic,
        patient,
        make_clinic,
        make_staff,
    ):
        other_clinic = make_clinic(
            name="Other Clinic",
        )

        other_staff = make_staff(
            other_clinic,
            status=StaffStatus.ACTIVE,
        )

        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                recorded_by_id=other_staff.id,
            )

    def test_record_vitals_rejects_nonexistent_staff(
        self,
        db,
        patient,
    ):
        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                recorded_by_id=999999,
            )

    def test_record_vitals_rejects_inactive_linked_user(
        self,
        db,
        clinic,
        patient,
        make_staff,
    ):
        staff = make_staff(
            clinic,
            status=StaffStatus.ACTIVE,
        )

        if staff.user is None:
            pytest.skip(
                "Fixture does not create a linked user for staff"
            )

        staff.user.is_active = False
        db.session.flush()

        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                recorded_by_id=staff.id,
            )

    def test_record_vitals_requires_active_clinic(
        self,
        db,
        suspended_clinic,
        make_patient,
    ):
        patient = make_patient(
            suspended_clinic,
        )

        with pytest.raises(ValidationError):
            svc.record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
            )

    def test_record_vitals_patient_not_found(
        self,
        db,
    ):
        with pytest.raises(NotFoundError):
            svc.record_vitals(
                999999,
                {
                    "heart_rate": 80,
                },
            )

    def test_get_latest_vitals_returns_most_recent(
        self,
        db,
        patient,
    ):
        svc.record_vitals(
            patient.id,
            {
                "heart_rate": 60,
            },
        )

        latest = svc.record_vitals(
            patient.id,
            {
                "heart_rate": 90,
            },
        )

        assert svc.get_latest_vitals(
            patient.id,
        ).id == latest.id

    def test_get_latest_vitals_none_when_no_records(
        self,
        db,
        patient,
    ):
        assert svc.get_latest_vitals(
            patient.id,
        ) is None

    def test_get_vitals_history_returns_all(
        self,
        db,
        patient,
    ):
        svc.record_vitals(
            patient.id,
            {
                "heart_rate": 60,
            },
        )

        svc.record_vitals(
            patient.id,
            {
                "heart_rate": 90,
            },
        )

        assert len(
            svc.get_vitals_history(patient.id)
        ) == 2