from enum import Enum

class AuditAction(str,Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    VIEW = "view"
    LOGIN = "login"
    LOGOUT = "logout"
    PAYMENT = "payment"
    STATUS_CHANGE = "status_change"