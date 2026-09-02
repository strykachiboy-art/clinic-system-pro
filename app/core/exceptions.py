class DomainError(Exception):
    """Base class for business-logic errors raised from the service layer."""
    status_code = 400


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ValidationError(DomainError):
    status_code = 422


class InsufficientCreditsError(ConflictError):
    status_code = 402