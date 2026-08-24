import enum

class PrescriptionStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class DrugInteractionSeverity(enum.Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"