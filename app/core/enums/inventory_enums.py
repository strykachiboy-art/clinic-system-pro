import enum

class InventoryCategory(enum.Enum):
    MEDICAL_SUPPLY = "medical_supply"     
    EQUIPMENT = "equipment"                
    CONSUMABLE = "consumable"           
    OFFICE_SUPPLY = "office_supply"
    OTHER = "other"


class StockMovementType(enum.Enum):
    RESTOCK = "restock"
    USAGE = "usage"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"
    DAMAGED = "damaged"
    EXPIRED = "expired"