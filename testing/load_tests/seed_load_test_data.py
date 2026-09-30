from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app import create_app
from app.core.auth.user.models.user_device_model import (
    UserDevice,
)
from app.core.auth.user.services.user_service import (
    get_user_by_email,
)
from app.core.enums.ambulance_enums import (
    EquipmentLevel,
    TripStatus,
    TripType,
    VehicleStatus,
)
from app.core.enums.appointment_enums import (
    AppointmentStatus,
    AppointmentType,
)
from app.core.enums.billing_enums import (
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
)
from app.core.enums.chat_enums import (
    ConversationStatus,
    ConversationType,
    MessagePriority,
    MessageStatus,
    MessageType,
    ParticipantRole,
    ParticipantStatus,
)
from app.core.enums.consultation_enums import (
    ConsultationStatus,
    ConsultationType,
)
from app.core.enums.inventory_enums import (
    InventoryCategory,
    StockMovementDirection,
    StockMovementType,
)
from app.core.enums.lab_enums import (
    LabOrderStatus,
    LabResultFlag,
    SampleType,
)
from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.core.enums.patient_enums import (
    BloodType,
    Gender,
)
from app.core.enums.pharmacy_enums import (
    DrugCategory,
)
from app.core.enums.prescription_enums import (
    PrescriptionStatus,
)
from app.core.enums.reports_enums import (
    ReportFormat,
    ReportType,
)
from app.core.enums.role_enums import Role
from app.core.enums.staff_enums import StaffStatus
from app.core.enums.ward_enums import (
    BedStatus,
    WardType,
)
from app.extensions import db
from app.modules.ambulance.models.ambulance_model import (
    AmbulanceTrip,
    AmbulanceVehicle,
)
from app.modules.appointment.models.appointment_model import (
    Appointment,
)
from app.modules.billing.models.billing_model import (
    Invoice,
    InvoiceItem,
    Payment,
)
from app.modules.chat.models.conversation_model import (
    Conversation,
)
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_model import (
    Message,
)
from app.modules.clinic.models.clinic_model import (
    Clinic,
)
from app.modules.consultation.models.consultation_model import (
    Consultation,
)
from app.modules.inventory.models.inventory_model import (
    InventoryBatch,
    InventoryItem,
    StockMovement,
)
from app.modules.lab.models.lab_model import (
    LabOrder,
    LabOrderItem,
    LabTest,
)
from app.modules.patient.models.patient_model import (
    Patient,
)
from app.modules.pharmacy.models.pharmacy_model import (
    Drug,
    DrugBatch,
)
from app.modules.prescription.models.prescription_model import (
    Prescription,
    PrescriptionItem,
)
from app.modules.reports.models.reports_model import (
    GeneratedReport,
)
from app.modules.staff.models.staff_model import (
    Staff,
)
from app.modules.ward.models.ward_model import (
    Bed,
    Ward,
)


LOAD_TEST_EMAIL = "loadtest@clinicload.com"
LOAD_TEST_PASSWORD = "LoadTestPassword123!"
LOAD_TEST_CLINIC_NAME = "Clinic Load Test"
LOAD_TEST_PATIENT_EMAIL = "loadtest-patient@clinicload.com"

AI_CREDITS = 100_000

BENCHMARK_VERSION = 1
BENCHMARK_PREFIX = "BENCHMARK"
BENCHMARK_EMAIL_DOMAIN = "example.com"
DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "load_tests"
    / "benchmark_dataset.json"
)

SEED_BASE_TIME = datetime(
    2026,
    1,
    1,
    8,
    0,
    0,
)

STAFF_BLUEPRINT = (
    ("Doctor", "001", Role.DOCTOR, "General Medicine"),
    ("Doctor", "002", Role.DOCTOR, "Cardiology"),
    ("Doctor", "003", Role.DOCTOR, "Pediatrics"),
    ("Doctor", "004", Role.DOCTOR, "Internal Medicine"),
    ("Nurse", "001", Role.NURSE, "Nursing"),
    ("Nurse", "002", Role.NURSE, "Nursing"),
    ("Pharmacist", "001", Role.PHARMACIST, "Pharmacy"),
    (
        "Lab",
        "001",
        Role.LAB_TECHNICIAN,
        "Laboratory",
    ),
    (
        "Accountant",
        "001",
        Role.ACCOUNTANT,
        "Finance",
    ),
    (
        "Reception",
        "001",
        Role.RECEPTIONIST,
        "Front Desk",
    ),
    ("Paramedic", "001", Role.PARAMEDIC, "Emergency"),
    ("Driver", "001", Role.DRIVER, "Transport"),
)


@dataclass(frozen=True)
class BenchmarkConfig:
    staff: int = 12
    patients: int = 500
    appointments: int = 1000
    consultations: int = 300
    lab_tests: int = 12
    lab_orders: int = 300
    drugs: int = 12
    prescriptions: int = 300
    inventory_items: int = 20
    wards: int = 2
    beds_per_ward: int = 10
    ambulances: int = 2
    ambulance_trips: int = 50
    invoices: int = 500
    notifications: int = 1000
    conversations: int = 50
    messages: int = 500
    reports: int = 100
    user_devices: int = 10
    ai_credits: int = AI_CREDITS


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _benchmark_datetime(offset_minutes: int = 0):
    return (
        SEED_BASE_TIME
        + timedelta(
            minutes=offset_minutes
        )
    )


def _benchmark_date(offset_days: int = 0):
    return (
        SEED_BASE_TIME.date()
        + timedelta(
            days=offset_days
        )
    )


def _validate_config(
    config: BenchmarkConfig,
) -> None:
    for field_name, value in asdict(
        config
    ).items():
        if value < 0:
            raise ValueError(
                f"{field_name} cannot be negative"
            )

    if config.beds_per_ward < 0:
        raise ValueError(
            "beds_per_ward cannot be negative"
        )


def get_or_create_clinic():
    clinic = db.session.execute(
        select(Clinic)
        .where(
            Clinic.name
            == LOAD_TEST_CLINIC_NAME
        )
        .limit(1)
    ).scalar_one_or_none()

    if clinic is not None:
        return clinic

    from app.modules.clinic.services.clinic_service import (
        create_clinic,
    )

    return create_clinic(
        name=LOAD_TEST_CLINIC_NAME,
        city="Asaba",
        country="Nigeria",
        timezone="Africa/Lagos",
    )


def get_or_create_control_user(
    clinic_id: int,
):
    user = get_user_by_email(
        LOAD_TEST_EMAIL
    )

    if user is not None:
        if user.clinic_id != clinic_id:
            raise RuntimeError(
                "Existing load-test control user belongs "
                f"to clinic {user.clinic_id}, expected {clinic_id}"
            )

        if user.role != Role.ADMIN:
            raise RuntimeError(
                "Existing load-test control user has role "
                f"{user.role.value}, expected admin"
            )

        return user

    from app.core.auth.user.services.user_service import (
        register_user,
    )

    return register_user(
        email=LOAD_TEST_EMAIL,
        password=LOAD_TEST_PASSWORD,
        role=Role.ADMIN,
        clinic_id=clinic_id,
    )


