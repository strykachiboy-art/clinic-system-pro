from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db as _db

from app.core.enums.notification_enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)

from app.core.notifications.models.notification_models import (
    Notification,
)


# ============================================================================
# APP / DATABASE / CLIENT
# ============================================================================


@pytest.fixture(scope="function")
def app():
    """
    Create an isolated Flask application and database for every test.
    """

    flask_app = create_app("testing")

    # ------------------------------------------------------------------------
    # Test-only integration encryption key.
    #
    # Production continues to require INTEGRATION_ENCRYPTION_KEY from the
    # environment/deployment secret manager.
    # ------------------------------------------------------------------------
    flask_app.config["INTEGRATION_ENCRYPTION_KEY"] = (
        Fernet.generate_key().decode("utf-8")
    )

    with flask_app.app_context():
        _db.create_all()

        try:
            yield flask_app
        finally:
            _db.session.rollback()
            _db.session.remove()
            _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    """Return the application's SQLAlchemy extension."""

    return _db


@pytest.fixture(scope="function")
def db_session(app, db):
    """
    Return the active SQLAlchemy session.
    """

    return db.session


@pytest.fixture(scope="function")
def client(app):
    """Flask test client."""

    return app.test_client()


# ============================================================================
# AUTHENTICATION
# ============================================================================


@pytest.fixture()
def auth_headers_for(app):
    """
    Factory for authenticated JWT headers.
    """

    def _make(user, role=None):
        claim_role = (
            role
            if role is not None
            else user.role
        )

        if hasattr(claim_role, "value"):
            claim_role = claim_role.value

        with app.test_request_context():
            token = create_access_token(
                identity=str(user.id),
                additional_claims={
                    "role": claim_role,
                },
            )

        return {
            "Authorization": f"Bearer {token}",
        }

    return _make


@pytest.fixture()
def make_auth_headers(auth_headers_for):
    """
    Backward-compatible authentication helper.
    """

    def _make(user, role=None):
        return auth_headers_for(
            user,
            role=role,
        )

    return _make


# ============================================================================
# CLINIC
# ============================================================================


@pytest.fixture()
def make_clinic(db):
    """
    Factory for Clinic.
    """

    from app.core.enums.clinic_enums import ClinicStatus
    from app.modules.clinic.models.clinic_model import Clinic

    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1

        overrides.setdefault(
            "name",
            f"Test Clinic {counter['n']}",
        )

        overrides.setdefault(
            "ai_credits",
            5,
        )

        # Default test clinics are active.
        # Individual tests can explicitly override this.
        overrides.setdefault(
            "status",
            ClinicStatus.ACTIVE,
        )

        clinic = Clinic(**overrides)

        db.session.add(clinic)
        db.session.flush()

        return clinic

    return _make


@pytest.fixture()
def clinic(make_clinic):
    """Default active clinic."""

    return make_clinic()


@pytest.fixture()
def suspended_clinic(make_clinic):
    """Clinic in SUSPENDED state."""

    from app.core.enums.clinic_enums import ClinicStatus

    return make_clinic(
        name="Suspended Clinic",
        status=ClinicStatus.SUSPENDED,
    )


# ============================================================================
# USER
# ============================================================================


@pytest.fixture()
def make_user(db):
    """
    Factory for User.
    """

    from app.core.auth.user.models.user_model import User
    from app.core.enums.role_enums import Role

    counter = {"n": 0}

    def _make(
        clinic=None,
        role=Role.ADMIN,
        is_active=True,
        password="supersecret",
        **overrides,
    ):
        counter["n"] += 1

        overrides.setdefault(
            "email",
            f"user{counter['n']}@test.com",
        )

        user = User(
            clinic_id=(
                clinic.id
                if clinic is not None
                else None
            ),
            role=role,
            is_active=is_active,
            **overrides,
        )

        user.set_password(password)

        db.session.add(user)
        db.session.flush()

        return user

    return _make


