import enum

class ClinicStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class ClinicType(enum.Enum):
    GENERAL = "general"
    SPECIALIST = "specialist"
    DENTAL = "dental"
    DIAGNOSTIC_CENTER = "diagnostic_center"
    PHARMACY_ONLY = "pharmacy_only"