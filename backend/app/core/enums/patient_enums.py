from enum import Enum

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class BloodType(str, Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    UNKNOWN = "unknown"


class FamilyRelation(str, Enum):
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    SIBLING = "sibling"
    GUARDIAN = "guardian"
    OTHER = "other"