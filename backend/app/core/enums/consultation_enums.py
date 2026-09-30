from enum import Enum

class ConsultationStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConsultationType(str, Enum):
    GENERAL = "general"
    FOLLOW_UP = "follow_up"
    SPECIALIST = "specialist"
    EMERGENCY = "emergency"