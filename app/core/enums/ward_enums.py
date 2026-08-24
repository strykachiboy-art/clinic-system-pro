import enum

class BedStatus(enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"


class AdmissionStatus(enum.Enum):
    ADMITTED = "admitted"
    DISCHARGED = "discharged"
    TRANSFERRED = "transferred"


class WardType(enum.Enum):
    GENERAL = "general"
    ICU = "icu"
    MATERNITY = "maternity"
    PEDIATRIC = "pediatric"
    ISOLATION = "isolation"