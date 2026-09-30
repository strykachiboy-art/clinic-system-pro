from enum import Enum


class NotificationChannel(str, Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationPriority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class NotificationType(str, Enum):
    GENERAL = "general"
    APPOINTMENT = "appointment"
    CONSULTATION = "consultation"
    LAB = "lab"
    PHARMACY = "pharmacy"
    PRESCRIPTION = "prescription"
    INVENTORY = "inventory"
    BILLING = "billing"
    WARD = "ward"
    AMBULANCE = "ambulance"
    HIE = "hie"
    SYSTEM = "system"