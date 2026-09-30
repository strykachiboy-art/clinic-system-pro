from __future__ import annotations

from app.extensions import db
from app.modules.patient.models.patient_model import PatientFamilyMember
from app.modules.patient.services import patient_service

from load_tests.resilience.checks.integrity import (
    assert_patient_data_integrity,
)


def test_patient_family_data_integrity_after_valid_workflow(
    db_session,
    clinic,
):
    parent = patient_service.create_patient(
        clinic.id,
        {
            "first_name": "Integrity",
            "last_name": "Parent",
            "email": "integrity-parent@test.com",
        },
    )

    related = patient_service.create_patient(
        clinic.id,
        {
            "first_name": "Integrity",
            "last_name": "Related",
            "email": "integrity-related@test.com",
        },
    )

    member = patient_service.add_family_member(
        parent.id,
        {
            "full_name": "Integrity Related",
            "relation": "sibling",
            "phone": "+2348100000000",
            "related_patient_id": related.id,
        },
    )

    db_session.commit()
    db_session.expire_all()

    persisted = db_session.get(
        PatientFamilyMember,
        member.id,
    )

    assert persisted is not None
    assert persisted.patient_id == parent.id
    assert persisted.related_patient_id == related.id

    assert_patient_data_integrity(db_session)
