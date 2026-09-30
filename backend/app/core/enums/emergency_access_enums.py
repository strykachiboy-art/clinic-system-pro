from enum import Enum


class EmergencyAccessStatus(str, Enum):
    REQUESTED = "requested"
    ACTIVE = "active"
    DENIED = "denied"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ConsentGuardDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    EMERGENCY_EXCEPTION = "emergency_exception"