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
    TRANSFER = "transfer"
    DAMAGED = "damaged"
    EXPIRED = "expired"



INCREASING_MOVEMENTS = {StockMovementType.RESTOCK}
DECREASING_MOVEMENTS = {
    StockMovementType.USAGE,
    StockMovementType.TRANSFER,
    StockMovementType.DAMAGED,
    StockMovementType.EXPIRED,
}