import enum

class AppointmentStatus(enum.Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class AppointmentType(enum.Enum):
    IN_PERSON = "in_person"
    TELEMEDICINE = "telemedicine"
    FOLLOW_UP = "follow_up"
    EMERGENCY = "emergency"