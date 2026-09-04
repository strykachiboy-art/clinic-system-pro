from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import or_

from app.extensions import db
from app.core.enums.staff_enums import StaffStatus
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.enums.audit_enums import AuditAction
from app.core.utils.decorators import transactional
from app.core.audit.services.audit_services import create_audit_log
from app.core.utils.qrcode_util import generate_tracking_code

from app.modules.patient.models.patient_model import (
    Patient,
    PatientFamilyMember,
    PatientInsurance,
    PatientVitals,
)
from app.modules.clinic.services.clinic_service import ensure_clinic_active
from app.modules.staff.models.staff_model import Staff


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EDITABLE_PATIENT_FIELDS = {
    "first_name",
    "last_name",
    "date_of_birth",
    "gender",
    "blood_type",
    "phone",
    "email",
    "address",
    "allergies",
    "chronic_conditions",
    "emirates_id",
    "umrn",
}

_EDITABLE_FAMILY_FIELDS = {
    "full_name",
    "relation",
    "phone",
    "is_emergency_contact",
}

_EDITABLE_INSURANCE_FIELDS = {
    "provider_name",
    "policy_number",
    "plan_type",
    "coverage_start",
    "coverage_end",
    "is_primary",
    "is_active",
}

_EDITABLE_VITAL_FIELDS = {
    "temperature",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "heart_rate",
    "respiratory_rate",
    "oxygen_saturation",
    "weight",
    "height",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_patient_names(
    first_name: str,
    last_name: str,
) -> None:
    if not first_name or not first_name.strip():
        raise ValidationError("First name is required")

    if not last_name or not last_name.strip():
        raise ValidationError("Last name is required")


def _validate_date_of_birth(date_of_birth: Optional[date]) -> None:
    if date_of_birth is not None and date_of_birth > date.today():
        raise ValidationError("Date of birth cannot be in the future")


def _validate_fields(
    data: dict,
    allowed_fields: set[str],
) -> None:
    unknown_fields = set(data) - allowed_fields

    if unknown_fields:
        raise ValidationError(
            f"Unknown fields: {', '.join(sorted(unknown_fields))}"
        )


def _generate_patient_number(clinic_id: int) -> str:
    """
    Generate a unique patient number.

    The database unique constraint remains the final guarantee against
    concurrent collisions. The retry loop handles normal collisions.
    """
    for _ in range(5):
        patient_number = generate_tracking_code(f"PT{clinic_id}")

        exists = (
            db.session.query(Patient.id)
            .filter(Patient.patient_number == patient_number)
            .first()
        )

        if not exists:
            return patient_number

    raise ConflictError(
        "Unable to generate a unique patient number. Please try again."
    )


def _get_patient_or_404(patient_id: int) -> Patient:
    patient = db.session.get(Patient, patient_id)

    if patient is None:
        raise NotFoundError(f"Patient {patient_id} not found")

    return patient


def _get_family_member_or_404(
    patient_id: int,
    family_member_id: int,
) -> PatientFamilyMember:
    member = (
        PatientFamilyMember.query
        .filter(
            PatientFamilyMember.id == family_member_id,
            PatientFamilyMember.patient_id == patient_id,
        )
        .first()
    )

    if member is None:
        raise NotFoundError(
            f"Family member {family_member_id} not found for patient {patient_id}"
        )

    return member


def _get_insurance_or_404(
    patient_id: int,
    insurance_id: int,
) -> PatientInsurance:
    insurance = (
        PatientInsurance.query
        .filter(
            PatientInsurance.id == insurance_id,
            PatientInsurance.patient_id == patient_id,
        )
        .first()
    )

    if insurance is None:
        raise NotFoundError(
            f"Insurance {insurance_id} not found for patient {patient_id}"
        )

    return insurance


def _get_vitals_or_404(
    patient_id: int,
    vitals_id: int,
) -> PatientVitals:
    vitals = (
        PatientVitals.query
        .filter(
            PatientVitals.id == vitals_id,
            PatientVitals.patient_id == patient_id,
        )
        .first()
    )

    if vitals is None:
        raise NotFoundError(
            f"Vitals record {vitals_id} not found for patient {patient_id}"
        )

    return vitals


def _validate_related_patient(
    patient: Patient,
    related_patient_id: Optional[int],
) -> Optional[Patient]:
    if related_patient_id is None:
        return None

    if related_patient_id == patient.id:
        raise ValidationError(
            "A patient cannot be related to themselves"
        )

    related_patient = db.session.get(Patient, related_patient_id)

    if related_patient is None:
        raise NotFoundError(
            f"Related patient {related_patient_id} not found"
        )

    if related_patient.clinic_id != patient.clinic_id:
        raise ValidationError(
            "Related patient must belong to the same clinic"
        )

    return related_patient


def _validate_staff_for_patient(
    clinic_id: int,
    staff_id: Optional[int],
) -> Optional[Staff]:
    if staff_id is None:
        return None

    staff = db.session.get(Staff, staff_id)

    if staff is None:
        raise NotFoundError(f"Staff {staff_id} not found")

    if staff.clinic_id != clinic_id:
        raise ValidationError(
            "Staff member must belong to the same clinic as the patient"
        )

    if staff.status != StaffStatus.ACTIVE:
        raise ValidationError(
            f"Staff member {staff_id} is not active"
        )

    if staff.user is not None and not staff.user.is_active:
        raise ValidationError(
            f"User account for staff member {staff_id} is not active"
        )

    return staff


def _validate_consultation_for_vitals(
    patient: Patient,
    consultation_id: Optional[int],
):
    if consultation_id is None:
        return None

    # Lazy import prevents circular import issues during application startup.
    from app.modules.consultation.models.consultation_model import (
        Consultation,
    )

    consultation = db.session.get(Consultation, consultation_id)

    if consultation is None:
        raise NotFoundError(
            f"Consultation {consultation_id} not found"
        )

    if consultation.clinic_id != patient.clinic_id:
        raise ValidationError(
            "Consultation must belong to the same clinic as the patient"
        )

    if consultation.patient_id != patient.id:
        raise ValidationError(
            "Consultation must belong to the same patient"
        )

    return consultation


# ---------------------------------------------------------------------------
# Patient retrieval
# ---------------------------------------------------------------------------

def get_patient(patient_id: int) -> Patient:
    """
    Retrieve a patient.

    This is intentionally a read operation and therefore does NOT require
    the patient's clinic to be active. Historical patient data remains
    accessible for inactive or suspended clinics.
    """
    return _get_patient_or_404(patient_id)


def list_patients(
    clinic_id: Optional[int] = None,
    active_only: bool = False,
    search: Optional[str] = None,
):
    """
    List patients.

    Read operations remain available even when a clinic is inactive or
    suspended.
    """
    query = Patient.query

    if clinic_id is not None:
        query = query.filter(Patient.clinic_id == clinic_id)

    if active_only:
        query = query.filter(Patient.is_active.is_(True))

    if search:
        search_term = search.strip()

        if search_term:
            pattern = f"%{search_term}%"

            query = query.filter(
                or_(
                    Patient.first_name.ilike(pattern),
                    Patient.last_name.ilike(pattern),
                    Patient.patient_number.ilike(pattern),
                    Patient.phone.ilike(pattern),
                    Patient.email.ilike(pattern),
                )
            )

    return query.order_by(
        Patient.last_name.asc(),
        Patient.first_name.asc(),
    ).all()


# ---------------------------------------------------------------------------
# Patient creation / update / lifecycle
# ---------------------------------------------------------------------------

@transactional
def create_patient(
    clinic_id: int,
    data: dict,
) -> Patient:
    ensure_clinic_active(clinic_id)

    _validate_fields(data, _EDITABLE_PATIENT_FIELDS | {
        "first_name",
        "last_name",
    })

    first_name = data.get("first_name")
    last_name = data.get("last_name")

    _validate_patient_names(first_name, last_name)
    _validate_date_of_birth(data.get("date_of_birth"))

    patient_number = _generate_patient_number(clinic_id)

    patient = Patient(
        clinic_id=clinic_id,
        patient_number=patient_number,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        date_of_birth=data.get("date_of_birth"),
        gender=data.get("gender"),
        blood_type=data.get("blood_type"),
        phone=data.get("phone"),
        email=data.get("email"),
        address=data.get("address"),
        allergies=data.get("allergies"),
        chronic_conditions=data.get("chronic_conditions"),
        emirates_id=data.get("emirates_id"),
        umrn=data.get("umrn"),
        is_active=True,
    )

    db.session.add(patient)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        resource_type="patient",
        resource_id=patient.id,
        details={
            "clinic_id": clinic_id,
            "patient_number": patient.patient_number,
        },
    )

    return patient


