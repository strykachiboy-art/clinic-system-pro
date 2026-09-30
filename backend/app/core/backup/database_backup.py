from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app
from sqlalchemy.engine import URL, make_url


DEFAULT_PG_DUMP_FORMAT = "custom"
DEFAULT_TIMEOUT_SECONDS = 300
READ_CHUNK_SIZE = 1024 * 1024
MAX_ERROR_LENGTH = 4000


class DatabaseBackupError(RuntimeError):
    """Raised when a PostgreSQL backup cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class DatabaseBackupResult:
    backup_id: str
    created_at: str
    database_name: str
    database_host: str | None
    database_port: int | None
    backup_path: str
    backup_size_bytes: int
    backup_sha256: str
    format: str
    migration_revision: str | None
    success: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_database_url(
    database_url: str | None = None,
) -> URL:
    if database_url is None:
        database_url = current_app.config.get(
            "SQLALCHEMY_DATABASE_URI"
        )

    if not isinstance(
        database_url,
        str,
    ):
        raise DatabaseBackupError(
            "Database URL must be a string"
        )

    database_url = database_url.strip()

    if not database_url:
        raise DatabaseBackupError(
            "Database URL cannot be empty"
        )

    try:
        url = make_url(
            database_url
        )
    except Exception as exc:
        raise DatabaseBackupError(
            "Invalid database URL"
        ) from exc

    if url.get_backend_name() != "postgresql":
        raise DatabaseBackupError(
            "Database backup requires a PostgreSQL database"
        )

    if not url.database:
        raise DatabaseBackupError(
            "PostgreSQL database name is required"
        )

    return url


def _get_pg_dump_path(
    pg_dump_path: str | None = None,
) -> str:
    if pg_dump_path is None:
        pg_dump_path = current_app.config.get(
            "PG_DUMP_PATH"
        )

    if pg_dump_path is None:
        pg_dump_path = "pg_dump"

    if not isinstance(
        pg_dump_path,
        str,
    ):
        raise DatabaseBackupError(
            "pg_dump path must be a string"
        )

    pg_dump_path = pg_dump_path.strip()

    if not pg_dump_path:
        raise DatabaseBackupError(
            "pg_dump path cannot be empty"
        )

    resolved = shutil.which(
        pg_dump_path
    )

    if resolved is None:
        raise DatabaseBackupError(
            "pg_dump executable was not found"
        )

    return resolved


def _get_timeout_seconds(
    timeout_seconds: int | None = None,
) -> int:
    if timeout_seconds is None:
        timeout_seconds = current_app.config.get(
            "BACKUP_COMMAND_TIMEOUT_SECONDS",
            DEFAULT_TIMEOUT_SECONDS,
        )

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or timeout_seconds <= 0
    ):
        raise DatabaseBackupError(
            "Backup timeout must be a positive integer"
        )

    return timeout_seconds


def _validate_output_path(
    output_path: str | Path,
) -> Path:
    if isinstance(
        output_path,
        bool,
    ):
        raise DatabaseBackupError(
            "Backup output path is invalid"
        )

    path = Path(
        output_path
    ).expanduser()

    if path.name in {
        "",
        ".",
        "..",
    }:
        raise DatabaseBackupError(
            "Backup output path is invalid"
        )

    return path.resolve()


def _safe_database_dsn(
    url: URL,
) -> str:
    safe_url = url.set(
        password=None
    )

    return safe_url.render_as_string(
        hide_password=False
    )


def _build_command(
    *,
    pg_dump_path: str,
    database_url: URL,
    output_path: Path,
) -> list[str]:
    return [
        pg_dump_path,
        "--format",
        DEFAULT_PG_DUMP_FORMAT,
        "--file",
        str(output_path),
        "--dbname",
        _safe_database_dsn(
            database_url
        ),
    ]


def _checksum_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    try:
        with path.open(
            "rb"
        ) as source:
            while True:
                chunk = source.read(
                    READ_CHUNK_SIZE
                )

                if not chunk:
                    break

                digest.update(
                    chunk
                )
    except OSError as exc:
        raise DatabaseBackupError(
            "Unable to read backup artifact "
            f"for checksum: {path}"
        ) from exc

    return digest.hexdigest()


def _cleanup_partial(
    path: Path,
) -> None:
    try:
        path.unlink(
            missing_ok=True
        )
    except OSError:
        pass


def backup_database(
    *,
    output_path: str | Path,
    database_url: str | None = None,
    pg_dump_path: str | None = None,
    timeout_seconds: int | None = None,
    migration_revision: str | None = None,
) -> DatabaseBackupResult:

    url = _get_database_url(
        database_url
    )

    executable = _get_pg_dump_path(
        pg_dump_path
    )

    timeout = _get_timeout_seconds(
        timeout_seconds
    )

    final_path = _validate_output_path(
        output_path
    )

    if final_path.exists():
        raise DatabaseBackupError(
            f"Backup output already exists: "
            f"{final_path}"
        )

    final_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    partial_path = final_path.with_name(
        f"{final_path.name}.partial"
    )

    if partial_path.exists():
        _cleanup_partial(
            partial_path
        )

    command = _build_command(
        pg_dump_path=executable,
        database_url=url,
        output_path=partial_path,
    )

    environment = os.environ.copy()

    if url.password is not None:
        environment["PGPASSWORD"] = (
            url.password
        )

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        _cleanup_partial(
            partial_path
        )

        raise DatabaseBackupError(
            "pg_dump timed out after "
            f"{timeout} seconds"
        ) from exc

    except OSError as exc:
        _cleanup_partial(
            partial_path
        )

        raise DatabaseBackupError(
            "Unable to execute pg_dump"
        ) from exc

    if completed.returncode != 0:
        _cleanup_partial(
            partial_path
        )

        stderr = (
            completed.stderr
            or ""
        ).strip()

        if len(stderr) > MAX_ERROR_LENGTH:
            stderr = stderr[
                -MAX_ERROR_LENGTH:
            ]

        if stderr:
            raise DatabaseBackupError(
                "pg_dump failed: "
                f"{stderr}"
            )

        raise DatabaseBackupError(
            "pg_dump failed with exit code "
            f"{completed.returncode}"
        )

    if not partial_path.is_file():
        _cleanup_partial(
            partial_path
        )

        raise DatabaseBackupError(
            "pg_dump completed without producing "
            "a backup artifact"
        )

    try:
        backup_size = partial_path.stat().st_size
    except OSError as exc:
        _cleanup_partial(
            partial_path
        )

        raise DatabaseBackupError(
            "Unable to inspect backup artifact"
        ) from exc

    if backup_size <= 0:
        _cleanup_partial(
            partial_path
        )

        raise DatabaseBackupError(
            "pg_dump produced an empty backup artifact"
        )

    try:
        partial_path.replace(
            final_path
        )
    except OSError as exc:
        _cleanup_partial(
            partial_path
        )

        raise DatabaseBackupError(
            "Unable to finalize database backup"
        ) from exc

    try:
        checksum = _checksum_file(
            final_path
        )
    except DatabaseBackupError:
        _cleanup_partial(
            final_path
        )

        raise

    created_at = _utcnow().isoformat()

    return DatabaseBackupResult(
        backup_id=str(
            uuid4()
        ),
        created_at=created_at,
        database_name=url.database,
        database_host=url.host,
        database_port=url.port,
        backup_path=str(
            final_path
        ),
        backup_size_bytes=backup_size,
        backup_sha256=checksum,
        format=DEFAULT_PG_DUMP_FORMAT,
        migration_revision=(
            migration_revision
        ),
        success=True,
    )