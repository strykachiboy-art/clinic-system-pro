from enum import Enum


class MessageType(str, Enum):
    DIRECT = "direct"
    SYSTEM = "system"
    CLINICAL = "clinical"
    APPOINTMENT = "appointment"
    LAB = "lab"
    PHARMACY = "pharmacy"
    BILLING = "billing"
    GENERAL = "general"


class MessageStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    ARCHIVED = "archived"


class MessagePriority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"