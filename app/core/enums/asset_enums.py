from enum import Enum


class AssetCategory(str, Enum):
    MEDICAL_EQUIPMENT = "medical_equipment"
    MEDICAL_DEVICE = "medical_device"
    IT_EQUIPMENT = "it_equipment"
    COMPUTER = "computer"
    NETWORK_EQUIPMENT = "network_equipment"
    FURNITURE = "furniture"
    VEHICLE = "vehicle"
    OPERATIONAL_EQUIPMENT = "operational_equipment"
    FACILITY_EQUIPMENT = "facility_equipment"
    OTHER = "other"


class AssetStatus(str, Enum):
    ACTIVE = "active"
    ASSIGNED = "assigned"
    IN_STORAGE = "in_storage"
    UNDER_MAINTENANCE = "under_maintenance"
    OUT_OF_SERVICE = "out_of_service"
    LOST = "lost"
    RETIRED = "retired"
    DISPOSED = "disposed"


class AssetCondition(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    DAMAGED = "damaged"
    NON_FUNCTIONAL = "non_functional"


class AssetOwnership(str, Enum):
    CLINIC = "clinic"
    LEASED = "leased"
    RENTED = "rented"
    GOVERNMENT = "government"
    DONATED = "donated"
    OTHER = "other"


class MaintenanceStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    SCHEDULED = "scheduled"
    DUE = "due"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    
    
class AssetHistoryEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    LOCATION_CHANGED = "location_changed"
    STATUS_CHANGED = "status_changed"
    CONDITION_CHANGED = "condition_changed"
    MAINTENANCE_STARTED = "maintenance_started"
    MAINTENANCE_COMPLETED = "maintenance_completed"
    MAINTENANCE_CANCELLED = "maintenance_cancelled"
    RETIRED = "retired"
    DISPOSED = "disposed"