from enum import Enum

class ClinicStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class ClinicType(str, Enum):
    GENERAL = "general"
    SPECIALIST = "specialist"
    DENTAL = "dental"
    DIAGNOSTIC_CENTER = "diagnostic_center"
    PHARMACY_ONLY = "pharmacy_only"