def get_or_create_control_patient(
    clinic_id: int,
    actor_id: int,
):
    patient = db.session.execute(
        select(Patient)
        .where(
            Patient.clinic_id == clinic_id,
            Patient.email
            == LOAD_TEST_PATIENT_EMAIL,
        )
        .limit(1)
    ).scalar_one_or_none()

    if patient is not None:
        return patient

    from app.modules.patient.services.patient_service import (
        create_patient,
    )

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


def seed_user_devices(
    user,
    count: int,
):
    count = max(0, count)

    existing = db.session.execute(
        select(UserDevice)
        .where(
            UserDevice.user_id == user.id,
            UserDevice.device_token.like(
                f"{BENCHMARK_PREFIX}-DEVICE-%"
            ),
        )
        .order_by(
            UserDevice.device_token.asc(),
            UserDevice.id.asc(),
        )
    ).scalars().all()

    by_token = {
        device.device_token: device
        for device in existing
    }

    devices = []

    platforms = (
        "android",
        "ios",
        "web",
    )

    for index in range(count):
        sequence = index + 1

        token = (
            f"{BENCHMARK_PREFIX}"
            f"-DEVICE-{sequence:04d}"
        )

        device = by_token.get(token)

        if device is None:
            created_at = _benchmark_datetime(
                index
            )

            device = UserDevice(
                user_id=user.id,
                device_token=token,
                device_name=(
                    f"Benchmark Device "
                    f"{sequence:02d}"
                ),
                platform=platforms[
                    index % len(platforms)
                ],
                is_active=(
                    index % 5 != 0
                ),
                last_seen_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )

            db.session.add(device)

        devices.append(device)

    db.session.flush()

    return devices


def ensure_ai_credits(
    clinic: Clinic,
):
    if clinic.ai_credits >= AI_CREDITS:
        return clinic

    from app.modules.clinic.services.clinic_service import (
        add_ai_credits,
    )

    return add_ai_credits(
        clinic_id=clinic.id,
        amount=AI_CREDITS
        - clinic.ai_credits,
    )


def _benchmark_user_email(
    index: int,
) -> str:
    return (
        f"{BENCHMARK_PREFIX.lower()}"
        f"-staff-{index:04d}@"
        f"{BENCHMARK_EMAIL_DOMAIN}"
    )


def _benchmark_patient_email(
    index: int,
) -> str:
    return (
        f"{BENCHMARK_PREFIX.lower()}"
        f"-patient-{index:06d}@"
        f"{BENCHMARK_EMAIL_DOMAIN}"
    )


def _get_existing_by_key(
    model,
    *,
    clinic_id: int,
    field,
    prefix: str,
):
    rows = db.session.execute(
        select(model)
        .where(
            model.clinic_id == clinic_id,
            field.like(f"{prefix}%"),
        )
    ).scalars().all()

    return rows


def seed_staff(
    clinic: Clinic,
    count: int,
):
    count = min(
        count,
        len(STAFF_BLUEPRINT),
    )

    users = []
    staff_rows = []

    User = __import__(
        "app.core.auth.user.models.user_model",
        fromlist=["User"],
    ).User

    existing_users = {
        user.email: user
        for user in db.session.execute(
            select(User).where(
                User.email.like(
                    f"{BENCHMARK_PREFIX.lower()}-staff-%"
                )
            )
        ).scalars()
    }

    existing_staff_rows = db.session.execute(
        select(Staff).where(
            Staff.clinic_id == clinic.id,
            Staff.email.like(
                f"{BENCHMARK_PREFIX.lower()}-%"
            ),
        )
    ).scalars().all()

    existing_staff_by_email = {
        staff.email: staff
        for staff in existing_staff_rows
        if staff.email
    }

    existing_staff_by_user_id = {
        staff.user_id: staff
        for staff in existing_staff_rows
        if staff.user_id is not None
    }

    for index in range(1, count + 1):
        display_name, code, role, specialty = (
            STAFF_BLUEPRINT[index - 1]
        )

        email = _benchmark_user_email(
            index
        )

        user = existing_users.get(
            email
        )

        if user is None:
            user = User(
                email=email,
                role=role,
                clinic_id=clinic.id,
                is_active=True,
                token_version=0,
            )
            user.set_password(
                f"BenchmarkPassword{index:04d}!"
            )
            db.session.add(user)
            db.session.flush()

        users.append(user)

        staff = existing_staff_by_user_id.get(
            user.id
        )

        if staff is None:
            staff = existing_staff_by_email.get(
                email
            )

        if staff is None:
            staff = Staff(
                clinic_id=clinic.id,
                user_id=user.id,
                first_name=display_name,
                last_name=f"Benchmark{code}",
                specialty=specialty,
                phone=f"0810000{index:04d}",
                email=email,
                status=StaffStatus.ACTIVE,
                hired_at=date(
                    2025,
                    1,
                    1,
                ),
            )
            db.session.add(staff)
            db.session.flush()

            existing_staff_by_user_id[
                user.id
            ] = staff

            existing_staff_by_email[
                email
            ] = staff
        else:
            staff.clinic_id = clinic.id
            staff.user_id = user.id
            staff.first_name = display_name
            staff.last_name = (
                f"Benchmark{code}"
            )
            staff.specialty = specialty
            staff.phone = (
                f"0810000{index:04d}"
            )
            staff.email = email
            staff.status = StaffStatus.ACTIVE
            staff.hired_at = date(
                2025,
                1,
                1,
            )

            existing_staff_by_user_id[
                user.id
            ] = staff

            existing_staff_by_email[
                email
            ] = staff

        staff_rows.append(staff)

    db.session.flush()

    return users, staff_rows


def seed_patients(
    clinic: Clinic,
    count: int,
):
    existing = db.session.execute(
        select(Patient).where(
            Patient.clinic_id == clinic.id,
            Patient.patient_number.like(
                f"{BENCHMARK_PREFIX}-PT-%"
            ),
        )
        .order_by(
            Patient.patient_number.asc(),
            Patient.id.asc(),
        )
    ).scalars().all()

    by_patient_number = {
        patient.patient_number: patient
        for patient in existing
        if patient.patient_number
    }

    patients = []

    for index in range(1, count + 1):
        email = _benchmark_patient_email(
            index
        )

        patient_number = (
            f"{BENCHMARK_PREFIX}"
            f"-PT-{index:08d}"
        )

        patient = by_patient_number.get(
            patient_number
        )

        if patient is None:
            patient = Patient(
                clinic_id=clinic.id,
                first_name="Benchmark",
                last_name=(
                    f"Patient{index:06d}"
                ),
                date_of_birth=date(
                    1980 + (index % 30),
                    1 + (index % 12),
                    1 + (index % 25),
                ),
                gender=(
                    Gender.MALE
                    if index % 2
                    else Gender.FEMALE
                ),
                blood_type=BloodType.UNKNOWN,
                phone=(
                    f"0820000{index:06d}"
                ),
                email=email,
                address=(
                    f"Benchmark Avenue "
                    f"{index:06d}"
                ),
                allergies="None reported",
                chronic_conditions=(
                    "None reported"
                ),
                patient_number=(
                    patient_number
                ),
                is_active=True,
            )

            db.session.add(patient)
            db.session.flush()

        else:
            patient.clinic_id = clinic.id
            patient.first_name = "Benchmark"
            patient.last_name = (
                f"Patient{index:06d}"
            )
            patient.date_of_birth = date(
                1980 + (index % 30),
                1 + (index % 12),
                1 + (index % 25),
            )
            patient.gender = (
                Gender.MALE
                if index % 2
                else Gender.FEMALE
            )
            patient.blood_type = (
                BloodType.UNKNOWN
            )
            patient.phone = (
                f"0820000{index:06d}"
            )
            patient.email = email
            patient.address = (
                f"Benchmark Avenue "
                f"{index:06d}"
            )
            patient.allergies = (
                "None reported"
            )
            patient.chronic_conditions = (
                "None reported"
            )
            patient.is_active = True

        patients.append(patient)

        by_patient_number[
            patient_number
        ] = patient

    db.session.flush()

    return patients


