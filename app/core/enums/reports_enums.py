from enum import Enum

class ReportType(str, Enum):
    OVERVIEW = "overview"
    PATIENTS = "patients"
    STAFF = "staff"
    APPOINTMENTS = "appointments"
    BILLING = "billing"
    INVENTORY = "inventory"
    LAB = "lab"
    PHARMACY = "pharmacy"


class ReportFormat(str, Enum):
    PDF = "pdf"
    CSV = "csv"
    XLSX = "xlsx"