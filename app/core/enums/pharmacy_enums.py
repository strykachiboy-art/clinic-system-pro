from enum import Enum

class DrugCategory(str, Enum):
    ANTIBIOTIC = "antibiotic"
    ANALGESIC = "analgesic"
    ANTIVIRAL = "antiviral"
    ANTIHISTAMINE = "antihistamine"
    VITAMIN = "vitamin"
    CONTROLLED_SUBSTANCE = "controlled_substance"
    OTHER = "other"


class DispenseStatus(str, Enum):
    PENDING = "pending"
    PARTIALLY_DISPENSED = "partially_dispensed"
    DISPENSED = "dispensed"
    CANCELLED = "cancelled"