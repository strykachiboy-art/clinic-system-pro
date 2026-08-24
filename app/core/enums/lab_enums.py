from enum import Enum

class LabOrderStatus(str,Enum):
    ORDERED = "ordered"
    SAMPLE_COLLECTED = "sample_collected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LabResultFlag(str, Enum):
    NORMAL = "normal"
    ABNORMAL = "abnormal"
    CRITICAL = "critical"


class SampleType(str, Enum):
    BLOOD = "blood"
    URINE = "urine"
    STOOL = "stool"
    SALIVA = "saliva"
    TISSUE = "tissue"
    SWAB = "swab"
    OTHER = "other"