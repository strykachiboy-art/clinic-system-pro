# Core
from app.core.auth.user.models.user_model import User
from app.core.audit.models.audit_model import AuditLog

# Clinic
from app.modules.clinic.models.clinic_model import Clinic

# Patient
from app.modules.patient.models.patient_model import (
    Patient,
    PatientFamilyMember,
    PatientInsurance,
    PatientVitals,
)

# Staff
from app.modules.staff.models.staff_model import (
    Staff,
    PayrollRecord,
    LeaveRequest,
)

# Appointment
from app.modules.appointment.models.appointment_model import Appointment

# Consultation
from app.modules.consultation.models.consultation_model import (
    Consultation,
    ConsultationTemplate,
)

# Prescription
from app.modules.prescription.models.prescription_model import (
    Prescription,
    PrescriptionItem,
    DrugInteraction,
)

# Lab
from app.modules.lab.models.lab_model import (
    LabTest,
    LabOrder,
    LabOrderItem,
)

# Pharmacy
from app.modules.pharmacy.models.pharmacy_model import (
    Drug,
    DrugBatch,
    DispenseRecord,
    DispenseItem,
)

# Billing
from app.modules.billing.models.billing_model import (
    Invoice,
    InvoiceItem,
    Payment,
)

# Ward
from app.modules.ward.models.ward_model import (
    Ward,
    Bed,
    Admission,
    WardTransfer,
)

# Inventory
from app.modules.inventory.models.inventory_model import (
    InventoryItem,
    InventorySupplier,
    StockMovement,
)

# Reports
from app.modules.reports.models.reports_model import GeneratedReport

# AI
from app.modules.ai.models.ai_model import AILog

# Ambulance
from app.modules.ambulance.models.ambulance_model import (
    AmbulanceVehicle,
    AmbulanceTrip,
)

# HIE
from app.modules.hie.models.hie_model import (
    HIEIntegration,
    HIESubmission,
)

# Notifications
from app.core.notifications.models.notification_models import Notification

# Clinic Settings
from app.modules.settings.models.clinic_settings import ClinicSettings

# Integration
from app.modules.settings.models.integration_config import IntegrationConfig

# Google Auth
from app.core.auth.user.models.user_auth_identity_model import UserAuthIdentity

# User Device
from app.core.auth.user.models.user_device_model import UserDevice

# Asset Control
from app.modules.asset_control.models.asset_model import Asset

# Chat
from app.modules.chat.models.conversation_model import Conversation
from app.modules.chat.models.conversation_participant_model import (
    ConversationParticipant,
)
from app.modules.chat.models.message_model import Message
from app.modules.chat.models.message_attachment_model import MessageAttachment
from app.modules.chat.models.message_mention_model import MessageMention
from app.modules.chat.models.message_pin_model import MessagePin
from app.modules.chat.models.message_read_receipt_model import MessageReadReceipt
from app.modules.chat.models.message_reaction_model import MessageReaction
from app.modules.chat.models.message_revision_model import MessageRevision
from app.modules.chat.models.chat_outbox_model import ChatOutbox
from app.modules.chat.models.chat_usage_model import ChatUsage


__all__ = [
    # Core
    "User",
    "AuditLog",

    # Clinic
    "Clinic",

    # Patient
    "Patient",
    "PatientFamilyMember",
    "PatientInsurance",
    "PatientVitals",

    # Staff
    "Staff",
    "PayrollRecord",
    "LeaveRequest",

    # Appointment
    "Appointment",

    # Consultation
    "Consultation",
    "ConsultationTemplate",

    # Prescription
    "Prescription",
    "PrescriptionItem",
    "DrugInteraction",

    # Lab
    "LabTest",
    "LabOrder",
    "LabOrderItem",

    # Pharmacy
    "Drug",
    "DrugBatch",
    "DispenseRecord",
    "DispenseItem",

    # Billing
    "Invoice",
    "InvoiceItem",
    "Payment",

    # Ward
    "Ward",
    "Bed",
    "Admission",
    "WardTransfer",

    # Inventory
    "InventoryItem",
    "InventorySupplier",
    "StockMovement",

    # Reports
    "GeneratedReport",

    # AI
    "AILog",

    # Ambulance
    "AmbulanceVehicle",
    "AmbulanceTrip",

    # HIE
    "HIEIntegration",
    "HIESubmission",

    # Notifications
    "Notification",

    # Settings
    "ClinicSettings",
    "IntegrationConfig",

    # Authentication
    "UserAuthIdentity",

    # User Devices
    "UserDevice",

    # Asset Control
    "Asset",

    # Chat
    "Conversation",
    "ConversationParticipant",
    "Message",
    "MessageAttachment",
    "MessageMention",
    "MessagePin",
    "MessageReadReceipt",
    "MessageReaction",
    "MessageRevision",
    "ChatOutbox",
    "ChatUsage",
]