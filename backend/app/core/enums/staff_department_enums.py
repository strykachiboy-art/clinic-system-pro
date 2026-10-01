from enum import Enum


class StaffDepartmentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ENDED = "ended"
