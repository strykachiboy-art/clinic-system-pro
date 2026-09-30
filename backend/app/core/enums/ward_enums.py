from enum import Enum


class BedStatus(str, Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"


class AdmissionStatus(str, Enum):
    ADMITTED = "admitted"
    DISCHARGED = "discharged"
    TRANSFERRED = "transferred"


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FULFILLED = "fulfilled"


class WardType(str, Enum):
    GENERAL = "general"
    ICU = "icu"
    MATERNITY = "maternity"
    PEDIATRIC = "pediatric"
    ISOLATION = "isolation"