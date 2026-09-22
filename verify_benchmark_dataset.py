from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from app import create_app
from app.extensions import db

from app.core.auth.user.models.user_device_model import UserDevice
from app.modules.ambulance.models.ambulance_model import (
    AmbulanceTrip,
    AmbulanceVehicle,
)
from app.modules.appointment.models.appointment_model import Appointment
from app.modules.billing.models.billing_model import Invoice
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.message_model import Message
from app.modules.clinic.models.clinic_model import Clinic
from app.modules.consultation.models.consultation_model import Consultation
from app.modules.inventory.models.inventory_model import InventoryItem
from app.modules.lab.models.lab_model import LabOrder, LabTest
from app.modules.patient.models.patient_model import Patient
from app.modules.pharmacy.models.pharmacy_model import Drug
from app.modules.prescription.models.prescription_model import Prescription
from app.modules.reports.models.reports_model import GeneratedReport
from app.modules.staff.models.staff_model import Staff
from app.modules.ward.models.ward_model import Bed, Ward


PROJECT_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = (
    PROJECT_ROOT
    / "load_tests"
    / "benchmark_dataset.json"
)

BENCHMARK_PREFIX = "BENCHMARK"
CONTROL_EMAIL = "loadtest@clinicload.com"


app = create_app("development")


def count(query):
    return db.session.execute(query).scalar_one()


