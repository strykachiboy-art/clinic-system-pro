import logging

from flask import Flask, jsonify
from pydantic import ValidationError as PydanticValidationError
from werkzeug.exceptions import HTTPException

from app.core.exceptions import DomainError


logger = logging.getLogger(__name__)


def _error_response(message, status_code, details=None):
    body = {
        "success": False,
        "error": message,
    }

    if details is not None:
        body["details"] = details

    return jsonify(body), status_code


def _sanitize_pydantic_errors(errors):
    sanitized = []

    for error in errors:
        item = dict(error)

        if "ctx" in item and isinstance(item["ctx"], dict):
            item["ctx"] = {
                key: str(value)
                for key, value in item["ctx"].items()
            }

        sanitized.append(item)

    return sanitized


def register_error_handlers(app: Flask) -> None:

    @app.errorhandler(DomainError)
    def handle_domain_error(error: DomainError):
        return _error_response(
            str(error),
            error.status_code,
        )

    @app.errorhandler(PydanticValidationError)
    def handle_pydantic_error(error: PydanticValidationError):
        details = _sanitize_pydantic_errors(error.errors())

        return _error_response(
            "Validation error",
            422,
            details,
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return _error_response(
            error.description,
            error.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        logger.exception(
            "Unhandled application error",
            exc_info=error,
        )

        return _error_response(
            "Internal server error",
            500,
        )
