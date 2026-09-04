from enum import Enum


class Role(str, Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    PATIENT = "patient"
    PHARMACIST = "pharmacist"
    LAB_TECHNICIAN = "lab_technician"
    RECEPTIONIST = "receptionist"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"

    # Emergency / clinical
    PARAMEDIC = "paramedic"
    EMT = "emt"

    # Transport
    DRIVER = "driver"

    # Ambulance operations
    AMBULANCE_DISPATCHER = "ambulance_dispatcher"
    AMBULANCE_COORDINATOR = "ambulance_coordinator"

    OTHER = "other"