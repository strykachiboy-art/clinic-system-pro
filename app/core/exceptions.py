from __future__ import annotations


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ValidationError(DomainError):
    status_code = 422


class InsufficientCreditsError(ConflictError):
    status_code = 402


class APIVersionNotSupportedError(DomainError):
    status_code = 404
    code = "api_version_not_supported"

    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(
            f"API version '{version}' is not supported."
        )