def seed_appointments(
    clinic: Clinic,
    patients: list[Patient],
    staff_rows: list[Staff],
    count: int,
):
    doctors = [
        staff
        for staff in staff_rows
        if getattr(
            staff.user,
            "role",
            None,
        )
        == Role.DOCTOR
    ]

    if not doctors:
        raise RuntimeError(
            "Benchmark dataset requires at least one doctor"
        )

    existing = db.session.execute(
        select(Appointment)
        .where(
            Appointment.clinic_id == clinic.id,
            Appointment.google_calendar_event_id.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            Appointment.google_calendar_event_id.asc(),
            Appointment.id.asc(),
        )
    ).scalars().all()

    by_key = {
        appointment.google_calendar_event_id:
        appointment
        for appointment in existing
    }

    appointments = []

    for index in range(count):
        sequence = index + 1
        key = (
            f"{BENCHMARK_PREFIX}"
            f"-APPT-{sequence:08d}"
        )

        appointment = by_key.get(key)

        if appointment is None:
            start = (
                SEED_BASE_TIME
                + timedelta(
                    days=index // 20,
                    minutes=(index % 20)
                    * 30,
                )
            )
            end = start + timedelta(
                minutes=30
            )

            if index % 10 == 0:
                status = AppointmentStatus.COMPLETED
            elif index % 3 == 0:
                status = AppointmentStatus.CONFIRMED
            else:
                status = AppointmentStatus.SCHEDULED

            appointment = Appointment(
                clinic_id=clinic.id,
                patient_id=(
                    patients[
                        index % len(patients)
                    ].id
                ),
                staff_id=(
                    doctors[
                        index % len(doctors)
                    ].id
                ),
                scheduled_start=start,
                scheduled_end=end,
                status=status,
                appointment_type=(
                    AppointmentType.IN_PERSON
                    if index % 5
                    else AppointmentType.FOLLOW_UP
                ),
                reason=(
                    f"{BENCHMARK_PREFIX}"
                    f" appointment "
                    f"{sequence:08d}"
                ),
                notes=(
                    "Deterministic benchmark "
                    "appointment"
                ),
                google_calendar_event_id=key,
                reminder_sent=index % 2 == 0,
            )
            db.session.add(appointment)
            appointments.append(appointment)
        else:
            appointments.append(appointment)

    db.session.flush()

    return appointments


def seed_consultations(
    clinic: Clinic,
    patients: list[Patient],
    staff_rows: list[Staff],
    appointments: list[Appointment],
    count: int,
):
    doctors = [
        staff
        for staff in staff_rows
        if getattr(
            staff.user,
            "role",
            None,
        )
        == Role.DOCTOR
    ]

    existing = db.session.execute(
        select(Consultation)
        .where(
            Consultation.clinic_id == clinic.id,
            Consultation.notes.like(
                f"{BENCHMARK_PREFIX}:%"
            ),
        )
        .order_by(
            Consultation.notes.asc(),
            Consultation.id.asc(),
        )
    ).scalars().all()

    by_key = {
        consultation.notes: consultation
        for consultation in existing
    }

    consultations = []

    eligible_appointments = [
        appointment
        for appointment in appointments
        if appointment.status
        in {
            AppointmentStatus.COMPLETED,
            AppointmentStatus.CONFIRMED,
        }
    ]

    for index in range(
        min(
            count,
            len(eligible_appointments),
        )
    ):
        appointment = eligible_appointments[
            index
        ]

        key = (
            f"{BENCHMARK_PREFIX}"
            f":CONSULT-{index + 1:08d}"
        )

        consultation = by_key.get(key)

        if consultation is None:
            started = (
                appointment.scheduled_start
                + timedelta(minutes=5)
            )
            ended = (
                started
                + timedelta(minutes=25)
            )

            consultation = Consultation(
                clinic_id=clinic.id,
                patient_id=appointment.patient_id,
                staff_id=appointment.staff_id,
                appointment_id=appointment.id,
                icd10_code="Z00.00",
                consultation_type=(
                    ConsultationType.GENERAL
                    if index % 4
                    else ConsultationType.FOLLOW_UP
                ),
                status=ConsultationStatus.COMPLETED,
                chief_complaint=(
                    "Benchmark consultation"
                ),
                symptoms=(
                    "Synthetic benchmark symptoms"
                ),
                diagnosis=(
                    "Synthetic benchmark diagnosis"
                ),
                treatment_plan=(
                    "Synthetic benchmark treatment plan"
                ),
                notes=key,
                started_at=started,
                ended_at=ended,
                created_at=started,
                updated_at=ended,
            )
            db.session.add(
                consultation
            )
            consultations.append(
                consultation
            )
        else:
            consultations.append(
                consultation
            )

    db.session.flush()

    return consultations


def seed_lab_tests(
    clinic: Clinic,
    count: int,
):
    existing = db.session.execute(
        select(LabTest)
        .where(
            LabTest.clinic_id == clinic.id,
            LabTest.code.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            LabTest.code.asc(),
            LabTest.id.asc(),
        )
    ).scalars().all()

    by_code = {
        test.code: test
        for test in existing
    }

    tests = []

    for index in range(count):
        sequence = index + 1
        code = (
            f"{BENCHMARK_PREFIX}"
            f"-LAB-{sequence:04d}"
        )

        test = by_code.get(code)

        if test is None:
            test = LabTest(
                clinic_id=clinic.id,
                loinc_code=None,
                name=(
                    f"Benchmark Lab Test "
                    f"{sequence:02d}"
                ),
                code=code,
                sample_type=(
                    SampleType.BLOOD
                    if index % 2 == 0
                    else SampleType.URINE
                ),
                reference_range="Normal benchmark range",
                unit="units",
                price=Decimal("25.00")
                + Decimal(index),
                critical_low=Decimal("1.000"),
                critical_high=Decimal("999.000"),
                is_active=True,
            )
            db.session.add(test)
            tests.append(test)
        else:
            tests.append(test)

    db.session.flush()

    return tests