@pytest.fixture()
def user(make_user, clinic):
    """Default active ADMIN user."""

    from app.core.enums.role_enums import Role

    return make_user(
        clinic,
        role=Role.ADMIN,
        email="admin@test.com",
    )


# ============================================================================
# SETTINGS
# ============================================================================


@pytest.fixture()
def make_clinic_settings(db_session):
    """
    Factory for ClinicSettings.
    """

    from app.modules.settings.models.clinic_settings import (
        ClinicSettings,
    )

    def _make(
        clinic,
        language="en",
        date_format="YYYY-MM-DD",
        time_format="24h",
        notification_preferences=None,
        feature_flags=None,
        operational_preferences=None,
        security_preferences=None,
        system_preferences=None,
        is_enabled=True,
        version=1,
        **overrides,
    ):
        settings = ClinicSettings(
            clinic_id=clinic.id,
            language=language,
            date_format=date_format,
            time_format=time_format,
            notification_preferences=(
                {}
                if notification_preferences is None
                else notification_preferences
            ),
            feature_flags=(
                {}
                if feature_flags is None
                else feature_flags
            ),
            operational_preferences=(
                {}
                if operational_preferences is None
                else operational_preferences
            ),
            security_preferences=(
                {}
                if security_preferences is None
                else security_preferences
            ),
            system_preferences=(
                {}
                if system_preferences is None
                else system_preferences
            ),
            is_enabled=is_enabled,
            version=version,
            **overrides,
        )

        db_session.add(settings)
        db_session.flush()

        return settings

    return _make


@pytest.fixture()
def clinic_settings(
    make_clinic_settings,
    clinic,
):
    """Default enabled clinic settings."""

    return make_clinic_settings(
        clinic,
    )


@pytest.fixture()
def disabled_clinic_settings(
    make_clinic_settings,
    clinic,
):
    """Default disabled clinic settings."""

    return make_clinic_settings(
        clinic,
        is_enabled=False,
    )


# ============================================================================
# MESSAGE
# ============================================================================


@pytest.fixture()
def make_message(db):
    """
    Factory for Message.
    """

    from app.core.enums.message_enums import (
        MessagePriority,
        MessageStatus,
        MessageType,
    )

    from app.modules.messages.models.message_model import Message

    counter = {"n": 0}

    def _make(
        clinic,
        sender,
        recipient,
        subject=None,
        body="Test message body",
        message_type=MessageType.DIRECT,
        status=MessageStatus.SENT,
        priority=MessagePriority.NORMAL,
        parent_message=None,
        sent_at=None,
        read_at=None,
        deleted_at=None,
        **overrides,
    ):
        counter["n"] += 1

        if subject is None:
            subject = (
                f"Test Message {counter['n']}"
            )

        if sent_at is None:
            sent_at = datetime.now(
                timezone.utc
            )

        message = Message(
            clinic_id=clinic.id,
            sender_id=sender.id,
            recipient_id=recipient.id,
            subject=subject,
            body=body,
            message_type=message_type,
            status=status,
            priority=priority,
            parent_message_id=(
                parent_message.id
                if parent_message is not None
                else None
            ),
            sent_at=sent_at,
            read_at=read_at,
            deleted_at=deleted_at,
            **overrides,
        )

        db.session.add(message)
        db.session.flush()

        return message

    return _make


# ============================================================================
# NOTIFICATION
# ============================================================================


@pytest.fixture()
def make_notification(db_session):
    """
    Factory for Notification.
    """

    def _make_notification(
        *,
        clinic_id,
        user_id,
        title="Test Notification",
        message="This is a test notification.",
        notification_type=NotificationType.SYSTEM,
        priority=NotificationPriority.NORMAL,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.PENDING,
        reference_type=None,
        reference_id=None,
        is_read=False,
        read_at=None,
        sent_at=None,
        delivered_at=None,
        failed_at=None,
        error_message=None,
        retry_count=0,
        created_at=None,
        updated_at=None,
    ):
        notification = Notification(
            clinic_id=clinic_id,
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            channel=channel,
            status=status,
            reference_type=reference_type,
            reference_id=reference_id,
            is_read=is_read,
            read_at=read_at,
            sent_at=sent_at,
            delivered_at=delivered_at,
            failed_at=failed_at,
            error_message=error_message,
            retry_count=retry_count,
            created_at=created_at,
            updated_at=updated_at,
        )

        db_session.add(notification)
        db_session.flush()

        return notification

    return _make_notification


