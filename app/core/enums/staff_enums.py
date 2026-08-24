import enum

class StaffRole(enum.Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    PHARMACIST = "pharmacist"
    LAB_TECHNICIAN = "lab_technician"
    RECEPTIONIST = "receptionist"
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    OTHER = "other"


class StaffStatus(enum.Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class LeaveType(enum.Enum):
    ANNUAL = "annual"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    UNPAID = "unpaid"


class LeaveStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"