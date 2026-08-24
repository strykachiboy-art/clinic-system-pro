import enum

class DrugCategory(enum.Enum):
    ANTIBIOTIC = "antibiotic"
    ANALGESIC = "analgesic"
    ANTIVIRAL = "antiviral"
    ANTIHISTAMINE = "antihistamine"
    VITAMIN = "vitamin"
    CONTROLLED_SUBSTANCE = "controlled_substance"
    OTHER = "other"


class DispenseStatus(enum.Enum):
    PENDING = "pending"
    PARTIALLY_DISPENSED = "partially_dispensed"
    DISPENSED = "dispensed"
    CANCELLED = "cancelled"