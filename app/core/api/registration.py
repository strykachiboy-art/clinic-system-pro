from __future__ import annotations

from flask import Flask
from flask.blueprints import Blueprint


API_V1_PREFIX = "/api/v1"


def register_api_blueprint(
    app: Flask,
    blueprint: Blueprint,
) -> None:
    app.register_blueprint(
        blueprint,
        url_prefix=f"{API_V1_PREFIX}{blueprint.url_prefix}",
    )