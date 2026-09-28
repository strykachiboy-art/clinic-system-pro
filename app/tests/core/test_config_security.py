from __future__ import annotations

import importlib

import pytest

import app.config as app_config
from app import create_app


def test_production_config_reads_secret_environment_values(
    monkeypatch,
):
    secret_key = "production-secret-test-value"
    jwt_secret_key = "production-jwt-secret-test-value"

    monkeypatch.setenv(
        "SECRET_KEY",
        secret_key,
    )
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        jwt_secret_key,
    )

    config_module = importlib.reload(
        app_config
    )

    try:
        assert (
            config_module.ProductionConfig.SECRET_KEY
            == secret_key
        )

        assert (
            config_module.ProductionConfig.JWT_SECRET_KEY
            == jwt_secret_key
        )
    finally:
        importlib.reload(app_config)


@pytest.mark.parametrize(
    "missing_secret",
    [
        "SECRET_KEY",
        "JWT_SECRET_KEY",
    ],
)
def test_production_rejects_missing_required_secret(
    monkeypatch,
    missing_secret,
):
    monkeypatch.setenv(
        "SECRET_KEY",
        "production-secret-test-value",
    )

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "production-jwt-secret-test-value",
    )

    monkeypatch.delenv(
        missing_secret,
        raising=False,
    )

    expected_name = (
        "SECRET_KEY"
        if missing_secret == "SECRET_KEY"
        else "JWT_SECRET_KEY"
    )

    with pytest.raises(
        RuntimeError,
        match=(
            rf"Production {expected_name} "
            r"is not configured"
        ),
    ):
        create_app("production")