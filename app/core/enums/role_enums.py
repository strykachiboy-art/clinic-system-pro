from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    RECEPTIONIST = "receptionist"
    PHARMACIST = "pharmacist"
    LAB_TECH = "lab_tech"
    ACCOUNTANT = "accountant"
    PATIENT = "patient"