def seed_lab_orders(
    clinic: Clinic,
    patients: list[Patient],
    staff_rows: list[Staff],
    consultations: list[Consultation],
    tests: list[LabTest],
    count: int,
):
    ordering_staff = staff_rows[0]
    lab_staff = next(
        (
            staff
            for staff in staff_rows
            if getattr(
                staff.user,
                "role",
                None,
            )
            == Role.LAB_TECHNICIAN
        ),
        staff_rows[0],
    )

    existing = db.session.execute(
        select(LabOrder)
        .where(
            LabOrder.clinic_id == clinic.id,
            LabOrder.qr_code.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            LabOrder.qr_code.asc(),
            LabOrder.id.asc(),
        )
    ).scalars().all()

    by_key = {
        order.qr_code: order
        for order in existing
    }

    orders = []

    for index in range(count):
        sequence = index + 1
        key = (
            f"{BENCHMARK_PREFIX}"
            f"-LABORDER-{sequence:08d}"
        )

        order = by_key.get(key)

        if order is None:
            created_at = (
                SEED_BASE_TIME
                + timedelta(
                    days=index // 30,
                    minutes=index % 30,
                )
            )

            completed = (
                index % 2 == 0
            )

            collected_at = (
                created_at
                + timedelta(minutes=10)
                if completed
                else None
            )

            processed_at = (
                created_at
                + timedelta(minutes=20)
                if completed
                else None
            )

            verified_at = (
                created_at
                + timedelta(minutes=30)
                if completed
                else None
            )

            completed_at = (
                created_at
                + timedelta(minutes=35)
                if completed
                else None
            )

            consultation_id = (
                consultations[
                    index
                    % len(consultations)
                ].id
                if consultations
                else None
            )

            order = LabOrder(
                clinic_id=clinic.id,
                patient_id=patients[
                    index % len(patients)
                ].id,
                consultation_id=consultation_id,
                ordered_by_id=ordering_staff.id,
                collected_by_id=(
                    lab_staff.id
                    if completed
                    else None
                ),
                processed_by_id=(
                    lab_staff.id
                    if completed
                    else None
                ),
                verified_by_id=(
                    lab_staff.id
                    if completed
                    else None
                ),
                status=(
                    LabOrderStatus.COMPLETED
                    if completed
                    else LabOrderStatus.ORDERED
                ),
                qr_code=key,
                sample_collected_at=collected_at,
                processed_at=processed_at,
                verified_at=verified_at,
                equipment_reference_id=(
                    f"{BENCHMARK_PREFIX}"
                    f"-EQUIPMENT-{index % 5:02d}"
                ),
                created_at=created_at,
                updated_at=(
                    completed_at
                    or created_at
                ),
                completed_at=completed_at,
            )

            db.session.add(order)
            db.session.flush()

            item = LabOrderItem(
                order_id=order.id,
                test_id=tests[
                    index % len(tests)
                ].id,
                result_value=(
                    "Normal"
                    if completed
                    else None
                ),
                flag=(
                    LabResultFlag.NORMAL
                    if completed
                    else None
                ),
                result_notes=(
                    "Synthetic benchmark result"
                    if completed
                    else None
                ),
                result_file_url=None,
                resulted_at=completed_at,
            )

            db.session.add(item)
            orders.append(order)
        else:
            orders.append(order)

    db.session.flush()

    return orders


def seed_drugs(
    clinic: Clinic,
    count: int,
):
    existing = db.session.execute(
        select(Drug)
        .where(
            Drug.clinic_id == clinic.id,
            Drug.name.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            Drug.name.asc(),
            Drug.id.asc(),
        )
    ).scalars().all()

    by_name = {
        drug.name: drug
        for drug in existing
    }

    drugs = []

    for index in range(count):
        sequence = index + 1
        name = (
            f"{BENCHMARK_PREFIX}"
            f"-Drug-{sequence:04d}"
        )

        drug = by_name.get(name)

        if drug is None:
            drug = Drug(
                clinic_id=clinic.id,
                name=name,
                generic_name=(
                    f"Benchmark Generic "
                    f"{sequence:04d}"
                ),
                category=(
                    DrugCategory.ANALGESIC
                    if index % 2 == 0
                    else DrugCategory.ANTIBIOTIC
                ),
                manufacturer="Benchmark Pharma",
                dosage_form="tablet",
                strength="500 mg",
                unit_price=Decimal("10.00")
                + Decimal(index),
                is_controlled=False,
                is_active=True,
            )
            db.session.add(drug)
            drugs.append(drug)
        else:
            drugs.append(drug)

    db.session.flush()

    existing_batches = db.session.execute(
        select(DrugBatch)
        .where(
            DrugBatch.clinic_id == clinic.id,
            DrugBatch.batch_number.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            DrugBatch.batch_number.asc(),
            DrugBatch.id.asc(),
        )
    ).scalars().all()

    batch_keys = {
        batch.batch_number
        for batch in existing_batches
    }

    for index, drug in enumerate(drugs):
        batch_number = (
            f"{BENCHMARK_PREFIX}"
            f"-BATCH-{index + 1:04d}"
        )

        if batch_number in batch_keys:
            continue

        db.session.add(
            DrugBatch(
                clinic_id=clinic.id,
                drug_id=drug.id,
                batch_number=batch_number,
                quantity_on_hand=1000,
                reorder_level=100,
                expiry_date=date(
                    2028,
                    12,
                    31,
                ),
                received_at=(
                    SEED_BASE_TIME
                ),
            )
        )

    db.session.flush()

    return drugs


def seed_prescriptions(
    clinic: Clinic,
    patients: list[Patient],
    staff_rows: list[Staff],
    consultations: list[Consultation],
    drugs: list[Drug],
    count: int,
):
    prescriber = next(
        (
            staff
            for staff in staff_rows
            if getattr(
                staff.user,
                "role",
                None,
            )
            == Role.DOCTOR
        ),
        staff_rows[0],
    )

    existing = db.session.execute(
        select(Prescription)
        .where(
            Prescription.clinic_id == clinic.id,
            Prescription.notes.like(
                f"{BENCHMARK_PREFIX}:%"
            ),
        )
        .order_by(
            Prescription.notes.asc(),
            Prescription.id.asc(),
        )
    ).scalars().all()

    by_key = {
        prescription.notes: prescription
        for prescription in existing
    }

    prescriptions = []

    for index in range(count):
        key = (
            f"{BENCHMARK_PREFIX}"
            f":RX-{index + 1:08d}"
        )

        prescription = by_key.get(
            key
        )

        if prescription is None:
            issued_at = (
                _benchmark_datetime(
                    index * 7
                )
            )

            prescription = Prescription(
                clinic_id=clinic.id,
                patient_id=patients[
                    index % len(patients)
                ].id,
                consultation_id=(
                    consultations[
                        index
                        % len(consultations)
                    ].id
                    if consultations
                    else None
                ),
                prescribed_by_id=prescriber.id,
                status=PrescriptionStatus.ACTIVE,
                notes=key,
                issued_at=issued_at,
                expires_at=(
                    issued_at
                    + timedelta(days=30)
                ),
                created_at=issued_at,
                updated_at=issued_at,
            )

            db.session.add(
                prescription
            )
            db.session.flush()

            drug = drugs[
                index % len(drugs)
            ]

            db.session.add(
                PrescriptionItem(
                    prescription_id=prescription.id,
                    drug_id=drug.id,
                    dosage="1 tablet",
                    frequency="twice daily",
                    duration="7 days",
                    quantity=14,
                    instructions=(
                        "Synthetic benchmark instructions"
                    ),
                )
            )

            prescriptions.append(
                prescription
            )
        else:
            prescriptions.append(
                prescription
            )

    db.session.flush()

    return prescriptions