with app.app_context():
    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )

    clinic_id = manifest["clinic_id"]
    expected = manifest["actual_counts"]
    configured = manifest["configured_counts"]

    clinic = db.session.get(
        Clinic,
        clinic_id,
    )

    if clinic is None:
        raise RuntimeError(
            f"Benchmark clinic {clinic_id} does not exist."
        )

    print("=" * 80)
    print("BENCHMARK DATASET VERIFICATION")
    print("=" * 80)

    print(f"Manifest:   {MANIFEST_PATH}")
    print(f"Clinic ID:  {clinic.id}")
    print(f"Clinic:     {clinic.name}")
    print(
        f"Version:    "
        f"{manifest['dataset_version']}"
    )

    queries = {
        "staff": count(
            select(func.count(Staff.id)).where(
                Staff.clinic_id == clinic_id,
                Staff.email.like(
                    f"{BENCHMARK_PREFIX.lower()}-staff-%"
                ),
            )
        ),
        "patients": count(
            select(func.count(Patient.id)).where(
                Patient.clinic_id == clinic_id,
                Patient.patient_number.like(
                    f"{BENCHMARK_PREFIX}-PT-%"
                ),
            )
        ),
        "appointments": count(
            select(func.count(Appointment.id)).where(
                Appointment.clinic_id == clinic_id,
                Appointment.google_calendar_event_id.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "consultations": count(
            select(func.count(Consultation.id)).where(
                Consultation.clinic_id == clinic_id,
                Consultation.notes.like(
                    f"{BENCHMARK_PREFIX}:%"
                ),
            )
        ),
        "lab_tests": count(
            select(func.count(LabTest.id)).where(
                LabTest.clinic_id == clinic_id,
                LabTest.code.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "lab_orders": count(
            select(func.count(LabOrder.id)).where(
                LabOrder.clinic_id == clinic_id,
                LabOrder.qr_code.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "drugs": count(
            select(func.count(Drug.id)).where(
                Drug.clinic_id == clinic_id,
                Drug.name.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "prescriptions": count(
            select(func.count(Prescription.id)).where(
                Prescription.clinic_id == clinic_id,
                Prescription.notes.like(
                    f"{BENCHMARK_PREFIX}:%"
                ),
            )
        ),
        "inventory_items": count(
            select(func.count(InventoryItem.id)).where(
                InventoryItem.clinic_id == clinic_id,
                InventoryItem.name.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "wards": count(
            select(func.count(Ward.id)).where(
                Ward.clinic_id == clinic_id,
                Ward.name.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "beds": count(
            select(func.count(Bed.id)).where(
                Bed.bed_number.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "ambulances": count(
            select(
                func.count(AmbulanceVehicle.id)
            ).where(
                AmbulanceVehicle.clinic_id
                == clinic_id,
                AmbulanceVehicle.plate_number.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "ambulance_trips": count(
            select(
                func.count(AmbulanceTrip.id)
            ).where(
                AmbulanceTrip.clinic_id
                == clinic_id,
                AmbulanceTrip.notes.like(
                    f"{BENCHMARK_PREFIX}:%"
                ),
            )
        ),
        "invoices": count(
            select(func.count(Invoice.id)).where(
                Invoice.clinic_id == clinic_id,
                Invoice.invoice_number.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "notifications": count(
            select(
                func.count()
            ).select_from(
                __import__(
                    "app.core.notifications.models.notification_models",
                    fromlist=["Notification"],
                ).Notification
            ).where(
                __import__(
                    "app.core.notifications.models.notification_models",
                    fromlist=["Notification"],
                ).Notification.clinic_id
                == clinic_id,
                __import__(
                    "app.core.notifications.models.notification_models",
                    fromlist=["Notification"],
                ).Notification.title.like(
                    f"{BENCHMARK_PREFIX}:%"
                ),
            )
        ),
        "conversations": count(
            select(func.count(Conversation.id)).where(
                Conversation.clinic_id == clinic_id,
                Conversation.title.like(
                    f"{BENCHMARK_PREFIX}-%"
                ),
            )
        ),
        "messages": count(
            select(func.count(Message.id)).where(
                Message.clinic_id == clinic_id,
                Message.content.like(
                    f"{BENCHMARK_PREFIX}:%"
                ),
            )
        ),
        "reports": count(
            select(func.count(GeneratedReport.id)).where(
                GeneratedReport.clinic_id == clinic_id,
                GeneratedReport.file_url.like(
                    f"{BENCHMARK_PREFIX}:%"
                ),
            )
        ),
    }

    control_user = db.session.execute(
        select(
            __import__(
                "app.core.auth.user.models.user_model",
                fromlist=["User"],
            ).User
        ).where(
            __import__(
                "app.core.auth.user.models.user_model",
                fromlist=["User"],
            ).User.email
            == CONTROL_EMAIL
        )
    ).scalar_one_or_none()

    queries["user_devices"] = count(
        select(func.count(UserDevice.id)).where(
            UserDevice.user_id == control_user.id,
            UserDevice.device_token.like(
                f"{BENCHMARK_PREFIX}-DEVICE-%"
            ),
        )
    ) if control_user else 0

    print()
    print(
        f"{'DATASET':<22}"
        f"{'EXPECTED':>12}"
        f"{'DATABASE':>12}"
        f"{'STATUS':>12}"
    )
    print("-" * 58)

    problems = []

    for key in expected:
        expected_value = expected[key]
        actual_value = queries.get(key, 0)

        status = (
            "OK"
            if expected_value == actual_value
            else "MISMATCH"
        )

        print(
            f"{key:<22}"
            f"{expected_value:>12}"
            f"{actual_value:>12}"
            f"{status:>12}"
        )

        if status != "OK":
            problems.append(
                (
                    key,
                    expected_value,
                    actual_value,
                )
            )

    print("-" * 58)

    expected_trips = configured["ambulance_trips"]
    actual_trips = queries["ambulance_trips"]

    trip_status = (
        "OK"
        if expected_trips == actual_trips
        else "MISMATCH"
    )

    print(
        f"{'ambulance_trips':<22}"
        f"{expected_trips:>12}"
        f"{actual_trips:>12}"
        f"{trip_status:>12}"
    )

    if trip_status != "OK":
        problems.append(
            (
                "ambulance_trips",
                expected_trips,
                actual_trips,
            )
        )

    print()

    if problems:
        print(
            "RESULT: BENCHMARK DATASET VERIFICATION FAILED"
        )
        raise SystemExit(1)

    print(
        "RESULT: MANIFEST MATCHES DATABASE"
    )