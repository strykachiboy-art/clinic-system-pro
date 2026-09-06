from enum import Enum

class ExcuseType(str, Enum):
    MEDICAL = "medical"
    FAMILY = "family"
    EMERGENCY = "emergency"
    PERSONAL = "personal"
    OTHER = "other"


class ExcuseStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"