def seed_inventory(
    clinic: Clinic,
    staff_rows: list[Staff],
    count: int,
):
    actor = staff_rows[0]

    existing = db.session.execute(
        select(InventoryItem)
        .where(
            InventoryItem.clinic_id == clinic.id,
            InventoryItem.name.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            InventoryItem.name.asc(),
            InventoryItem.id.asc(),
        )
    ).scalars().all()

    by_name = {
        item.name: item
        for item in existing
    }

    items = []

    for index in range(count):
        sequence = index + 1
        name = (
            f"{BENCHMARK_PREFIX}"
            f"-Inventory-{sequence:04d}"
        )

        item = by_name.get(name)

        if item is None:
            item = InventoryItem(
                clinic_id=clinic.id,
                name=name,
                category=(
                    InventoryCategory.MEDICAL_SUPPLY
                ),
                sku=(
                    f"{BENCHMARK_PREFIX}"
                    f"-SKU-{sequence:04d}"
                ),
                barcode=(
                    f"{BENCHMARK_PREFIX}"
                    f"-BAR-{sequence:04d}"
                ),
                unit="units",
                quantity_on_hand=1000,
                reorder_level=100,
                is_active=True,
            )
            db.session.add(item)
            db.session.flush()

            batch = InventoryBatch(
                item_id=item.id,
                batch_number=(
                    f"{BENCHMARK_PREFIX}"
                    f"-INV-BATCH-{sequence:04d}"
                ),
                quantity_on_hand=1000,
                unit_cost=Decimal("5.00"),
                expiry_date=date(
                    2028,
                    12,
                    31,
                ),
                received_at=SEED_BASE_TIME,
                is_active=True,
            )

            db.session.add(batch)
            db.session.flush()

            db.session.add(
                StockMovement(
                    item_id=item.id,
                    batch_id=batch.id,
                    movement_type=(
                        StockMovementType.RESTOCK
                    ),
                    direction=(
                        StockMovementDirection.IN
                    ),
                    quantity=1000,
                    reason=(
                        f"{BENCHMARK_PREFIX}"
                        " initial stock"
                    ),
                    performed_by_id=actor.id,
                    reference_type="benchmark",
                    reference_id=sequence,
                    created_at=SEED_BASE_TIME,
                )
            )

            items.append(item)
        else:
            items.append(item)

    db.session.flush()

    return items


def seed_wards(
    clinic: Clinic,
    count: int,
    beds_per_ward: int,
):
    existing = db.session.execute(
        select(Ward)
        .where(
            Ward.clinic_id == clinic.id,
            Ward.name.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            Ward.name.asc(),
            Ward.id.asc(),
        )
    ).scalars().all()

    by_name = {
        ward.name: ward
        for ward in existing
    }

    wards = []

    for index in range(count):
        sequence = index + 1
        name = (
            f"{BENCHMARK_PREFIX}"
            f"-Ward-{sequence:02d}"
        )

        ward = by_name.get(name)

        if ward is None:
            ward = Ward(
                clinic_id=clinic.id,
                name=name,
                ward_type=(
                    WardType.GENERAL
                    if index % 2 == 0
                    else WardType.ICU
                ),
                capacity=beds_per_ward,
                created_at=SEED_BASE_TIME,
                updated_at=SEED_BASE_TIME,
            )
            db.session.add(ward)
            db.session.flush()

            for bed_index in range(
                beds_per_ward
            ):
                db.session.add(
                    Bed(
                        ward_id=ward.id,
                        bed_number=(
                            f"{BENCHMARK_PREFIX}"
                            f"-{sequence:02d}-"
                            f"{bed_index + 1:03d}"
                        ),
                        status=BedStatus.AVAILABLE,
                        created_at=SEED_BASE_TIME,
                        updated_at=SEED_BASE_TIME,
                    )
                )

        wards.append(ward)

    db.session.flush()

    return wards


def seed_ambulances(
    clinic: Clinic,
    staff_rows: list[Staff],
    patients: list[Patient],
    count: int,
    trip_count: int,
):
    driver = next(
        (
            staff
            for staff in staff_rows
            if getattr(
                staff.user,
                "role",
                None,
            )
            == Role.DRIVER
        ),
        staff_rows[0],
    )

    paramedic = next(
        (
            staff
            for staff in staff_rows
            if getattr(
                staff.user,
                "role",
                None,
            )
            == Role.PARAMEDIC
        ),
        next(
            (
                staff
                for staff in staff_rows
                if staff.id != driver.id
            ),
            staff_rows[0],
        ),
    )

    existing_vehicles = db.session.execute(
        select(AmbulanceVehicle)
        .where(
            AmbulanceVehicle.clinic_id
            == clinic.id,
            AmbulanceVehicle.plate_number.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            AmbulanceVehicle.plate_number.asc(),
            AmbulanceVehicle.id.asc(),
        )
    ).scalars().all()

    vehicles_by_plate = {
        vehicle.plate_number: vehicle
        for vehicle in existing_vehicles
    }

    vehicles = []

    for index in range(count):
        plate = (
            f"{BENCHMARK_PREFIX}"
            f"-AMB-{index + 1:02d}"
        )

        vehicle = vehicles_by_plate.get(
            plate
        )

        if vehicle is None:
            vehicle = AmbulanceVehicle(
                clinic_id=clinic.id,
                plate_number=plate,
                equipment_level=(
                    EquipmentLevel.BLS
                ),
                capacity=2,
                status=VehicleStatus.AVAILABLE,
                last_service_date=date(
                    2025,
                    6,
                    1,
                ),
            )
            db.session.add(vehicle)
            db.session.flush()

        vehicles.append(vehicle)

    existing_trips = db.session.execute(
        select(AmbulanceTrip)
        .where(
            AmbulanceTrip.clinic_id
            == clinic.id,
            AmbulanceTrip.notes.like(
                f"{BENCHMARK_PREFIX}:%"
            ),
        )
        .order_by(
            AmbulanceTrip.notes.asc(),
            AmbulanceTrip.id.asc(),
        )
    ).scalars().all()

    trip_keys = {
        trip.notes
        for trip in existing_trips
    }

    for index in range(trip_count):
        key = (
            f"{BENCHMARK_PREFIX}"
            f":AMBTRIP-{index + 1:08d}"
        )

        if key in trip_keys:
            continue

        requested_at = (
            SEED_BASE_TIME
            + timedelta(
                days=index // 20,
                minutes=index % 20,
            )
        )

        dispatched_at = (
            requested_at
            + timedelta(minutes=5)
        )

        pickup_at = (
            requested_at
            + timedelta(minutes=15)
        )

        completed_at = (
            requested_at
            + timedelta(minutes=45)
        )

        db.session.add(
            AmbulanceTrip(
                clinic_id=clinic.id,
                vehicle_id=vehicles[
                    index % len(vehicles)
                ].id,
                patient_id=patients[
                    index % len(patients)
                ].id,
                driver_id=driver.id,
                paramedic_id=paramedic.id,
                trip_type=(
                    TripType.NON_EMERGENCY
                ),
                status=TripStatus.COMPLETED,
                pickup_address=(
                    "Benchmark Pickup"
                ),
                destination_address=(
                    "Benchmark Clinic"
                ),
                created_at=requested_at,
                updated_at=completed_at,
                requested_at=requested_at,
                dispatched_at=dispatched_at,
                pickup_at=pickup_at,
                completed_at=completed_at,
                notes=key,
            )
        )

    db.session.flush()

    return vehicles


