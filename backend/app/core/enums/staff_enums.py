from enum import Enum

class StaffStatus(str, Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class LeaveType(str, Enum):
    ANNUAL = "annual"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    COMPASSIONATE = "compassionate"
    STUDY = "study"
    UNPAID = "unpaid"
    EMERGENCY = "emergency"
    OTHER = "other"


class LeaveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"