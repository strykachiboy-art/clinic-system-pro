from enum import Enum


class InventoryCategory(str, Enum):
    MEDICAL_SUPPLY = "medical_supply"
    EQUIPMENT = "equipment"
    CONSUMABLE = "consumable"
    OFFICE_SUPPLY = "office_supply"
    OTHER = "other"


class StockMovementType(str, Enum):
    RESTOCK = "restock"
    USAGE = "usage"
    ADJUSTMENT = "adjustment"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    DAMAGED = "damaged"
    EXPIRED = "expired"


class StockMovementDirection(str, Enum):
    IN = "in"
    OUT = "out"


class InventoryTransferStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    IN_TRANSIT = "in_transit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


INCREASING_MOVEMENTS = {
    StockMovementType.RESTOCK,
    StockMovementType.TRANSFER_IN,
}


DECREASING_MOVEMENTS = {
    StockMovementType.USAGE,
    StockMovementType.TRANSFER_OUT,
    StockMovementType.DAMAGED,
    StockMovementType.EXPIRED,
}