def seed_invoices(
    clinic: Clinic,
    patients: list[Patient],
    appointments: list[Appointment],
    count: int,
):
    existing = db.session.execute(
        select(Invoice)
        .where(
            Invoice.clinic_id == clinic.id,
            Invoice.invoice_number.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            Invoice.invoice_number.asc(),
            Invoice.id.asc(),
        )
    ).scalars().all()

    by_number = {
        invoice.invoice_number: invoice
        for invoice in existing
    }

    invoices = []

    for index in range(count):
        sequence = index + 1
        invoice_number = (
            f"{BENCHMARK_PREFIX}"
            f"-INV-{sequence:08d}"
        )

        invoice = by_number.get(
            invoice_number
        )

        if invoice is None:
            total = Decimal(
                "100.00"
            ) + Decimal(
                index % 10
            ) * Decimal("25.00")

            if index % 4 == 0:
                status = InvoiceStatus.PAID
                amount_paid = total
            elif index % 4 == 1:
                status = (
                    InvoiceStatus.PARTIALLY_PAID
                )
                amount_paid = (
                    total
                    * Decimal("0.40")
                )
            else:
                status = InvoiceStatus.ISSUED
                amount_paid = Decimal("0")

            appointment = (
                appointments[
                    index % len(appointments)
                ]
                if appointments
                else None
            )

            created_at = (
                SEED_BASE_TIME
                + timedelta(
                    days=index // 30,
                    minutes=index % 30,
                )
            )

            invoice = Invoice(
                clinic_id=clinic.id,
                patient_id=patients[
                    index % len(patients)
                ].id,
                appointment_id=(
                    appointment.id
                    if appointment
                    else None
                ),
                invoice_number=invoice_number,
                total_amount=total,
                amount_paid=amount_paid,
                status=status,
                due_date=(
                    created_at.date()
                    + timedelta(days=30)
                ),
                is_insurance_claim=(
                    index % 5 == 0
                ),
                insurance_provider=(
                    "Benchmark Health"
                    if index % 5 == 0
                    else None
                ),
                created_at=created_at,
                updated_at=created_at,
            )

            db.session.add(invoice)
            db.session.flush()

            db.session.add(
                InvoiceItem(
                    invoice_id=invoice.id,
                    description=(
                        f"{BENCHMARK_PREFIX}"
                        " consultation"
                    ),
                    quantity=1,
                    unit_price=total,
                    subtotal=total,
                )
            )

            if amount_paid > 0:
                db.session.add(
                    Payment(
                        invoice_id=invoice.id,
                        amount=amount_paid,
                        method=PaymentMethod.CASH,
                        status=(
                            PaymentStatus.SUCCESSFUL
                        ),
                        gateway=None,
                        reference=(
                            f"{BENCHMARK_PREFIX}"
                            f"-PAY-{sequence:08d}"
                        ),
                        gateway_transaction_id=None,
                        paid_at=created_at,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )

            invoices.append(invoice)
        else:
            invoices.append(invoice)

    db.session.flush()

    return invoices


def seed_notifications(
    clinic: Clinic,
    users: list,
    count: int,
):
    if not users:
        return []

    existing = db.session.execute(
        select(
            __import__(
                "app.core.notifications.models.notification_models",
                fromlist=["Notification"],
            ).Notification
        )
        .where(
            __import__(
                "app.core.notifications.models.notification_models",
                fromlist=["Notification"],
            ).Notification.clinic_id
            == clinic.id,
            __import__(
                "app.core.notifications.models.notification_models",
                fromlist=["Notification"],
            ).Notification.title.like(
                f"{BENCHMARK_PREFIX}:%"
            ),
        )
        .order_by(
            __import__(
                "app.core.notifications.models.notification_models",
                fromlist=["Notification"],
            ).Notification.title.asc()
        )
    ).scalars().all()

    Notification = __import__(
        "app.core.notifications.models.notification_models",
        fromlist=["Notification"],
    ).Notification

    by_title = {
        notification.title: notification
        for notification in existing
    }

    notifications = []

    for index in range(count):
        key = (
            f"{BENCHMARK_PREFIX}"
            f":NOTIFICATION-{index + 1:08d}"
        )

        notification = by_title.get(
            key
        )

        if notification is None:
            created_at = (
                SEED_BASE_TIME
                + timedelta(
                    minutes=index
                )
            )

            is_read = index % 3 == 0

            notification = Notification(
                clinic_id=clinic.id,
                user_id=users[
                    index % len(users)
                ].id,
                title=key,
                message=(
                    "Synthetic benchmark notification"
                ),
                notification_type=(
                    NotificationType.GENERAL
                ),
                priority=(
                    NotificationPriority.NORMAL
                ),
                channel=(
                    NotificationChannel.IN_APP
                ),
                status=(
                    NotificationStatus.READ
                    if is_read
                    else NotificationStatus.PENDING
                ),
                reference_type="benchmark",
                reference_id=index + 1,
                is_read=is_read,
                read_at=(
                    created_at
                    if is_read
                    else None
                ),
                created_at=created_at,
                updated_at=created_at,
                retry_count=0,
            )

            db.session.add(notification)
            notifications.append(
                notification
            )
        else:
            notifications.append(
                notification
            )

    db.session.flush()

    return notifications


def seed_chat(
    clinic: Clinic,
    users: list,
    conversations_count: int,
    messages_count: int,
):
    if len(users) < 2:
        return [], []

    existing_conversations = db.session.execute(
        select(Conversation)
        .where(
            Conversation.clinic_id == clinic.id,
            Conversation.title.like(
                f"{BENCHMARK_PREFIX}-%"
            ),
        )
        .order_by(
            Conversation.title.asc(),
            Conversation.id.asc(),
        )
    ).scalars().all()

    by_title = {
        conversation.title: conversation
        for conversation in existing_conversations
    }

    conversations = []

    for index in range(
        conversations_count
    ):
        title = (
            f"{BENCHMARK_PREFIX}"
            f"-Chat-{index + 1:04d}"
        )

        conversation = by_title.get(
            title
        )

        if conversation is None:
            creator = users[
                index % len(users)
            ]

            conversation = Conversation(
                clinic_id=clinic.id,
                conversation_type=(
                    ConversationType.GROUP
                ),
                status=ConversationStatus.ACTIVE,
                title=title,
                description=(
                    "Synthetic benchmark clinical team "
                    "conversation"
                ),
                created_by_id=creator.id,
                created_at=SEED_BASE_TIME,
                updated_at=SEED_BASE_TIME,
            )

            db.session.add(
                conversation
            )
            db.session.flush()

            member_indexes = {
                index % len(users),
                (index + 1) % len(users),
                (index + 2) % len(users),
                (index + 3) % len(users),
            }

            for member_index in sorted(
                member_indexes
            ):
                member = users[member_index]

                db.session.add(
                    ConversationParticipant(
                        clinic_id=clinic.id,
                        conversation_id=conversation.id,
                        user_id=member.id,
                        role=(
                            ParticipantRole.ADMIN
                            if member.id
                            == creator.id
                            else ParticipantRole.MEMBER
                        ),
                        status=(
                            ParticipantStatus.ACCEPTED
                        ),
                        joined_at=SEED_BASE_TIME,
                        created_at=SEED_BASE_TIME,
                        updated_at=SEED_BASE_TIME,
                    )
                )

        conversations.append(
            conversation
        )

    db.session.flush()

    existing_messages = db.session.execute(
        select(Message)
        .where(
            Message.clinic_id == clinic.id,
            Message.content.like(
                f"{BENCHMARK_PREFIX}:%"
            ),
        )
        .order_by(
            Message.content.asc(),
            Message.id.asc(),
        )
    ).scalars().all()

    by_content = {
        message.content: message
        for message in existing_messages
    }

    messages = []

    for index in range(
        messages_count
    ):
        key = (
            f"{BENCHMARK_PREFIX}"
            f":MESSAGE-{index + 1:08d}"
        )

        message = by_content.get(
            key
        )

        if message is None:
            conversation = conversations[
                index
                % len(conversations)
            ]

            sender = users[
                index
                % len(users)
            ]

            created_at = (
                SEED_BASE_TIME
                + timedelta(
                    minutes=index
                )
            )

            message = Message(
                clinic_id=clinic.id,
                conversation_id=conversation.id,
                sender_id=sender.id,
                message_type=MessageType.TEXT,
                content=key,
                status=MessageStatus.SENT,
                priority=MessagePriority.NORMAL,
                created_at=created_at,
                updated_at=created_at,
            )

            db.session.add(message)
            messages.append(message)
        else:
            messages.append(message)

    db.session.flush()

    for index, conversation in enumerate(
        conversations
    ):
        conversation_messages = [
            message
            for message in messages
            if message.conversation_id
            == conversation.id
        ]

        if conversation_messages:
            last_message = max(
                conversation_messages,
                key=lambda message: message.created_at,
            )

            conversation.last_message_at = (
                last_message.created_at
            )
            conversation.updated_at = (
                last_message.created_at
            )

    db.session.flush()

    return conversations, messages


def seed_reports(
    clinic: Clinic,
    staff_rows: list[Staff],
    count: int,
):
    if not staff_rows:
        return []

    existing = db.session.execute(
        select(GeneratedReport)
        .where(
            GeneratedReport.clinic_id
            == clinic.id,
            GeneratedReport.file_url.like(
                f"{BENCHMARK_PREFIX}:%"
            ),
        )
        .order_by(
            GeneratedReport.file_url.asc(),
            GeneratedReport.id.asc(),
        )
    ).scalars().all()

    by_key = {
        report.file_url: report
        for report in existing
    }

    report_types = list(
        ReportType
    )

    reports = []

    for index in range(count):
        key = (
            f"{BENCHMARK_PREFIX}"
            f":REPORT-{index + 1:08d}"
        )

        report = by_key.get(key)

        if report is None:
            report = GeneratedReport(
                clinic_id=clinic.id,
                generated_by_id=staff_rows[
                    index
                    % len(staff_rows)
                ].id,
                report_type=report_types[
                    index
                    % len(report_types)
                ],
                report_format=(
                    ReportFormat.JSON
                    if hasattr(
                        ReportFormat,
                        "JSON",
                    )
                    else ReportFormat.CSV
                ),
                filters={
                    "benchmark": True,
                    "dataset_version": (
                        BENCHMARK_VERSION
                    ),
                },
                file_url=key,
                created_at=_benchmark_datetime(
                    index
                ),
                updated_at=_benchmark_datetime(
                    index
                ),
            )

            db.session.add(report)
            reports.append(report)
        else:
            reports.append(report)

    db.session.flush()

    return reports


def build_manifest(
    *,
    config: BenchmarkConfig,
    clinic: Clinic,
    control_user,
    control_patient,
    user_devices: list[UserDevice],
    staff_rows: list[Staff],
    patients: list[Patient],
    appointments: list[Appointment],
    consultations: list[Consultation],
    lab_tests: list[LabTest],
    lab_orders: list[LabOrder],
    drugs: list[Drug],
    prescriptions: list[Prescription],
    inventory_items: list[InventoryItem],
    wards: list[Ward],
    ambulances: list[AmbulanceVehicle],
    invoices: list[Invoice],
    notifications: list,
    conversations: list[Conversation],
    messages: list[Message],
    reports: list[GeneratedReport],
):
    return {
        "dataset_version": BENCHMARK_VERSION,
        "dataset_name": "clinic_system_pro_benchmark",
        "seed_base_time": (
            SEED_BASE_TIME.isoformat()
        ),
        "clinic_id": clinic.id,
        "clinic_name": clinic.name,
        "control_user": {
            "id": control_user.id,
            "email": LOAD_TEST_EMAIL,
            "role": control_user.role.value,
        },
        "control_patient": {
            "id": control_patient.id,
            "email": LOAD_TEST_PATIENT_EMAIL,
        },
        "configured_counts": asdict(config),
        "actual_counts": {
            "staff": len(staff_rows),
            "patients": len(patients),
            "appointments": len(appointments),
            "consultations": len(consultations),
            "lab_tests": len(lab_tests),
            "lab_orders": len(lab_orders),
            "drugs": len(drugs),
            "prescriptions": len(prescriptions),
            "inventory_items": len(
                inventory_items
            ),
            "wards": len(wards),
            "beds": sum(
                len(ward.beds)
                for ward in wards
            ),
            "ambulances": len(ambulances),
            "invoices": len(invoices),
            "notifications": len(
                notifications
            ),
            "conversations": len(
                conversations
            ),
            "messages": len(
                messages
            ),
            "reports": len(
                reports
            ),
            "user_devices": len(
                user_devices
            ),
        },
        "benchmark_identity": {
            "prefix": BENCHMARK_PREFIX,
            "email_domain": (
                BENCHMARK_EMAIL_DOMAIN
            ),
        },
        "anchor_ids": {
            "staff_first": (
                staff_rows[0].id
                if staff_rows
                else None
            ),
            "staff_last": (
                staff_rows[-1].id
                if staff_rows
                else None
            ),
            "patient_first": (
                patients[0].id
                if patients
                else None
            ),
            "patient_last": (
                patients[-1].id
                if patients
                else None
            ),
            "appointment_first": (
                appointments[0].id
                if appointments
                else None
            ),
            "appointment_last": (
                appointments[-1].id
                if appointments
                else None
            ),
            "consultation_first": (
                consultations[0].id
                if consultations
                else None
            ),
            "consultation_last": (
                consultations[-1].id
                if consultations
                else None
            ),
            "lab_order_first": (
                lab_orders[0].id
                if lab_orders
                else None
            ),
            "lab_order_last": (
                lab_orders[-1].id
                if lab_orders
                else None
            ),
            "drug_first": (
                drugs[0].id
                if drugs
                else None
            ),
            "drug_last": (
                drugs[-1].id
                if drugs
                else None
            ),
            "prescription_first": (
                prescriptions[0].id
                if prescriptions
                else None
            ),
            "prescription_last": (
                prescriptions[-1].id
                if prescriptions
                else None
            ),
            "invoice_first": (
                invoices[0].id
                if invoices
                else None
            ),
            "invoice_last": (
                invoices[-1].id
                if invoices
                else None
            ),
        },
    }


def write_manifest(
    manifest: dict,
    path: Path,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def parse_args() -> tuple[BenchmarkConfig, Path]:
    parser = argparse.ArgumentParser(
        description=(
            "Seed the reproducible Clinic System Pro "
            "benchmark dataset."
        )
    )

    parser.add_argument(
        "--staff",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--patients",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--appointments",
        type=int,
        default=1000,
    )
    parser.add_argument(
        "--consultations",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--lab-tests",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--lab-orders",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--drugs",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--prescriptions",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--inventory-items",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--wards",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--beds-per-ward",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--ambulances",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--ambulance-trips",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--invoices",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--notifications",
        type=int,
        default=1000,
    )
    parser.add_argument(
        "--conversations",
        type=int,
        default=50,
    )
    parser.add_argument(
        "--messages",
        type=int,
        default=500,
    )
    parser.add_argument(
        "--reports",
        type=int,
        default=100,
    )
    parser.add_argument(
        "--user-devices",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--ai-credits",
        type=int,
        default=AI_CREDITS,
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )

    args = parser.parse_args()

    config = BenchmarkConfig(
        staff=args.staff,
        patients=args.patients,
        appointments=args.appointments,
        consultations=args.consultations,
        lab_tests=args.lab_tests,
        lab_orders=args.lab_orders,
        drugs=args.drugs,
        prescriptions=args.prescriptions,
        inventory_items=args.inventory_items,
        wards=args.wards,
        beds_per_ward=args.beds_per_ward,
        ambulances=args.ambulances,
        ambulance_trips=args.ambulance_trips,
        invoices=args.invoices,
        notifications=args.notifications,
        conversations=args.conversations,
        messages=args.messages,
        reports=args.reports,
        user_devices=args.user_devices,
        ai_credits=args.ai_credits,
    )

    _validate_config(config)

    return config, args.manifest


def main():
    config, manifest_path = parse_args()

    app = create_app("development")

    with app.app_context():
        clinic = get_or_create_clinic()

        control_user = (
            get_or_create_control_user(
                clinic.id
            )
        )

        control_patient = (
            get_or_create_control_patient(
                clinic.id,
                control_user.id,
            )
        )

        user_devices = seed_user_devices(
            control_user,
            config.user_devices,
        )

        clinic = ensure_ai_credits(
            clinic
        )

        users, staff_rows = seed_staff(
            clinic,
            config.staff,
        )

        patients = seed_patients(
            clinic,
            config.patients,
        )

        appointments = seed_appointments(
            clinic,
            patients,
            staff_rows,
            config.appointments,
        )

        consultations = seed_consultations(
            clinic,
            patients,
            staff_rows,
            appointments,
            config.consultations,
        )

        lab_tests = seed_lab_tests(
            clinic,
            config.lab_tests,
        )

        lab_orders = seed_lab_orders(
            clinic,
            patients,
            staff_rows,
            consultations,
            lab_tests,
            config.lab_orders,
        )

        drugs = seed_drugs(
            clinic,
            config.drugs,
        )

        prescriptions = seed_prescriptions(
            clinic,
            patients,
            staff_rows,
            consultations,
            drugs,
            config.prescriptions,
        )

        inventory_items = seed_inventory(
            clinic,
            staff_rows,
            config.inventory_items,
        )

        wards = seed_wards(
            clinic,
            config.wards,
            config.beds_per_ward,
        )

        ambulances = seed_ambulances(
            clinic,
            staff_rows,
            patients,
            config.ambulances,
            config.ambulance_trips,
        )

        invoices = seed_invoices(
            clinic,
            patients,
            appointments,
            config.invoices,
        )

        notifications = seed_notifications(
            clinic,
            users,
            config.notifications,
        )

        conversations, messages = seed_chat(
            clinic,
            users,
            config.conversations,
            config.messages,
        )

        reports = seed_reports(
            clinic,
            staff_rows,
            config.reports,
        )

        db.session.flush()

        clinic = db.session.get(
            Clinic,
            clinic.id,
        )

        db.session.commit()

        manifest = build_manifest(
            config=config,
            clinic=clinic,
            control_user=control_user,
            control_patient=control_patient,
            user_devices=user_devices,
            staff_rows=staff_rows,
            patients=patients,
            appointments=appointments,
            consultations=consultations,
            lab_tests=lab_tests,
            lab_orders=lab_orders,
            drugs=drugs,
            prescriptions=prescriptions,
            inventory_items=inventory_items,
            wards=wards,
            ambulances=ambulances,
            invoices=invoices,
            notifications=notifications,
            conversations=conversations,
            messages=messages,
            reports=reports,
        )

        write_manifest(
            manifest,
            manifest_path,
        )

        print()
        print(
            "=== Clinic System Pro Benchmark Dataset ==="
        )
        print(
            f"Dataset version:    "
            f"{BENCHMARK_VERSION}"
        )
        print(
            f"Clinic ID:          "
            f"{clinic.id}"
        )
        print(
            f"Clinic name:        "
            f"{clinic.name}"
        )
        print(
            f"Control user ID:    "
            f"{control_user.id}"
        )
        print(
            f"Control user:       "
            f"{LOAD_TEST_EMAIL}"
        )
        print(
            f"Control patient ID: "
            f"{control_patient.id}"
        )
        print(
            f"Staff:              "
            f"{len(staff_rows)}"
        )
        print(
            f"Patients:           "
            f"{len(patients)}"
        )
        print(
            f"Appointments:       "
            f"{len(appointments)}"
        )
        print(
            f"Consultations:      "
            f"{len(consultations)}"
        )
        print(
            f"Lab tests:          "
            f"{len(lab_tests)}"
        )
        print(
            f"Lab orders:         "
            f"{len(lab_orders)}"
        )
        print(
            f"Drugs:              "
            f"{len(drugs)}"
        )
        print(
            f"Prescriptions:      "
            f"{len(prescriptions)}"
        )
        print(
            f"Inventory items:    "
            f"{len(inventory_items)}"
        )
        print(
            f"Wards:              "
            f"{len(wards)}"
        )
        print(
            f"Ambulances:         "
            f"{len(ambulances)}"
        )
        print(
            f"Invoices:           "
            f"{len(invoices)}"
        )
        print(
            f"Notifications:      "
            f"{len(notifications)}"
        )
        print(
            f"Conversations:      "
            f"{len(conversations)}"
        )
        print(
            f"Messages:           "
            f"{len(messages)}"
        )
        print(
            f"Reports:            "
            f"{len(reports)}"
        )
        print(
            f"User devices:       "
            f"{len(user_devices)}"
        )
        print(
            f"AI credits:         "
            f"{clinic.ai_credits}"
        )
        print(
            f"Manifest:           "
            f"{manifest_path}"
        )
        print()


if __name__ == "__main__":
    main()