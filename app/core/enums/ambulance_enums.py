from enum import Enum

class TripType(str, Enum):
    EMERGENCY_PICKUP = "emergency_pickup"        # dispatched to an external location
    INTER_FACILITY_TRANSFER = "inter_facility_transfer"  # patient moving to/from another hospital
    DISCHARGE_TRANSPORT = "discharge_transport"  # taking a discharged patient home
    NON_EMERGENCY = "non_emergency"              # scheduled routine transport


class TripStatus(str, Enum):
    REQUESTED = "requested"
    DISPATCHED = "dispatched"
    EN_ROUTE_TO_PICKUP = "en_route_to_pickup"
    AT_PICKUP = "at_pickup"
    EN_ROUTE_TO_DESTINATION = "en_route_to_destination"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VehicleStatus(str, Enum):
    AVAILABLE = "available"
    ON_TRIP = "on_trip"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"


class EquipmentLevel(str, Enum):
    BLS = "bls"   # Basic Life Support
    ALS = "als"   # Advanced Life Support
    CCT = "cct"   # Critical Care Transport