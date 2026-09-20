from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "dev-secret-change-me",
    )

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(
            basedir,
            "..",
            "clinic.db",
        ),
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.environ.get(
        "JWT_SECRET_KEY",
        "dev-jwt-secret-change-me",
    )

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        hours=1
    )

    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=30
    )

    GOOGLE_CLIENT_ID = os.environ.get(
        "GOOGLE_CLIENT_ID"
    )

    GOOGLE_CLIENT_SECRET = os.environ.get(
        "GOOGLE_CLIENT_SECRET"
    )

    GOOGLE_REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:5000/api/v1/auth/google/callback",
    )

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    #
    # Development/production Redis remains configurable through the
    # environment.
    #
    REDIS_URL = os.environ.get(
        "REDIS_URL",
        "redis://localhost:6379/0",
    )

    # Celery
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # ------------------------------------------------------------------
    # Upload / storage
    # ------------------------------------------------------------------

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        "uploads",
    )

    STORAGE_ROOT = os.environ.get(
        "STORAGE_ROOT"
    )

    STORAGE_PUBLIC_BASE_URL = os.environ.get(
        "STORAGE_PUBLIC_BASE_URL"
    )

    MAX_PROFILE_IMAGE_SIZE_BYTES = (
        5 * 1024 * 1024
    )

    # Flask-Limiter
    RATELIMIT_STORAGE_URI = REDIS_URL

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------

    OPENAI_API_KEY = os.environ.get(
        "OPENAI_API_KEY"
    )

    OPENAI_MODEL = os.environ.get(
        "OPENAI_MODEL",
        "gpt-4o-mini",
    )

    # ------------------------------------------------------------------
    # Integration encryption
    # ------------------------------------------------------------------

    INTEGRATION_ENCRYPTION_KEY = os.environ.get(
        "INTEGRATION_ENCRYPTION_KEY"
    )


class DevelopmentConfig(Config):
    DEBUG = True

    AI_PROVIDER = os.environ.get(
        "AI_PROVIDER",
        "openai",
    )


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True

    # ------------------------------------------------------------------
    # Isolated test database
    # ------------------------------------------------------------------

    SQLALCHEMY_DATABASE_URI = (
        "sqlite:///:memory:"
    )

    # ------------------------------------------------------------------
    # Isolated test Redis
    # ------------------------------------------------------------------
    #
    # Production/development normally use Redis DB 0.
    # Tests use Redis DB 15 so test authentication/revocation state
    # cannot collide with the normal development Redis database.
    #
    REDIS_URL = os.environ.get(
        "TEST_REDIS_URL",
        "redis://localhost:6379/15",
    )

    # Keep Celery test infrastructure on the isolated Redis database.
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL

    # Keep Flask-Limiter isolated from development/production counters.
    RATELIMIT_STORAGE_URI = REDIS_URL

    # ------------------------------------------------------------------
    # Test encryption key
    # ------------------------------------------------------------------

    INTEGRATION_ENCRYPTION_KEY = (
        "YOUR_VALID_FERNET_TEST_KEY_HERE"
    )

    MAX_PROFILE_IMAGE_SIZE_BYTES = (
        5 * 1024 * 1024
    )


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}