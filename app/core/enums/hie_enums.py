from enum import Enum


class HIEIntegrationStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class HIEOperation(str, Enum):
    PATIENT_SUBMISSION = "patient_submission"
    CLINICAL_DATA_SUBMISSION = "clinical_data_submission"
    CLINICAL_DOCUMENT_SUBMISSION = "clinical_document_submission"
    PATIENT_QUERY = "patient_query"
    CLINICAL_DATA_QUERY = "clinical_data_query"


class HIESubmissionStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"