@pytest.fixture()
def notification(
    make_notification,
    clinic,
    user,
):
    """
    Default pending in-app notification.
    """

    return make_notification(
        clinic_id=clinic.id,
        user_id=user.id,
    )


# ============================================================================
# STAFF
# ============================================================================


@pytest.fixture()
def make_staff(db, make_user):
    """
    Factory for Staff.
    """

    from app.core.enums.role_enums import Role
    from app.core.enums.staff_enums import StaffStatus
    from app.modules.staff.models.staff_model import Staff

    counter = {"n": 0}

    def _make(
        clinic,
        role=Role.ADMIN,
        status=StaffStatus.ACTIVE,
        first_name="Test",
        last_name="Staff",
        user_is_active=True,
        user_overrides=None,
        **overrides,
    ):
        counter["n"] += 1

        user_overrides = dict(
            user_overrides or {}
        )

        linked_user = make_user(
            clinic,
            role=role,
            is_active=user_is_active,
            **user_overrides,
        )

        staff = Staff(
            clinic_id=clinic.id,
            user_id=linked_user.id,
            first_name=first_name,
            last_name=last_name,
            status=status,
            **overrides,
        )

        db.session.add(staff)
        db.session.flush()

        return staff

    return _make


@pytest.fixture()
def staff(make_staff, clinic):
    """Default active ADMIN staff member."""

    return make_staff(clinic)


@pytest.fixture()
def make_authenticated_staff(
    make_staff,
    auth_headers_for,
):
    """
    Factory returning (staff, headers).
    """

    def _make(clinic, role, **overrides):
        staff_obj = make_staff(
            clinic,
            role=role,
            **overrides,
        )

        headers = auth_headers_for(
            staff_obj.user,
            role=role,
        )

        return staff_obj, headers

    return _make


# ============================================================================
# PATIENT
# ============================================================================


@pytest.fixture()
def make_patient(db):
    """
    Factory for Patient.
    """

    from app.modules.patient.models.patient_model import Patient

    counter = {"n": 0}

    def _make(clinic, **overrides):
        counter["n"] += 1

        overrides.setdefault(
            "first_name",
            "Jane",
        )

        overrides.setdefault(
            "last_name",
            "Doe",
        )

        overrides.setdefault(
            "patient_number",
            f"MRN-{counter['n']}",
        )

        patient = Patient(
            clinic_id=clinic.id,
            **overrides,
        )

        db.session.add(patient)
        db.session.flush()

        return patient

    return _make


@pytest.fixture()
def patient(make_patient, clinic):
    """Default patient."""

    return make_patient(clinic)


# ============================================================================
# ASSET CONTROL
# ============================================================================


@pytest.fixture()
def make_asset(db):
    """
    Factory for Asset.

    Creates a valid active clinic asset by default.
    Individual tests can override any supported Asset field.
    """

    from app.core.enums.asset_enums import (
        AssetCategory,
        AssetCondition,
        AssetOwnership,
        AssetStatus,
        MaintenanceStatus,
    )

    from app.modules.asset_control.models.asset_model import Asset

    counter = {"n": 0}

    def _make(
        clinic,
        asset_tag=None,
        name=None,
        category=AssetCategory.MEDICAL_EQUIPMENT,
        status=AssetStatus.ACTIVE,
        condition=AssetCondition.GOOD,
        ownership=AssetOwnership.CLINIC,
        is_active=True,
        **overrides,
    ):
        counter["n"] += 1

        if asset_tag is None:
            asset_tag = (
                f"AST-{counter['n']:04d}"
            )

        if name is None:
            name = (
                f"Test Asset {counter['n']}"
            )

        overrides.setdefault(
            "maintenance_status",
            MaintenanceStatus.NOT_REQUIRED,
        )

        asset = Asset(
            clinic_id=clinic.id,
            asset_tag=asset_tag,
            name=name,
            category=category,
            status=status,
            condition=condition,
            ownership=ownership,
            is_active=is_active,
            **overrides,
        )

        db.session.add(asset)
        db.session.flush()

        return asset

    return _make


