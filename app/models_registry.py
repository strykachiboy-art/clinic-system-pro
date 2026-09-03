

# Core
from app.modules.user.models.user import User
from app.core.audit.models.audit_model import AuditLog

# Clinic
from app.modules.clinic.models.clinic_model import Clinic

# Patient
from app.modules.patient.models.patient_model import (
    Patient, PatientFamilyMember, PatientInsurance, PatientVitals
)

# Staff
from app.modules.staff.models.staff_model import Staff, PayrollRecord, LeaveRequest

# Appointment
from app.modules.appointment.models.appointment_model import Appointment

# Consultation
from app.modules.consultation.models.consultation_model import Consultation, ConsultationTemplate

# Prescription
from app.modules.prescription.models.prescription_model import (
    Prescription, PrescriptionItem, DrugInteraction
)

# Lab
from app.modules.lab.models.lab_model import LabTest, LabOrder, LabOrderItem

# Pharmacy
from app.modules.pharmacy.models.pharmacy_model import Drug, DrugBatch, DispenseRecord, DispenseItem

# Billing
from app.modules.billing.models.billing_model import Invoice, InvoiceItem, Payment

# Ward
from app.modules.ward.models.ward_model import Ward, Bed, Admission, WardTransfer

# Inventory
from app.modules.inventory.models.inventory_model import InventoryItem, InventorySupplier, StockMovement

# Reports
from app.modules.reports.models.reports_model import GeneratedReport

# AI
from app.modules.ai.models.ai_model import AILog

# User
from app.modules.user.models.user import User

# Ambulance
from app.modules.ambulance.models.ambulance_model import AmbulanceVehicle, AmbulanceTrip