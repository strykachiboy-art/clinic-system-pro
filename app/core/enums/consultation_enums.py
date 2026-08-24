import enum

class ConsultationStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConsultationType(enum.Enum):
    GENERAL = "general"
    FOLLOW_UP = "follow_up"
    SPECIALIST = "specialist"
    EMERGENCY = "emergency"