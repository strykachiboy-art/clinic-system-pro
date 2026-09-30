from enum import Enum


class FeedbackType(str, Enum):
    PRODUCT_FEEDBACK = "product_feedback"
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    SERVICE_COMPLAINT = "service_complaint"
    COMPLIMENT = "compliment"


class FeedbackCategory(str, Enum):
    USABILITY = "usability"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    BILLING = "billing"
    APPOINTMENT = "appointment"
    PHARMACY = "pharmacy"
    LABORATORY = "laboratory"
    CLINICAL_WORKFLOW = "clinical_workflow"
    COMMUNICATION = "communication"
    SECURITY = "security"
    OTHER = "other"


class FeedbackPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class FeedbackStatus(str, Enum):
    OPEN = "open"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    CLOSED = "closed"
    REJECTED = "rejected"


class FeedbackSource(str, Enum):
    WEB = "web"
    MOBILE = "mobile"
    API = "api"
    SYSTEM = "system"