@transactional
def update_patient(
    patient_id: int,
    data: dict,
) -> Patient:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    _validate_fields(data, _EDITABLE_PATIENT_FIELDS)

    if "date_of_birth" in data:
        _validate_date_of_birth(data["date_of_birth"])

    if "first_name" in data:
        if not data["first_name"] or not data["first_name"].strip():
            raise ValidationError("First name cannot be empty")

    if "last_name" in data:
        if not data["last_name"] or not data["last_name"].strip():
            raise ValidationError("Last name cannot be empty")

    changed_fields = {}

    for field, value in data.items():
        if field in {"first_name", "last_name"} and value is not None:
            value = value.strip()

        old_value = getattr(patient, field)

        if old_value != value:
            changed_fields[field] = {
                "old": old_value,
                "new": value,
            }
            setattr(patient, field, value)

    if changed_fields:
        patient.updated_at = _utcnow()

        create_audit_log(
            action=AuditAction.UPDATE,
            resource_type="patient",
            resource_id=patient.id,
            details={
                "clinic_id": patient.clinic_id,
                "changed_fields": changed_fields,
            },
        )

    return patient


@transactional
def set_active_status(
    patient_id: int,
    is_active: bool,
) -> Patient:
    """
    Activate/deactivate a patient.

    This does NOT delete the patient or historical records.
    """
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    if patient.is_active == is_active:
        return patient

    old_status = patient.is_active
    patient.is_active = is_active
    patient.updated_at = _utcnow()

    create_audit_log(
        action=AuditAction.UPDATE,
        resource_type="patient",
        resource_id=patient.id,
        details={
            "clinic_id": patient.clinic_id,
            "is_active": {
                "old": old_status,
                "new": is_active,
            },
        },
    )

    return patient


