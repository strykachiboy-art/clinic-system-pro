from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


basedir = os.path.abspath(
    os.path.dirname(__file__)
)


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "dev-secret-change-me",
    )

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///"
        + os.path.join(
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

    REDIS_URL = os.environ.get(
        "REDIS_URL",
        "redis://localhost:6379/0",
    )

    # Celery

    CELERY_BROKER_URL = REDIS_URL

    CELERY_RESULT_BACKEND = REDIS_URL

    # ------------------------------------------------------------------
    # Upload / Storage
    # ------------------------------------------------------------------

    MAX_CONTENT_LENGTH = (
        16 * 1024 * 1024
    )

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
    
    
        # ------------------------------------------------------------------
    # Backup & Disaster Recovery
    # ------------------------------------------------------------------

    BACKUP_ROOT = os.environ.get(
        "BACKUP_ROOT"
    )

    BACKUP_RETENTION_DAYS = int(
        os.environ.get(
            "BACKUP_RETENTION_DAYS",
            "30",
        )
    )

    BACKUP_MIN_RECOVERY_POINTS = int(
        os.environ.get(
            "BACKUP_MIN_RECOVERY_POINTS",
            "1",
        )
    )
    

    # ------------------------------------------------------------------
    # Flask-Limiter
    # ------------------------------------------------------------------

    RATELIMIT_STORAGE_URI = REDIS_URL

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------

    OPENAI_API_KEY = (
        "OPENAI_API_KEY"
        )

    OPENAI_MODEL = "gpt-4o-mini"

    AI_PROVIDER = "openai"

    AI_LOAD_TEST_MODE = True

    AI_LOAD_TEST_RATE_LIMIT = (
        "1000 per second"
    )

    # ------------------------------------------------------------------
    # Integration Encryption
    # ------------------------------------------------------------------

    INTEGRATION_ENCRYPTION_KEY = os.environ.get(
        "INTEGRATION_ENCRYPTION_KEY"
    )


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True

    JWT_SECRET_KEY = os.environ.get(
        "TEST_JWT_SECRET_KEY",
        "clinic-system-pro-test-jwt-secret-2026",
    )

    # ------------------------------------------------------------------
    # Isolated Test Database
    # ------------------------------------------------------------------

    SQLALCHEMY_DATABASE_URI = (
        "sqlite:///:memory:"
    )
    # ------------------------------------------------------------------
    # Isolated Test Redis
    # ------------------------------------------------------------------

    REDIS_URL = os.environ.get(
        "TEST_REDIS_URL",
        "redis://localhost:6379/15",
    )

    CELERY_BROKER_URL = REDIS_URL

    CELERY_RESULT_BACKEND = REDIS_URL

    RATELIMIT_STORAGE_URI = REDIS_URL

    # ------------------------------------------------------------------
    # Test Encryption Key
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