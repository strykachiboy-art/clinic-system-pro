from __future__ import annotations

from flask import Flask, request


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        if not app.config.get(
            "SECURITY_HEADERS_ENABLED",
            True,
        ):
            return response

        response.headers.setdefault(
            "X-Content-Type-Options",
            "nosniff",
        )

        response.headers.setdefault(
            "X-Frame-Options",
            "DENY",
        )

        response.headers.setdefault(
            "Referrer-Policy",
            "no-referrer",
        )

        response.headers.setdefault(
            "Permissions-Policy",
            (
                "camera=(), "
                "microphone=(), "
                "geolocation=(), "
                "payment=()"
            ),
        )

        if (
            app.config.get(
                "SECURITY_HSTS_ENABLED",
                False,
            )
            and request.is_secure
        ):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
