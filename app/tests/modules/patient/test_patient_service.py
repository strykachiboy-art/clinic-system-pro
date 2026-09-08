import pytest
from datetime import date, timedelta, timezone
from decimal import Decimal

from app.core.enums.patient_enums import (
    BloodType,
    FamilyRelation,
    Gender,
)
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.audit_enums import AuditAction
from app.core.enums.clinic_enums import ClinicStatus
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

from app.modules.patient.models.patient_model import (
    Patient,
    PatientFamilyMember,
    PatientInsurance,
    PatientVitals,
)
from app.modules.staff.models.staff_model import Staff

from app.modules.patient.services.patient_service import (
    get_patient,
    list_patients,
    create_patient,
    update_patient,
    set_active_status,
    list_family_members,
    add_family_member,
    update_family_member,
    remove_family_member,
    list_insurances,
    add_insurance,
    update_insurance,
    get_vitals_history,
    get_latest_vitals,
    record_vitals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def patient_payload(**overrides):
    data = {
        "first_name": "John",
        "last_name": "Doe",
        "date_of_birth": date(1990, 5, 15),
        "gender": Gender.MALE,
        "blood_type": BloodType.O_POS,
        "phone": "08012345678",
        "email": "john@example.com",
        "address": "123 Main Street",
        "allergies": "Penicillin",
        "chronic_conditions": "Asthma",
        "emirates_id": None,
        "umrn": None,
    }
    data.update(overrides)
    return data


def family_payload(**overrides):
    data = {
        "full_name": "Jane Doe",
        "relation": FamilyRelation.SPOUSE,
        "phone": "08098765432",
        "is_emergency_contact": True,
        "related_patient_id": None,
    }
    data.update(overrides)
    return data


def insurance_payload(**overrides):
    data = {
        "provider_name": "Health Insurance Co",
        "policy_number": "POL-001",
        "plan_type": "Premium",
        "coverage_start": date(2026, 1, 1),
        "coverage_end": date(2026, 12, 31),
        "is_primary": False,
        "is_active": True,
    }
    data.update(overrides)
    return data


def vitals_payload(**overrides):
    data = {
        "temperature": Decimal("36.7"),
        "blood_pressure_systolic": 120,
        "blood_pressure_diastolic": 80,
        "heart_rate": 72,
        "respiratory_rate": 16,
        "oxygen_saturation": Decimal("98.0"),
        "weight": Decimal("70.50"),
        "height": Decimal("175.00"),
    }
    data.update(overrides)
    return data


def make_patient(db_session, clinic_id, **overrides):
    """
    Create a raw Patient for service-level tests.

    Uses a deterministic per-test counter instead of id(overrides), because
    id(dict) can be reused and therefore cannot safely guarantee uniqueness.
    """
    if not hasattr(make_patient, "_counter"):
        make_patient._counter = 0

    make_patient._counter += 1

    patient_number = overrides.pop(
        "patient_number",
        f"PT-{clinic_id}-TEST-{make_patient._counter}",
    )

    payload = patient_payload(**overrides)

    patient = Patient(
        clinic_id=clinic_id,
        patient_number=patient_number,
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        date_of_birth=payload["date_of_birth"],
        gender=payload["gender"],
        blood_type=payload["blood_type"],
        phone=payload["phone"],
        email=payload["email"],
        address=payload["address"],
        allergies=payload["allergies"],
        chronic_conditions=payload["chronic_conditions"],
        emirates_id=payload["emirates_id"],
        umrn=payload["umrn"],
        is_active=True,
    )

    db_session.add(patient)
    db_session.flush()

    return patient


def make_staff(
    db_session,
    clinic_id,
    user=None,
    **overrides,
):
    """
    Create a valid Staff record.

    Staff requires first_name and last_name, so provide safe defaults.
    """
    staff = Staff(
        clinic_id=clinic_id,
        first_name=overrides.pop(
            "first_name",
            "Test",
        ),
        last_name=overrides.pop(
            "last_name",
            "Staff",
        ),
        status=overrides.pop(
            "status",
            StaffStatus.ACTIVE,
        ),
        user=user,
        **overrides,
    )

    db_session.add(staff)
    db_session.flush()

    return staff


def suspend_clinic(clinic, db_session):
    """
    Put a clinic into the project's actual inactive lifecycle state.

    The clinic model uses ClinicStatus rather than an is_active boolean.
    """
    clinic.status = ClinicStatus.SUSPENDED
    db_session.flush()


def normalize_datetime(value):
    """
    Normalize aware/naive datetimes so SQLite-backed tests do not fail merely
    because timezone information was stripped during persistence.
    """
    if value is None:
        return None

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


# ===========================================================================
# PATIENT RETRIEVAL
# ===========================================================================

class TestGetPatient:

    def test_get_existing_patient(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        result = get_patient(patient.id)

        assert result is patient
        assert result.id == patient.id
        assert result.clinic_id == clinic.id

    def test_get_missing_patient_raises_not_found(
        self,
        db_session,
    ):
        with pytest.raises(NotFoundError):
            get_patient(999999999)

    def test_get_patient_does_not_require_active_clinic(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        result = get_patient(patient.id)

        assert result.id == patient.id


# ===========================================================================
# PATIENT LISTING
# ===========================================================================

class TestListPatients:

    def test_list_all_patients_for_clinic(
        self,
        db_session,
        clinic,
    ):
        patient1 = make_patient(
            db_session,
            clinic.id,
            first_name="Alice",
            last_name="Brown",
        )

        patient2 = make_patient(
            db_session,
            clinic.id,
            first_name="Bob",
            last_name="Smith",
        )

        results = list_patients(
            clinic_id=clinic.id,
        )

        ids = {
            patient.id
            for patient in results
        }

        assert patient1.id in ids
        assert patient2.id in ids

    def test_list_patients_filters_by_clinic(
        self,
        db_session,
        clinic,
        make_clinic,
    ):
        other_clinic = make_clinic()

        patient1 = make_patient(
            db_session,
            clinic.id,
        )

        patient2 = make_patient(
            db_session,
            other_clinic.id,
        )

        results = list_patients(
            clinic_id=clinic.id,
        )

        ids = {
            patient.id
            for patient in results
        }

        assert patient1.id in ids
        assert patient2.id not in ids

    def test_list_active_patients_only(
        self,
        db_session,
        clinic,
    ):
        active = make_patient(
            db_session,
            clinic.id,
            first_name="Active",
        )

        inactive = make_patient(
            db_session,
            clinic.id,
            first_name="Inactive",
        )

        inactive.is_active = False
        db_session.flush()

        results = list_patients(
            clinic_id=clinic.id,
            active_only=True,
        )

        ids = {
            patient.id
            for patient in results
        }

        assert active.id in ids
        assert inactive.id not in ids

    def test_list_patients_includes_inactive_by_default(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        patient.is_active = False
        db_session.flush()

        results = list_patients(
            clinic_id=clinic.id,
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_search_by_first_name(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
            first_name="Christopher",
            last_name="Stone",
        )

        results = list_patients(
            clinic_id=clinic.id,
            search="christopher",
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_search_by_last_name(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
            first_name="Christopher",
            last_name="Stone",
        )

        results = list_patients(
            clinic_id=clinic.id,
            search="stone",
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_search_by_patient_number(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
            patient_number="PT-SEARCH-001",
        )

        results = list_patients(
            clinic_id=clinic.id,
            search="PT-SEARCH-001",
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_search_by_phone(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
            phone="08055555555",
        )

        results = list_patients(
            clinic_id=clinic.id,
            search="08055555555",
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_search_by_email(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
            email="unique.patient@example.com",
        )

        results = list_patients(
            clinic_id=clinic.id,
            search="unique.patient@example.com",
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_blank_search_behaves_like_no_search(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        results = list_patients(
            clinic_id=clinic.id,
            search="   ",
        )

        assert patient.id in {
            p.id
            for p in results
        }

    def test_patients_are_ordered_by_last_then_first_name(
        self,
        db_session,
        clinic,
    ):
        first = make_patient(
            db_session,
            clinic.id,
            first_name="Zed",
            last_name="Alpha",
        )

        second = make_patient(
            db_session,
            clinic.id,
            first_name="Adam",
            last_name="Beta",
        )

        third = make_patient(
            db_session,
            clinic.id,
            first_name="Aaron",
            last_name="Beta",
        )

        results = list_patients(
            clinic_id=clinic.id,
        )

        relevant = [
            patient.id
            for patient in results
            if patient.id in {
                first.id,
                second.id,
                third.id,
            }
        ]

        assert relevant == [
            first.id,
            third.id,
            second.id,
        ]


# ===========================================================================
# PATIENT CREATION
# ===========================================================================

class TestCreatePatient:

    def test_create_patient_success(
        self,
        db_session,
        clinic,
    ):
        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        assert patient.id is not None
        assert patient.clinic_id == clinic.id
        assert patient.first_name == "John"
        assert patient.last_name == "Doe"
        assert patient.is_active is True
        assert patient.patient_number
        assert patient.patient_number.startswith(
            f"PT{clinic.id}"
        )

    def test_create_patient_generates_unique_numbers(
        self,
        db_session,
        clinic,
    ):
        patient1 = create_patient(
            clinic.id,
            patient_payload(
                email="one@example.com",
            ),
        )

        patient2 = create_patient(
            clinic.id,
            patient_payload(
                email="two@example.com",
            ),
        )

        assert (
            patient1.patient_number
            != patient2.patient_number
        )

    def test_create_rejects_missing_first_name(
        self,
        clinic,
    ):
        data = patient_payload(
            first_name=None,
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_rejects_blank_first_name(
        self,
        clinic,
    ):
        data = patient_payload(
            first_name="   ",
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_rejects_missing_last_name(
        self,
        clinic,
    ):
        data = patient_payload(
            last_name=None,
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_rejects_blank_last_name(
        self,
        clinic,
    ):
        data = patient_payload(
            last_name="   ",
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_rejects_future_date_of_birth(
        self,
        clinic,
    ):
        data = patient_payload(
            date_of_birth=(
                date.today()
                + timedelta(days=1)
            ),
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_accepts_today_as_date_of_birth(
        self,
        clinic,
    ):
        data = patient_payload(
            date_of_birth=date.today(),
        )

        patient = create_patient(
            clinic.id,
            data,
        )

        assert patient.date_of_birth == date.today()

    def test_create_rejects_unknown_fields(
        self,
        clinic,
    ):
        data = patient_payload(
            unauthorized_field="should_not_be_allowed",
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_does_not_accept_client_patient_number(
        self,
        clinic,
    ):
        data = patient_payload(
            patient_number="ATTACKER-CONTROLLED",
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_does_not_accept_client_is_active(
        self,
        clinic,
    ):
        data = patient_payload(
            is_active=False,
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                data,
            )

    def test_create_rejects_inactive_clinic(
        self,
        db_session,
        clinic,
    ):
        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                patient_payload(),
            )

        assert (
            Patient.query
            .filter_by(
                clinic_id=clinic.id,
            )
            .count()
            == 0
        )

    def test_create_strips_patient_names(
        self,
        clinic,
    ):
        patient = create_patient(
            clinic.id,
            patient_payload(
                first_name="  John  ",
                last_name="  Doe  ",
            ),
        )

        assert patient.first_name == "John"
        assert patient.last_name == "Doe"


# ===========================================================================
# PATIENT UPDATE
# ===========================================================================

class TestUpdatePatient:

    def test_update_patient_success(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        result = update_patient(
            patient.id,
            {
                "first_name": "Michael",
                "phone": "08011111111",
            },
        )

        assert result.first_name == "Michael"
        assert result.phone == "08011111111"

    def test_update_partial_payload_preserves_other_fields(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
            first_name="John",
            last_name="Doe",
            phone="08012345678",
        )

        update_patient(
            patient.id,
            {
                "first_name": "Michael",
            },
        )

        assert patient.first_name == "Michael"
        assert patient.last_name == "Doe"
        assert patient.phone == "08012345678"

    def test_update_strips_names(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        update_patient(
            patient.id,
            {
                "first_name": "  Michael  ",
                "last_name": "  Smith  ",
            },
        )

        assert patient.first_name == "Michael"
        assert patient.last_name == "Smith"

    def test_update_rejects_blank_first_name(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            update_patient(
                patient.id,
                {
                    "first_name": "   ",
                },
            )

    def test_update_rejects_blank_last_name(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            update_patient(
                patient.id,
                {
                    "last_name": "   ",
                },
            )

    def test_update_rejects_future_date_of_birth(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            update_patient(
                patient.id,
                {
                    "date_of_birth": (
                        date.today()
                        + timedelta(days=1)
                    ),
                },
            )

    def test_update_rejects_unknown_fields(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            update_patient(
                patient.id,
                {
                    "patient_number": "HACKED",
                },
            )

    def test_update_missing_patient_raises_not_found(
        self,
        db_session,
    ):
        with pytest.raises(NotFoundError):
            update_patient(
                999999999,
                {
                    "first_name": "John",
                },
            )

    def test_update_rejects_inactive_clinic(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            update_patient(
                patient.id,
                {
                    "first_name": "Blocked",
                },
            )


# ===========================================================================
# PATIENT STATUS
# ===========================================================================

class TestPatientStatus:

    def test_deactivate_patient(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        set_active_status(
            patient.id,
            False,
        )

        assert patient.is_active is False

    def test_activate_patient(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        patient.is_active = False
        db_session.flush()

        set_active_status(
            patient.id,
            True,
        )

        assert patient.is_active is True

    def test_setting_existing_status_is_idempotent(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        original_updated_at = normalize_datetime(
            patient.updated_at
        )

        set_active_status(
            patient.id,
            True,
        )

        assert patient.is_active is True
        assert normalize_datetime(
            patient.updated_at
        ) == original_updated_at

    def test_status_update_requires_active_clinic(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            set_active_status(
                patient.id,
                False,
            )


# ===========================================================================
# FAMILY MEMBERS
# ===========================================================================

class TestPatientFamilyMembers:

    def test_list_family_members_empty(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        result = list_family_members(
            patient.id,
        )

        assert result == []

    def test_add_family_member(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        assert member.id is not None
        assert member.patient_id == patient.id
        assert member.full_name == "Jane Doe"
        assert member.relation == FamilyRelation.SPOUSE
        assert member.is_emergency_contact is True

    def test_add_family_member_strips_name(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(
                full_name="  Jane Doe  ",
            ),
        )

        assert member.full_name == "Jane Doe"

    def test_add_family_member_rejects_blank_name(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            add_family_member(
                patient.id,
                family_payload(
                    full_name="   ",
                ),
            )

    def test_add_family_member_rejects_unknown_fields(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            add_family_member(
                patient.id,
                {
                    **family_payload(),
                    "patient_id": 999,
                },
            )

    def test_self_related_patient_is_rejected(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            add_family_member(
                patient.id,
                family_payload(
                    related_patient_id=patient.id,
                ),
            )

    def test_missing_related_patient_is_rejected(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(NotFoundError):
            add_family_member(
                patient.id,
                family_payload(
                    related_patient_id=999999999,
                ),
            )

    def test_related_patient_must_belong_to_same_clinic(
        self,
        db_session,
        clinic,
        make_clinic,
    ):
        other_clinic = make_clinic()

        patient = make_patient(
            db_session,
            clinic.id,
        )

        related = make_patient(
            db_session,
            other_clinic.id,
        )

        with pytest.raises(ValidationError):
            add_family_member(
                patient.id,
                family_payload(
                    related_patient_id=related.id,
                ),
            )

    def test_list_family_members_orders_emergency_first(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        normal = add_family_member(
            patient.id,
            family_payload(
                full_name="Aaron Normal",
                is_emergency_contact=False,
            ),
        )

        emergency = add_family_member(
            patient.id,
            family_payload(
                full_name="Zoe Emergency",
                is_emergency_contact=True,
            ),
        )

        results = list_family_members(
            patient.id,
        )

        ids = [
            member.id
            for member in results
        ]

        assert ids.index(
            emergency.id
        ) < ids.index(
            normal.id
        )

    def test_update_family_member(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        result = update_family_member(
            patient.id,
            member.id,
            {
                "full_name": "Updated Name",
                "phone": "08000000000",
                "is_emergency_contact": False,
            },
        )

        assert result.full_name == "Updated Name"
        assert result.phone == "08000000000"
        assert result.is_emergency_contact is False

    def test_update_family_member_rejects_unknown_fields(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        with pytest.raises(ValidationError):
            update_family_member(
                patient.id,
                member.id,
                {
                    "patient_id": 999,
                },
            )

    def test_update_family_member_missing_member(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(NotFoundError):
            update_family_member(
                patient.id,
                999999999,
                {
                    "full_name": "Nobody",
                },
            )

    def test_remove_family_member(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        remove_family_member(
            patient.id,
            member.id,
        )

        assert (
            db_session.get(
                PatientFamilyMember,
                member.id,
            )
            is None
        )

    def test_remove_family_member_requires_active_clinic(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            remove_family_member(
                patient.id,
                member.id,
            )


# ===========================================================================
# INSURANCE
# ===========================================================================

class TestPatientInsurance:

    def test_list_insurances_empty(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        assert list_insurances(
            patient.id
        ) == []

    def test_add_insurance(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(),
        )

        assert insurance.id is not None
        assert insurance.patient_id == patient.id
        assert insurance.provider_name == "Health Insurance Co"
        assert insurance.policy_number == "POL-001"

    def test_add_insurance_strips_provider_and_policy(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(
                provider_name="  Provider  ",
                policy_number="  POLICY-1  ",
            ),
        )

        assert insurance.provider_name == "Provider"
        assert insurance.policy_number == "POLICY-1"

    def test_add_insurance_rejects_blank_provider(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            add_insurance(
                patient.id,
                insurance_payload(
                    provider_name="   ",
                ),
            )

    def test_add_insurance_rejects_blank_policy(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            add_insurance(
                patient.id,
                insurance_payload(
                    policy_number="   ",
                ),
            )

    def test_add_insurance_rejects_invalid_coverage_range(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            add_insurance(
                patient.id,
                insurance_payload(
                    coverage_start=date(
                        2026,
                        12,
                        31,
                    ),
                    coverage_end=date(
                        2026,
                        1,
                        1,
                    ),
                ),
            )

    def test_add_primary_insurance_demotes_existing_primary(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        first = add_insurance(
            patient.id,
            insurance_payload(
                policy_number="POL-001",
                is_primary=True,
            ),
        )

        second = add_insurance(
            patient.id,
            insurance_payload(
                policy_number="POL-002",
                is_primary=True,
            ),
        )

        db_session.refresh(first)
        db_session.refresh(second)

        assert first.is_primary is False
        assert second.is_primary is True

    def test_multiple_non_primary_insurances_are_allowed(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        first = add_insurance(
            patient.id,
            insurance_payload(
                policy_number="POL-001",
                is_primary=False,
            ),
        )

        second = add_insurance(
            patient.id,
            insurance_payload(
                policy_number="POL-002",
                is_primary=False,
            ),
        )

        assert first.is_primary is False
        assert second.is_primary is False

    def test_update_insurance(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(),
        )

        result = update_insurance(
            patient.id,
            insurance.id,
            {
                "provider_name": "Updated Provider",
                "plan_type": "Gold",
            },
        )

        assert result.provider_name == "Updated Provider"
        assert result.plan_type == "Gold"

    def test_update_insurance_rejects_invalid_effective_range(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(
                coverage_start=date(
                    2026,
                    1,
                    1,
                ),
                coverage_end=date(
                    2026,
                    12,
                    31,
                ),
            ),
        )

        with pytest.raises(ValidationError):
            update_insurance(
                patient.id,
                insurance.id,
                {
                    "coverage_start": date(
                        2027,
                        1,
                        1,
                    ),
                },
            )

    def test_update_insurance_can_promote_to_primary(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        first = add_insurance(
            patient.id,
            insurance_payload(
                policy_number="POL-001",
                is_primary=True,
            ),
        )

        second = add_insurance(
            patient.id,
            insurance_payload(
                policy_number="POL-002",
                is_primary=False,
            ),
        )

        update_insurance(
            patient.id,
            second.id,
            {
                "is_primary": True,
            },
        )

        db_session.refresh(first)
        db_session.refresh(second)

        assert first.is_primary is False
        assert second.is_primary is True

    def test_update_insurance_rejects_blank_provider(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(),
        )

        with pytest.raises(ValidationError):
            update_insurance(
                patient.id,
                insurance.id,
                {
                    "provider_name": "   ",
                },
            )

    def test_update_insurance_rejects_blank_policy(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(),
        )

        with pytest.raises(ValidationError):
            update_insurance(
                patient.id,
                insurance.id,
                {
                    "policy_number": "   ",
                },
            )

    def test_update_missing_insurance_raises_not_found(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(NotFoundError):
            update_insurance(
                patient.id,
                999999999,
                {
                    "plan_type": "Gold",
                },
            )


# ===========================================================================
# VITALS
# ===========================================================================

class TestPatientVitals:

    def test_get_vitals_history_empty(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        assert get_vitals_history(
            patient.id
        ) == []

    def test_get_latest_vitals_empty(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        assert get_latest_vitals(
            patient.id
        ) is None

    def test_record_vitals(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        vitals = record_vitals(
            patient.id,
            vitals_payload(),
        )

        assert vitals.id is not None
        assert vitals.patient_id == patient.id
        assert vitals.temperature_c == Decimal("36.7")
        assert vitals.blood_pressure_systolic == 120
        assert vitals.blood_pressure_diastolic == 80
        assert vitals.heart_rate_bpm == 72
        assert vitals.respiratory_rate == 16
        assert vitals.oxygen_saturation == Decimal("98.0")
        assert vitals.weight_kg == Decimal("70.50")
        assert vitals.height_cm == Decimal("175.00")

    def test_record_vitals_requires_at_least_one_measurement(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {},
            )

    def test_record_vitals_rejects_unknown_fields(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {
                    **vitals_payload(),
                    "unknown_field": 123,
                },
            )

    def test_record_single_vital_measurement(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        vitals = record_vitals(
            patient.id,
            {
                "heart_rate": 80,
            },
        )

        assert vitals.heart_rate_bpm == 80
        assert vitals.temperature_c is None
        assert vitals.weight_kg is None

    def test_record_vitals_with_none_only_is_rejected(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {
                    "temperature": None,
                    "heart_rate": None,
                },
            )

    def test_vitals_history_returns_records(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        first = record_vitals(
            patient.id,
            {
                "heart_rate": 70,
            },
        )

        second = record_vitals(
            patient.id,
            {
                "heart_rate": 80,
            },
        )

        results = get_vitals_history(
            patient.id
        )

        ids = [
            v.id
            for v in results
        ]

        assert first.id in ids
        assert second.id in ids

    def test_latest_vitals_returns_most_recent_record(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        first = record_vitals(
            patient.id,
            {
                "heart_rate": 70,
            },
        )

        second = record_vitals(
            patient.id,
            {
                "heart_rate": 80,
            },
        )

        latest = get_latest_vitals(
            patient.id
        )

        assert latest.id == second.id

    def test_vitals_are_ordered_latest_first(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        first = record_vitals(
            patient.id,
            {
                "heart_rate": 70,
            },
        )

        second = record_vitals(
            patient.id,
            {
                "heart_rate": 80,
            },
        )

        results = get_vitals_history(
            patient.id
        )

        assert results[0].id == second.id
        assert results[1].id == first.id

    def test_record_vitals_missing_patient(
        self,
        db_session,
    ):
        with pytest.raises(NotFoundError):
            record_vitals(
                999999999,
                {
                    "heart_rate": 80,
                },
            )


# ===========================================================================
# VITALS CONSULTATION VALIDATION
# ===========================================================================

class TestVitalsConsultationValidation:

    def test_missing_consultation_is_rejected(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(NotFoundError):
            record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                consultation_id=999999999,
            )


# ===========================================================================
# VITALS STAFF VALIDATION
# ===========================================================================

class TestVitalsStaffValidation:

    def test_missing_staff_is_rejected(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        with pytest.raises(NotFoundError):
            record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                recorded_by_id=999999999,
            )

    def test_inactive_staff_is_rejected(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        staff = make_staff(
            db_session,
            clinic.id,
            status=StaffStatus.ON_LEAVE,
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                recorded_by_id=staff.id,
            )

    def test_staff_from_other_clinic_is_rejected(
        self,
        db_session,
        clinic,
        make_clinic,
    ):
        other_clinic = make_clinic()

        patient = make_patient(
            db_session,
            clinic.id,
        )

        staff = make_staff(
            db_session,
            other_clinic.id,
            status=StaffStatus.ACTIVE,
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
                recorded_by_id=staff.id,
            )


# ===========================================================================
# INACTIVE CLINIC PROTECTION
# ===========================================================================

class TestInactiveClinicProtection:

    def test_add_family_member_blocked(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            add_family_member(
                patient.id,
                family_payload(),
            )

    def test_update_family_member_blocked(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            update_family_member(
                patient.id,
                member.id,
                {
                    "full_name": "Blocked",
                },
            )

    def test_add_insurance_blocked(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            add_insurance(
                patient.id,
                insurance_payload(),
            )

    def test_update_insurance_blocked(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(),
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            update_insurance(
                patient.id,
                insurance.id,
                {
                    "plan_type": "Blocked",
                },
            )

    def test_record_vitals_blocked(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        suspend_clinic(
            clinic,
            db_session,
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {
                    "heart_rate": 80,
                },
            )


# ===========================================================================
# CROSS-PATIENT / OWNERSHIP SAFETY
# ===========================================================================

class TestPatientOwnershipSafety:

    def test_family_member_cannot_be_updated_through_wrong_patient(
        self,
        db_session,
        clinic,
    ):
        patient1 = make_patient(
            db_session,
            clinic.id,
            first_name="Patient",
            last_name="One",
        )

        patient2 = make_patient(
            db_session,
            clinic.id,
            first_name="Patient",
            last_name="Two",
        )

        member = add_family_member(
            patient1.id,
            family_payload(),
        )

        with pytest.raises(NotFoundError):
            update_family_member(
                patient2.id,
                member.id,
                {
                    "full_name": "Attack",
                },
            )

    def test_family_member_cannot_be_removed_through_wrong_patient(
        self,
        db_session,
        clinic,
    ):
        patient1 = make_patient(
            db_session,
            clinic.id,
        )

        patient2 = make_patient(
            db_session,
            clinic.id,
        )

        member = add_family_member(
            patient1.id,
            family_payload(),
        )

        with pytest.raises(NotFoundError):
            remove_family_member(
                patient2.id,
                member.id,
            )

        assert (
            db_session.get(
                PatientFamilyMember,
                member.id,
            )
            is not None
        )

    def test_insurance_cannot_be_updated_through_wrong_patient(
        self,
        db_session,
        clinic,
    ):
        patient1 = make_patient(
            db_session,
            clinic.id,
        )

        patient2 = make_patient(
            db_session,
            clinic.id,
        )

        insurance = add_insurance(
            patient1.id,
            insurance_payload(),
        )

        with pytest.raises(NotFoundError):
            update_insurance(
                patient2.id,
                insurance.id,
                {
                    "plan_type": "Attack",
                },
            )

        assert insurance.plan_type == "Premium"


# ===========================================================================
# TRANSACTION / PERSISTENCE SAFETY
# ===========================================================================

class TestPatientPersistenceSafety:

    def test_failed_patient_creation_does_not_create_patient(
        self,
        db_session,
        clinic,
    ):
        before = (
            Patient.query
            .filter_by(
                clinic_id=clinic.id,
            )
            .count()
        )

        with pytest.raises(ValidationError):
            create_patient(
                clinic.id,
                patient_payload(
                    first_name="   ",
                ),
            )

        after = (
            Patient.query
            .filter_by(
                clinic_id=clinic.id,
            )
            .count()
        )

        assert after == before

    def test_failed_family_creation_does_not_persist_member(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        before = (
            PatientFamilyMember.query
            .filter_by(
                patient_id=patient.id,
            )
            .count()
        )

        with pytest.raises(ValidationError):
            add_family_member(
                patient.id,
                family_payload(
                    full_name="   ",
                ),
            )

        after = (
            PatientFamilyMember.query
            .filter_by(
                patient_id=patient.id,
            )
            .count()
        )

        assert after == before

    def test_failed_insurance_creation_does_not_persist(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        before = (
            PatientInsurance.query
            .filter_by(
                patient_id=patient.id,
            )
            .count()
        )

        with pytest.raises(ValidationError):
            add_insurance(
                patient.id,
                insurance_payload(
                    coverage_start=date(
                        2026,
                        12,
                        31,
                    ),
                    coverage_end=date(
                        2026,
                        1,
                        1,
                    ),
                ),
            )

        after = (
            PatientInsurance.query
            .filter_by(
                patient_id=patient.id,
            )
            .count()
        )

        assert after == before

    def test_failed_vitals_record_does_not_persist(
        self,
        db_session,
        clinic,
    ):
        patient = make_patient(
            db_session,
            clinic.id,
        )

        before = (
            PatientVitals.query
            .filter_by(
                patient_id=patient.id,
            )
            .count()
        )

        with pytest.raises(ValidationError):
            record_vitals(
                patient.id,
                {},
            )

        after = (
            PatientVitals.query
            .filter_by(
                patient_id=patient.id,
            )
            .count()
        )

        assert after == before


# ===========================================================================
# AUDIT COVERAGE
# ===========================================================================

class TestPatientAuditCoverage:

    def test_create_patient_creates_audit_log(
        self,
        db_session,
        clinic,
    ):
        from app.core.audit.models.audit_model import AuditLog

        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        audit = (
            AuditLog.query
            .filter_by(
                action=AuditAction.CREATE,
                entity_type="patient",
                entity_id=patient.id,
            )
            .order_by(
                AuditLog.id.desc()
            )
            .first()
        )

        assert audit is not None
        assert audit.user_id is None

        audit_text = (
            str(audit.description)
            + " "
            + str(audit.old_value)
            + " "
            + str(audit.new_value)
        )

        assert (
            str(patient.patient_number)
            in audit_text
        )

    def test_update_patient_creates_audit_log(
        self,
        db_session,
        clinic,
    ):
        from app.core.audit.models.audit_model import AuditLog

        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        update_patient(
            patient.id,
            {
                "first_name": "Updated",
            },
        )

        audit = (
            AuditLog.query
            .filter_by(
                action=AuditAction.UPDATE,
                entity_type="patient",
                entity_id=patient.id,
            )
            .order_by(
                AuditLog.id.desc()
            )
            .first()
        )

        assert audit is not None
        assert audit.user_id is None

    def test_patient_status_change_creates_audit_log(
        self,
        db_session,
        clinic,
    ):
        from app.core.audit.models.audit_model import AuditLog

        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        set_active_status(
            patient.id,
            False,
        )

        audit = (
            AuditLog.query
            .filter_by(
                action=AuditAction.UPDATE,
                entity_type="patient",
                entity_id=patient.id,
            )
            .order_by(
                AuditLog.id.desc()
            )
            .first()
        )

        assert audit is not None
        assert audit.user_id is None

    def test_family_create_creates_audit_log(
        self,
        db_session,
        clinic,
    ):
        from app.core.audit.models.audit_model import AuditLog

        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        member = add_family_member(
            patient.id,
            family_payload(),
        )

        audit = (
            AuditLog.query
            .filter_by(
                action=AuditAction.CREATE,
                entity_type="patient_family_member",
                entity_id=member.id,
            )
            .order_by(
                AuditLog.id.desc()
            )
            .first()
        )

        assert audit is not None
        assert audit.user_id is None

    def test_insurance_create_creates_audit_log(
        self,
        db_session,
        clinic,
    ):
        from app.core.audit.models.audit_model import AuditLog

        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        insurance = add_insurance(
            patient.id,
            insurance_payload(),
        )

        audit = (
            AuditLog.query
            .filter_by(
                action=AuditAction.CREATE,
                entity_type="patient_insurance",
                entity_id=insurance.id,
            )
            .order_by(
                AuditLog.id.desc()
            )
            .first()
        )

        assert audit is not None
        assert audit.user_id is None

    def test_vitals_create_creates_audit_log(
        self,
        db_session,
        clinic,
    ):
        from app.core.audit.models.audit_model import AuditLog

        patient = create_patient(
            clinic.id,
            patient_payload(),
        )

        vitals = record_vitals(
            patient.id,
            {
                "heart_rate": 80,
            },
        )

        audit = (
            AuditLog.query
            .filter_by(
                action=AuditAction.CREATE,
                entity_type="patient_vitals",
                entity_id=vitals.id,
            )
            .order_by(
                AuditLog.id.desc()
            )
            .first()
        )

        assert audit is not None
        assert audit.user_id is None