# ---------------------------------------------------------------------------
# Family members
# ---------------------------------------------------------------------------

def list_family_members(
    patient_id: int,
):
    """
    Read operation. Historical family contacts remain accessible regardless
    of clinic status.
    """
    patient = _get_patient_or_404(patient_id)

    return (
        PatientFamilyMember.query
        .filter(PatientFamilyMember.patient_id == patient.id)
        .order_by(
            PatientFamilyMember.is_emergency_contact.desc(),
            PatientFamilyMember.full_name.asc(),
        )
        .all()
    )


@transactional
def add_family_member(
    patient_id: int,
    data: dict,
) -> PatientFamilyMember:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    allowed_fields = _EDITABLE_FAMILY_FIELDS | {"related_patient_id"}
    _validate_fields(data, allowed_fields)

    full_name = data.get("full_name")

    if not full_name or not full_name.strip():
        raise ValidationError("Family member name is required")

    related_patient_id = data.get("related_patient_id")

    _validate_related_patient(
        patient,
        related_patient_id,
    )

    member = PatientFamilyMember(
        patient_id=patient.id,
        related_patient_id=related_patient_id,
        full_name=full_name.strip(),
        relation=data.get("relation"),
        phone=data.get("phone"),
        is_emergency_contact=data.get(
            "is_emergency_contact",
            False,
        ),
    )

    db.session.add(member)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        resource_type="patient_family_member",
        resource_id=member.id,
        details={
            "clinic_id": patient.clinic_id,
            "patient_id": patient.id,
            "related_patient_id": related_patient_id,
        },
    )

    return member


