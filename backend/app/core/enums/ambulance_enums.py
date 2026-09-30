from enum import Enum


class TripType(str, Enum):
    EMERGENCY_PICKUP = "emergency_pickup"
    INTER_FACILITY_TRANSFER = "inter_facility_transfer"
    DISCHARGE_TRANSPORT = "discharge_transport"
    NON_EMERGENCY = "non_emergency"


class TripStatus(str, Enum):
    REQUESTED = "requested"
    DISPATCHED = "dispatched"
    EN_ROUTE_TO_PICKUP = "en_route_to_pickup"
    AT_PICKUP = "at_pickup"
    PATIENT_ON_BOARD = "patient_on_board"
    EN_ROUTE_TO_DESTINATION = "en_route_to_destination"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VehicleStatus(str, Enum):
    AVAILABLE = "available"
    ON_TRIP = "on_trip"
    MAINTENANCE = "maintenance"
    OUT_OF_SERVICE = "out_of_service"


class EquipmentLevel(str, Enum):
    BLS = "bls"
    ALS = "als"
    CCT = "cct"