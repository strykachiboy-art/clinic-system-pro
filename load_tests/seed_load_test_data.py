from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app import create_app
from app.core.auth.user.services.user_service import (
    get_user_by_email,
    register_user,
)
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.clinic.services.clinic_service import (
    add_ai_credits,
    create_clinic,
)
from app.modules.patient.models.patient_model import Patient
from app.modules.patient.services.patient_service import (
    create_patient,
)


LOAD_TEST_EMAIL = "loadtest@clinicload.com"
LOAD_TEST_PASSWORD = "LoadTestPassword123!"
LOAD_TEST_CLINIC_NAME = "Clinic Load Test"
LOAD_TEST_PATIENT_EMAIL = "loadtest-patient@clinicload.com"
AI_CREDITS = 100_000


def get_or_create_clinic():
    clinic = db.session.execute(
        select(Clinic)
        .where(
            Clinic.name == LOAD_TEST_CLINIC_NAME
        )
        .limit(1)
    ).scalar_one_or_none()

    if clinic is not None:
        return clinic

    return create_clinic(
        name=LOAD_TEST_CLINIC_NAME,
        city="Asaba",
        country="Nigeria",
        timezone="Africa/Lagos",
    )


def get_or_create_user(clinic_id: int):
    user = get_user_by_email(
        LOAD_TEST_EMAIL
    )

    if user is not None:
        if user.clinic_id != clinic_id:
            raise RuntimeError(
                f"Existing load-test user belongs to clinic "
                f"{user.clinic_id}, expected {clinic_id}"
            )

        if user.role != Role.ADMIN:
            raise RuntimeError(
                f"Existing load-test user has role "
                f"{user.role.value}, expected admin"
            )

        return user

    return register_user(
        email=LOAD_TEST_EMAIL,
        password=LOAD_TEST_PASSWORD,
        role=Role.ADMIN,
        clinic_id=clinic_id,
    )


def get_or_create_patient(
    clinic_id: int,
    actor_id: int,
):
    patient = db.session.execute(
        select(Patient)
        .where(
            Patient.clinic_id == clinic_id,
            Patient.email == LOAD_TEST_PATIENT_EMAIL,
        )
        .limit(1)
    ).scalar_one_or_none()

    if patient is not None:
        return patient

    return create_patient(
        clinic_id=clinic_id,
        actor_id=actor_id,
        data={
            "first_name": "Load",
            "last_name": "Test",
            "email": LOAD_TEST_PATIENT_EMAIL,
            "phone": "08000000000",
        },
    )


def ensure_ai_credits(clinic: Clinic):
    if clinic.ai_credits >= AI_CREDITS:
        return clinic

    return add_ai_credits(
        clinic_id=clinic.id,
        amount=AI_CREDITS - clinic.ai_credits,
    )


def main():
    app = create_app("development")

    with app.app_context():
        clinic = get_or_create_clinic()

        user = get_or_create_user(
            clinic.id
        )

        patient = get_or_create_patient(
            clinic.id,
            user.id,
        )

        clinic = ensure_ai_credits(
            clinic
        )

        db.session.expire_all()

        print()
        print("=== Clinic Load Test Dataset ===")
        print(
            f"Clinic ID:       {clinic.id}"
        )
        print(
            f"Clinic name:     {clinic.name}"
        )
        print(
            f"User ID:         {user.id}"
        )
        print(
            f"User email:      {LOAD_TEST_EMAIL}"
        )
        print(
            f"User password:   {LOAD_TEST_PASSWORD}"
        )
        print(
            f"User role:       {user.role.value}"
        )
        print(
            f"Patient ID:      {patient.id}"
        )
        print(
            f"Patient name:    "
            f"{patient.first_name} {patient.last_name}"
        )
        print(
            f"AI credits:      {clinic.ai_credits}"
        )
        print()


if __name__ == "__main__":
    main()