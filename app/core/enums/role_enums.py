from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"

    DOCTOR = "doctor"
    NURSE = "nurse"
    PATIENT = "patient"
    PHARMACIST = "pharmacist"
    LAB_TECHNICIAN = "lab_technician"
    RECEPTIONIST = "receptionist"
    ACCOUNTANT = "accountant"

    PARAMEDIC = "paramedic"
    EMT = "emt"

    DRIVER = "driver"

    AMBULANCE_DISPATCHER = "ambulance_dispatcher"
    AMBULANCE_COORDINATOR = "ambulance_coordinator"

    OTHER = "other"