@transactional
def update_family_member(
    patient_id: int,
    family_member_id: int,
    data: dict,
) -> PatientFamilyMember:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    _validate_fields(data, _EDITABLE_FAMILY_FIELDS | {
        "related_patient_id",
    })

    member = _get_family_member_or_404(
        patient.id,
        family_member_id,
    )

    if "related_patient_id" in data:
        _validate_related_patient(
            patient,
            data["related_patient_id"],
        )

    if "full_name" in data:
        if not data["full_name"] or not data["full_name"].strip():
            raise ValidationError(
                "Family member name cannot be empty"
            )

    changed_fields = {}

    for field, value in data.items():
        if field == "full_name" and value is not None:
            value = value.strip()

        old_value = getattr(member, field)

        if old_value != value:
            changed_fields[field] = {
                "old": old_value,
                "new": value,
            }
            setattr(member, field, value)

    if changed_fields:
        member.updated_at = _utcnow()

        create_audit_log(
            action=AuditAction.UPDATE,
            resource_type="patient_family_member",
            resource_id=member.id,
            details={
                "clinic_id": patient.clinic_id,
                "patient_id": patient.id,
                "changed_fields": changed_fields,
            },
        )

    return member


@transactional
def remove_family_member(
    patient_id: int,
    family_member_id: int,
) -> None:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    member = _get_family_member_or_404(
        patient.id,
        family_member_id,
    )

    create_audit_log(
        action=AuditAction.DELETE,
        resource_type="patient_family_member",
        resource_id=member.id,
        details={
            "clinic_id": patient.clinic_id,
            "patient_id": patient.id,
        },
    )

    db.session.delete(member)


# ---------------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------------

def list_insurances(
    patient_id: int,
):
    """
    Read operation. Historical insurance records remain accessible even if
    the clinic is inactive or suspended.
    """
    patient = _get_patient_or_404(patient_id)

    return (
        PatientInsurance.query
        .filter(PatientInsurance.patient_id == patient.id)
        .order_by(
            PatientInsurance.is_primary.desc(),
            PatientInsurance.is_active.desc(),
            PatientInsurance.created_at.desc(),
        )
        .all()
    )


@transactional
def add_insurance(
    patient_id: int,
    data: dict,
) -> PatientInsurance:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    _validate_fields(data, _EDITABLE_INSURANCE_FIELDS)

    provider_name = data.get("provider_name")
    policy_number = data.get("policy_number")

    if not provider_name or not provider_name.strip():
        raise ValidationError("Insurance provider name is required")

    if not policy_number or not policy_number.strip():
        raise ValidationError("Insurance policy number is required")

    coverage_start = data.get("coverage_start")
    coverage_end = data.get("coverage_end")

    if (
        coverage_start is not None
        and coverage_end is not None
        and coverage_start > coverage_end
    ):
        raise ValidationError(
            "Insurance coverage start date cannot be after coverage end date"
        )

    is_primary = data.get("is_primary", False)

    if is_primary:
        PatientInsurance.query.filter(
            PatientInsurance.patient_id == patient.id,
            PatientInsurance.is_primary.is_(True),
        ).update(
            {
                PatientInsurance.is_primary: False,
                PatientInsurance.updated_at: _utcnow(),
            },
            synchronize_session=False,
        )

    insurance = PatientInsurance(
        patient_id=patient.id,
        provider_name=provider_name.strip(),
        policy_number=policy_number.strip(),
        plan_type=data.get("plan_type"),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        is_primary=is_primary,
        is_active=data.get("is_active", True),
    )

    db.session.add(insurance)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        resource_type="patient_insurance",
        resource_id=insurance.id,
        details={
            "clinic_id": patient.clinic_id,
            "patient_id": patient.id,
            "provider_name": insurance.provider_name,
            "is_primary": insurance.is_primary,
        },
    )

    return insurance