@pytest.fixture()
def asset(
    make_asset,
    clinic,
):
    """
    Default active clinic asset.
    """

    return make_asset(
        clinic,
    )


# ============================================================================
# APPOINTMENT
# ============================================================================


@pytest.fixture()
def make_appointment(db):
    """Factory for Appointment."""

    from app.core.enums.appointment_enums import (
        AppointmentStatus,
        AppointmentType,
    )

    from app.modules.appointment.models.appointment_model import (
        Appointment,
    )

    counter = {"n": 0}

    def _make(
        clinic,
        patient,
        staff,
        status=AppointmentStatus.SCHEDULED,
        appointment_type=AppointmentType.IN_PERSON,
        scheduled_start=None,
        scheduled_end=None,
        **overrides,
    ):
        counter["n"] += 1

        if scheduled_start is None:
            scheduled_start = (
                datetime.now(timezone.utc)
                + timedelta(days=counter["n"])
            )

        if scheduled_end is None:
            scheduled_end = (
                scheduled_start
                + timedelta(hours=1)
            )

        appointment = Appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            status=status,
            appointment_type=appointment_type,
            **overrides,
        )

        db.session.add(appointment)
        db.session.flush()

        return appointment

    return _make


# ============================================================================
# CONSULTATION
# ============================================================================


@pytest.fixture()
def make_consultation(db):
    """Factory for Consultation."""

    from app.core.enums.consultation_enums import (
        ConsultationStatus,
        ConsultationType,
    )

    from app.modules.consultation.models.consultation_model import (
        Consultation,
    )

    def _make(
        clinic,
        patient,
        staff,
        appointment=None,
        consultation_type=ConsultationType.GENERAL,
        status=ConsultationStatus.IN_PROGRESS,
        template=None,
        **overrides,
    ):
        consultation = Consultation(
            clinic_id=clinic.id,
            patient_id=patient.id,
            staff_id=staff.id,
            appointment_id=(
                appointment.id
                if appointment is not None
                else None
            ),
            consultation_type=consultation_type,
            status=status,
            template_id=(
                template.id
                if template is not None
                else None
            ),
            **overrides,
        )

        db.session.add(consultation)
        db.session.flush()

        return consultation

    return _make


@pytest.fixture()
def make_template(db):
    """Factory for ConsultationTemplate."""

    from app.modules.consultation.models.consultation_model import (
        ConsultationTemplate,
    )

    counter = {"n": 0}

    def _make(
        clinic=None,
        name=None,
        specialty=None,
        structure=None,
        is_active=True,
        **overrides,
    ):
        counter["n"] += 1

        if name is None:
            name = (
                "Test Consultation Template "
                f"{counter['n']}"
            )

        if structure is None:
            structure = {
                "sections": [
                    "chief_complaint",
                    "symptoms",
                    "diagnosis",
                    "treatment_plan",
                ]
            }

        template = ConsultationTemplate(
            clinic_id=(
                clinic.id
                if clinic is not None
                else None
            ),
            name=name,
            specialty=specialty,
            structure=structure,
            is_active=is_active,
            **overrides,
        )

        db.session.add(template)
        db.session.flush()

        return template

    return _make


# ============================================================================
# PHARMACY
# ============================================================================


@pytest.fixture()
def make_drug(db):
    """Factory for Drug."""

    from app.modules.pharmacy.models.pharmacy_model import Drug

    counter = {"n": 0}

    def _make(clinic=None, **overrides):
        counter["n"] += 1

        overrides.setdefault(
            "name",
            f"Test Drug {counter['n']}",
        )

        overrides.setdefault(
            "is_active",
            True,
        )

        drug = Drug(
            clinic_id=(
                clinic.id
                if clinic is not None
                else None
            ),
            **overrides,
        )

        db.session.add(drug)
        db.session.flush()

        return drug

    return _make


