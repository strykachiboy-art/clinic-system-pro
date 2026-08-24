import enum

class ReportType(enum.Enum):
    OVERVIEW = "overview"
    PATIENTS = "patients"
    STAFF = "staff"
    APPOINTMENTS = "appointments"
    BILLING = "billing"
    INVENTORY = "inventory"
    LAB = "lab"
    PHARMACY = "pharmacy"


class ReportFormat(enum.Enum):
    PDF = "pdf"
    CSV = "csv"
    XLSX = "xlsx"