@transactional
def update_insurance(
    patient_id: int,
    insurance_id: int,
    data: dict,
) -> PatientInsurance:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    _validate_fields(data, _EDITABLE_INSURANCE_FIELDS)

    insurance = _get_insurance_or_404(
        patient.id,
        insurance_id,
    )

    if "coverage_start" in data or "coverage_end" in data:
        coverage_start = data.get(
            "coverage_start",
            insurance.coverage_start,
        )
        coverage_end = data.get(
            "coverage_end",
            insurance.coverage_end,
        )

        if (
            coverage_start is not None
            and coverage_end is not None
            and coverage_start > coverage_end
        ):
            raise ValidationError(
                "Insurance coverage start date cannot be after coverage end date"
            )

    if "provider_name" in data:
        if (
            data["provider_name"] is None
            or not data["provider_name"].strip()
        ):
            raise ValidationError(
                "Insurance provider name cannot be empty"
            )

    if "policy_number" in data:
        if (
            data["policy_number"] is None
            or not data["policy_number"].strip()
        ):
            raise ValidationError(
                "Insurance policy number cannot be empty"
            )

    if data.get("is_primary") is True:
        PatientInsurance.query.filter(
            PatientInsurance.patient_id == patient.id,
            PatientInsurance.id != insurance.id,
            PatientInsurance.is_primary.is_(True),
        ).update(
            {
                PatientInsurance.is_primary: False,
                PatientInsurance.updated_at: _utcnow(),
            },
            synchronize_session=False,
        )

    changed_fields = {}

    for field, value in data.items():
        if field in {"provider_name", "policy_number"} and value is not None:
            value = value.strip()

        old_value = getattr(insurance, field)

        if old_value != value:
            changed_fields[field] = {
                "old": old_value,
                "new": value,
            }
            setattr(insurance, field, value)

    if changed_fields:
        insurance.updated_at = _utcnow()

        create_audit_log(
            action=AuditAction.UPDATE,
            resource_type="patient_insurance",
            resource_id=insurance.id,
            details={
                "clinic_id": patient.clinic_id,
                "patient_id": patient.id,
                "changed_fields": changed_fields,
            },
        )

    return insurance


# ---------------------------------------------------------------------------
# Vitals
# ---------------------------------------------------------------------------

def get_vitals_history(
    patient_id: int,
):
    """
    Read operation. Historical vitals remain available regardless of clinic
    status.
    """
    patient = _get_patient_or_404(patient_id)

    return (
        PatientVitals.query
        .filter(PatientVitals.patient_id == patient.id)
        .order_by(
            PatientVitals.recorded_at.desc(),
            PatientVitals.id.desc(),
        )
        .all()
    )


def get_latest_vitals(
    patient_id: int,
) -> Optional[PatientVitals]:
    """
    Read operation. Historical vitals remain available regardless of clinic
    status.
    """
    patient = _get_patient_or_404(patient_id)

    return (
        PatientVitals.query
        .filter(PatientVitals.patient_id == patient.id)
        .order_by(
            PatientVitals.recorded_at.desc(),
            PatientVitals.id.desc(),
        )
        .first()
    )


@transactional
def record_vitals(
    patient_id: int,
    data: dict,
    consultation_id: Optional[int] = None,
    recorded_by_id: Optional[int] = None,
) -> PatientVitals:
    patient = _get_patient_or_404(patient_id)

    ensure_clinic_active(patient.clinic_id)

    _validate_fields(data, _EDITABLE_VITAL_FIELDS)

    if not data:
        raise ValidationError(
            "At least one vital measurement is required"
        )

    # Validate every supplied value is not explicitly None.
    # A vitals record with no actual measurement is not useful.
    measurements = {
        field: value
        for field, value in data.items()
        if field in _EDITABLE_VITAL_FIELDS
        and value is not None
    }

    if not measurements:
        raise ValidationError(
            "At least one vital measurement is required"
        )

    # Critical ownership checks:
    # consultation -> same clinic + same patient
    # staff -> same clinic + active
    _validate_consultation_for_vitals(
        patient,
        consultation_id,
    )

    _validate_staff_for_patient(
        patient.clinic_id,
        recorded_by_id,
    )

    vitals = PatientVitals(
        patient_id=patient.id,
        consultation_id=consultation_id,
        recorded_by_id=recorded_by_id,
        temperature=data.get("temperature"),
        blood_pressure_systolic=data.get(
            "blood_pressure_systolic"
        ),
        blood_pressure_diastolic=data.get(
            "blood_pressure_diastolic"
        ),
        heart_rate=data.get("heart_rate"),
        respiratory_rate=data.get("respiratory_rate"),
        oxygen_saturation=data.get("oxygen_saturation"),
        weight=data.get("weight"),
        height=data.get("height"),
        recorded_at=data.get("recorded_at", _utcnow()),
    )

    db.session.add(vitals)
    db.session.flush()

    create_audit_log(
        action=AuditAction.CREATE,
        resource_type="patient_vitals",
        resource_id=vitals.id,
        details={
            "clinic_id": patient.clinic_id,
            "patient_id": patient.id,
            "consultation_id": consultation_id,
            "recorded_by_id": recorded_by_id,
        },
    )

    return vitals