@pytest.fixture()
def make_drug_batch(db):
    """Factory for DrugBatch."""

    from app.modules.pharmacy.models.pharmacy_model import DrugBatch

    counter = {"n": 0}

    def _make(clinic, drug, **overrides):
        counter["n"] += 1

        overrides.setdefault(
            "batch_number",
            f"BATCH-{counter['n']}",
        )

        overrides.setdefault(
            "quantity_on_hand",
            100,
        )

        overrides.setdefault(
            "reorder_level",
            20,
        )

        overrides.setdefault(
            "expiry_date",
            date.today()
            + timedelta(days=90),
        )

        batch = DrugBatch(
            clinic_id=clinic.id,
            drug_id=drug.id,
            **overrides,
        )

        db.session.add(batch)
        db.session.flush()

        return batch

    # IMPORTANT:
    # Return the factory itself so pytest injects a callable fixture.
    return _make


# ============================================================================
# PRESCRIPTION
# ============================================================================


@pytest.fixture()
def make_prescription(db):
    """Factory for Prescription."""

    from app.core.enums.prescription_enums import (
        PrescriptionStatus,
    )

    from app.modules.prescription.models.prescription_model import (
        Prescription,
    )

    def _make(
        clinic,
        patient,
        staff,
        status=PrescriptionStatus.ACTIVE,
        **overrides,
    ):
        prescription = Prescription(
            clinic_id=clinic.id,
            patient_id=patient.id,
            prescribed_by_id=staff.id,
            status=status,
            **overrides,
        )

        db.session.add(prescription)
        db.session.flush()

        return prescription

    return _make


@pytest.fixture()
def make_prescription_item(db):
    """Factory for PrescriptionItem."""

    from app.modules.prescription.models.prescription_model import (
        PrescriptionItem,
    )

    def _make(
        prescription,
        drug,
        quantity=30,
        **overrides,
    ):
        item = PrescriptionItem(
            prescription_id=prescription.id,
            drug_id=drug.id,
            quantity=quantity,
            **overrides,
        )

        db.session.add(item)
        db.session.flush()

        return item

    return _make


# ============================================================================
# WARD
# ============================================================================


@pytest.fixture()
def make_ward(db):
    """Factory for Ward."""

    from app.modules.ward.models.ward_model import Ward

    counter = {"n": 0}

    def _make(
        clinic,
        capacity=5,
        **overrides,
    ):
        counter["n"] += 1

        overrides.setdefault(
            "name",
            f"Test Ward {counter['n']}",
        )

        ward = Ward(
            clinic_id=clinic.id,
            capacity=capacity,
            **overrides,
        )

        db.session.add(ward)
        db.session.flush()

        return ward

    return _make


@pytest.fixture()
def make_bed(db):
    """Factory for Bed."""

    from app.modules.ward.models.ward_model import Bed

    counter = {"n": 0}

    def _make(ward, **overrides):
        counter["n"] += 1

        overrides.setdefault(
            "bed_number",
            f"B{counter['n']}",
        )

        bed = Bed(
            ward_id=ward.id,
            **overrides,
        )

        db.session.add(bed)
        db.session.flush()

        return bed

    # IMPORTANT:
    # Return the factory itself so pytest injects a callable fixture.
    return _make


# ============================================================================
# LAB
# ============================================================================


@pytest.fixture()
def make_lab_test(db):
    """Factory for LabTest."""

    from app.modules.lab.models.lab_model import LabTest

    counter = {"n": 0}

    def _make(clinic=None, **overrides):
        counter["n"] += 1

        overrides.setdefault(
            "name",
            f"Test Lab Test {counter['n']}",
        )

        test = LabTest(
            clinic_id=(
                clinic.id
                if clinic is not None
                else None
            ),
            **overrides,
        )

        db.session.add(test)
        db.session.flush()

        return test

    return _make


