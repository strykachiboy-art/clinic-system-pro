from enum import Enum


class Role(str, Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    PHARMACIST = "pharmacist"
    LAB_TECHNICIAN = "lab_technician"
    RECEPTIONIST = "receptionist"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    DRIVER = "driver"
    PARAMEDIC = "paramedic"
    OTHER = "other"