@pytest.fixture()
def make_lab_order(db):
    """Factory for LabOrder plus LabOrderItems."""

    from app.core.enums.lab_enums import LabOrderStatus

    from app.modules.lab.models.lab_model import (
        LabOrder,
        LabOrderItem,
    )

    counter = {"n": 0}

    def _make(
        clinic,
        patient,
        staff,
        tests,
        status=LabOrderStatus.ORDERED,
        **overrides,
    ):
        counter["n"] += 1

        overrides.setdefault(
            "qr_code",
            f"LAB-TEST-{counter['n']}",
        )

        order = LabOrder(
            clinic_id=clinic.id,
            patient_id=patient.id,
            ordered_by_id=staff.id,
            status=status,
            **overrides,
        )

        db.session.add(order)
        db.session.flush()

        for test in tests:
            db.session.add(
                LabOrderItem(
                    order_id=order.id,
                    test_id=test.id,
                )
            )

        db.session.flush()

        return order

    return _make


# ============================================================================
# AUDIT
# ============================================================================


@pytest.fixture()
def make_audit_log(db):
    """
    Factory for AuditLog.
    """

    from app.core.audit.models.audit_model import AuditLog
    from app.core.enums.audit_enums import AuditAction

    counter = {"n": 0}

    def _make(
        user=None,
        user_id=None,
        action=AuditAction.CREATE,
        entity_type="Patient",
        entity_id=None,
        description="Test audit log",
        old_value=None,
        new_value=None,
        ip_address=None,
        **overrides,
    ):
        counter["n"] += 1

        if entity_id is None:
            entity_id = counter["n"]

        if user is not None:
            user_id = user.id

        log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            **overrides,
        )

        db.session.add(log)
        db.session.flush()

        return log

    return _make


# ============================================================================
# AI
# ============================================================================


@pytest.fixture()
def mock_ai_provider(monkeypatch):
    """
    Mock the AI provider boundary used by AI routes.
    """

    import app.modules.ai.services.ai_service as ai_service

    state = {
        "response": {},
        "last_call": None,
    }

    def _fake_call_openai(feature, payload):
        state["last_call"] = {
            "feature": feature,
            "payload": payload,
        }

        return state["response"]

    monkeypatch.setattr(
        ai_service,
        "_call_openai",
        _fake_call_openai,
    )

    class Controller:
        def set_response(self, value):
            state["response"] = value

        @property
        def last_call(self):
            return state["last_call"]

    return Controller()


# ============================================================================
# RESPONSE ASSERTION HELPERS
# ============================================================================


@pytest.fixture()
def assert_domain_error():
    """
    Assert an application/domain error handled by error_handlers.py.
    """

    def _assert(response, status_code):
        body = response.get_json()

        assert response.status_code == status_code, body
        assert body["success"] is False
        assert "error" in body

        return body

    return _assert


@pytest.fixture()
def assert_forbidden():
    """
    Assert role_required() rejection.
    """

    def _assert(response):
        body = response.get_json()

        assert response.status_code == 403, body
        assert body["error"] == "Insufficient permissions"

        return body

    return _assert


@pytest.fixture()
def assert_unauthorized():
    """
    Assert Flask-JWT-Extended authentication failure.
    """

    def _assert(response):
        body = response.get_json()

        assert response.status_code in (
            401,
            422,
        ), body

        assert "msg" in body

        return body

    return _assert


# ============================================================================
# DATABASE HELPERS
# ============================================================================


@pytest.fixture()
def get_by_id(db_session):
    """
    SQLAlchemy 2.x-style primary-key lookup helper.
    """

    def _get(model, object_id):
        return db_session.get(
            model,
            object_id,
        )

    return _get


@pytest.fixture()
def commit_db(db_session):
    """
    Explicit transaction helper.
    """

    def _commit():
        db_session.commit()

    return _commit


@pytest.fixture()
def rollback_db(db_session):
    """
    Explicit rollback helper.
    """

    def _rollback():
        db_session.rollback()

    return _rollback