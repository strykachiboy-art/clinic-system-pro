from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CHECKS: list[tuple[str, bool, str]] = []


def add_check(
    name: str,
    passed: bool,
    detail: str,
) -> None:
    CHECKS.append(
        (
            name,
            passed,
            detail,
        )
    )


def read_text(
    relative_path: str,
) -> str | None:
    path = ROOT / relative_path

    if not path.is_file():
        return None

    try:
        return path.read_text(
            encoding="utf-8"
        )
    except OSError:
        return None


def run_command(
    args: list[str],
    *,
    timeout: int = 120,
) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        return (
            1,
            str(exc),
        )

    output = (
        result.stdout
        + "\n"
        + result.stderr
    ).strip()

    return (
        result.returncode,
        output,
    )


def check_required_files() -> None:
    required_files = [
        "app/extensions.py",
        "app/config.py",
        "app/core/backup/restore_drill.py",
        "app/core/backup/restore_service.py",
        "app/tests/core/test_config_security.py",
    ]

    for relative_path in required_files:
        exists = (
            ROOT / relative_path
        ).is_file()

        add_check(
            f"Required file: {relative_path}",
            exists,
            "present"
            if exists
            else "MISSING",
        )


def check_runbook() -> None:
    path = (
        ROOT
        / "docs"
        / "security"
        / "BACKUP_RESTORE_DRILL.md"
    )

    if not path.is_file():
        add_check(
            "Backup/restore runbook exists",
            False,
            f"missing: {path}",
        )
        return

    try:
        content = path.read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        add_check(
            "Backup/restore runbook exists",
            False,
            str(exc),
        )
        return

    normalized = content.lower()

    required_fragments = [
        "backup / restore security drill",
        "dedicated postgres",
        "dedicated filesystem",
        "restore_drill_confirmation",
        "restore_drill_target_database_url",
        "pg_restore",
        "psql",
    ]

    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in normalized
    ]

    authentication_evidence = any(
        marker in normalized
        for marker in (
            "authentication_invalidated: true",
            "authentication invalidated",
            "authentication invalidation",
            "token invalidation",
            "token versions",
        )
    )

    outbox_evidence = any(
        marker in normalized
        for marker in (
            "outbox_recovery_completed: true",
            "chat outbox recovery",
            "outbox recovery",
            "processing_outbox_count: 0",
        )
    )

    verification_evidence = any(
        marker in normalized
        for marker in (
            "post_restore_verification_completed: true",
            "post-restore database verification",
            "post-restore verification",
            "database verification",
        )
    )

    success_evidence = any(
        marker in normalized
        for marker in (
            "success: true",
            "successful restore drill",
            "restore drill is complete",
            "restore drill passed",
            "successful recovery",
        )
    )

    if not authentication_evidence:
        missing.append(
            "authentication recovery"
        )

    if not outbox_evidence:
        missing.append(
            "chat outbox recovery"
        )

    if not verification_evidence:
        missing.append(
            "post-restore verification"
        )

    if not success_evidence:
        missing.append(
            "successful drill evidence"
        )

    add_check(
        "Backup/restore runbook content",
        not missing,
        "complete"
        if not missing
        else (
            "missing: "
            + ", ".join(missing)
        ),
    )


def check_python_syntax() -> None:
    python_files = [
        "app/extensions.py",
        "app/config.py",
        "app/core/backup/restore_drill.py",
        "app/core/backup/restore_service.py",
    ]

    for relative_path in python_files:
        path = ROOT / relative_path

        if not path.is_file():
            continue

        try:
            source = path.read_text(
                encoding="utf-8"
            )

            ast.parse(
                source,
                filename=str(path),
            )

            add_check(
                f"Syntax: {relative_path}",
                True,
                "valid Python syntax",
            )
        except (
            OSError,
            SyntaxError,
        ) as exc:
            add_check(
                f"Syntax: {relative_path}",
                False,
                str(exc),
            )


def check_extensions() -> None:
    source = read_text(
        "app/extensions.py"
    )

    if source is None:
        add_check(
            "extensions.py hardened implementation",
            False,
            "file could not be read",
        )
        return

    required_fragments = [
        "def _resolve_cors_origins(",
        "CORS_ALLOWED_ORIGINS",
        "cors_origins = _resolve_cors_origins(",
        "cors.init_app(",
        "origins=cors_origins",
        "supports_credentials=False",
        "limiter.init_app(app)",
        'redis_url = app.config["REDIS_URL"]',
        "redis.StrictRedis.from_url(",
        '"cors_allowed_origins"',
        "cors_origins",
        "celery.conf.update(",
        '"run-scheduled-backup-daily"',
        '"run-backup-retention-daily"',
    ]

    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in source
    ]

    add_check(
        "extensions.py hardened implementation",
        not missing,
        "all expected hardening markers present"
        if not missing
        else (
            "missing: "
            + ", ".join(missing)
        ),
    )

    has_message_queue = (
        "message_queue" in source
        and "redis_url" in source
    )

    add_check(
        "Socket.IO Redis message queue",
        has_message_queue,
        "message_queue configured from Redis URL"
        if has_message_queue
        else (
            "message_queue/redis_url configuration not found"
        ),
    )

    wildcard_socketio = (
        '"cors_allowed_origins": "*"' in source
        or
        'cors_allowed_origins="*"' in source
    )

    add_check(
        "Socket.IO does not use unconditional wildcard",
        not wildcard_socketio,
        "uses configured origins"
        if not wildcard_socketio
        else (
            "unconditional Socket.IO wildcard found"
        ),
    )

    credentialed_cors = (
        "supports_credentials=True"
        in source
    )

    add_check(
        "Credentialed CORS remains disabled",
        not credentialed_cors,
        "supports_credentials=True not found"
        if not credentialed_cors
        else "credentialed CORS enabled",
    )


def check_config() -> None:
    source = read_text(
        "app/config.py"
    )

    if source is None:
        add_check(
            "Required security/infrastructure config exists",
            False,
            "app/config.py could not be read",
        )
        return

    required_fragments = [
        "CORS_ALLOWED_ORIGINS",
        "RATELIMIT_STORAGE_URI",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
    ]

    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in source
    ]

    add_check(
        "Required security/infrastructure config exists",
        not missing,
        "all expected config keys present"
        if not missing
        else (
            "missing: "
            + ", ".join(missing)
        ),
    )

    cors_line_found = False

    for line in source.splitlines():
        stripped = line.strip()

        if stripped.startswith(
            "CORS_ALLOWED_ORIGINS"
        ):
            cors_line_found = True
            break

    add_check(
        "CORS_ALLOWED_ORIGINS explicitly configured",
        cors_line_found,
        "configuration key found"
        if cors_line_found
        else (
            "CORS_ALLOWED_ORIGINS not found"
        ),
    )

    ratelimit_redis = (
        "RATELIMIT_STORAGE_URI = REDIS_URL"
        in source
    )

    add_check(
        "Flask-Limiter uses Redis config",
        ratelimit_redis,
        "RATELIMIT_STORAGE_URI = REDIS_URL"
        if ratelimit_redis
        else (
            "Redis-backed limiter configuration not found"
        ),
    )


def check_restore_drill_source() -> None:
    source = read_text(
        "app/core/backup/restore_drill.py"
    )

    if source is None:
        add_check(
            "Restore drill safety implementation",
            False,
            "restore_drill.py could not be read",
        )
        return

    required_fragments = [
        "RESTORE_DRILL_APPROVED",
        "def _validate_dedicated_database(",
        "def _validate_storage_target(",
        "pg_restore",
        "psql",
        "authentication_invalidated",
        "outbox_recovery_completed",
        "post_restore_verification_completed",
        "processing_outbox_count",
        "token_version = token_version + 1",
        "status = 'pending'",
        "status = 'processing'",
        "if not result.success:",
    ]

    missing = [
        fragment
        for fragment in required_fragments
        if fragment not in source
    ]

    add_check(
        "Restore drill safety implementation",
        not missing,
        "all expected safety/recovery controls present"
        if not missing
        else (
            "missing: "
            + ", ".join(missing)
        ),
    )

    dedicated_database_guard = (
        "_validate_dedicated_database("
        in source
    )

    add_check(
        "Restore drill dedicated database guard",
        dedicated_database_guard,
        "source/target database validation function present"
        if dedicated_database_guard
        else (
            "database separation guard missing"
        ),
    )

    dedicated_storage_guard = (
        "_validate_storage_target("
        in source
    )

    add_check(
        "Restore drill dedicated storage guard",
        dedicated_storage_guard,
        "source/target storage validation function present"
        if dedicated_storage_guard
        else (
            "storage separation guard missing"
        ),
    )

    database_identity_guard = (
        "_database_identity("
        in source
        and "source_database_url"
        in source
        and "target_database_url"
        in source
    )

    add_check(
        "Restore drill source/target database identity check",
        database_identity_guard,
        "source and target database identities are compared"
        if database_identity_guard
        else (
            "database source/target identity comparison not found"
        ),
    )

    storage_collision_guard = (
        "target == source"
        in source
        and "target.exists()"
        in source
    )

    add_check(
        "Restore drill storage collision protection",
        storage_collision_guard,
        "existing/equal storage targets are rejected"
        if storage_collision_guard
        else (
            "storage collision protection not detected"
        ),
    )


def check_auth_rate_limits() -> None:
    candidates: list[Path] = []

    for root_name in (
        "app/api",
        "app/core",
        "app/routes",
    ):
        root = ROOT / root_name

        if not root.exists():
            continue

        candidates.extend(
            root.rglob("*.py")
        )

    if not candidates:
        add_check(
            "Authentication rate-limit scan",
            False,
            "no route/service Python files found",
        )
        return

    login_markers = [
        "login",
        "register",
        "refresh",
        "google",
        "callback",
    ]

    relevant_files: list[Path] = []

    for path in candidates:
        try:
            source = path.read_text(
                encoding="utf-8"
            )
        except OSError:
            continue

        lower = source.lower()

        if any(
            marker in lower
            for marker in login_markers
        ):
            relevant_files.append(
                path
            )

    limiter_files: list[Path] = []

    for path in relevant_files:
        try:
            source = path.read_text(
                encoding="utf-8"
            )
        except OSError:
            continue

        if (
            "@limiter.limit"
            in source
            or "limiter.limit("
            in source
        ):
            limiter_files.append(
                path
            )

    add_check(
        "Authentication rate-limit implementation detected",
        bool(limiter_files),
        (
            "found in: "
            + ", ".join(
                str(path.relative_to(ROOT))
                for path in limiter_files
            )
        )
        if limiter_files
        else (
            "no @limiter.limit usage found "
            "in authentication-related files"
        ),
    )


def check_backup_scheduling() -> None:
    source = read_text(
        "app/extensions.py"
    )

    if source is None:
        add_check(
            "Backup Celery scheduling",
            False,
            "app/extensions.py could not be read",
        )
        return

    required_tasks = [
        '"run-scheduled-backup-daily"',
        '"run-backup-retention-daily"',
        '"task": "run_scheduled_backup"',
        '"task": "run_backup_retention"',
    ]

    missing = [
        fragment
        for fragment in required_tasks
        if fragment not in source
    ]

    add_check(
        "Backup Celery scheduling",
        not missing,
        "backup and retention schedules present"
        if not missing
        else (
            "missing: "
            + ", ".join(missing)
        ),
    )


def check_imports() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(
            0,
            str(ROOT),
        )

    modules = [
        "app",
        "app.config",
        "app.extensions",
        "app.core.backup.restore_drill",
        "app.core.backup.restore_service",
    ]

    for module_name in modules:
        try:
            importlib.import_module(
                module_name
            )

            add_check(
                f"Import: {module_name}",
                True,
                "imported successfully",
            )
        except Exception as exc:
            add_check(
                f"Import: {module_name}",
                False,
                (
                    type(exc).__name__
                    + ": "
                    + str(exc)
                ),
            )


def check_targeted_tests_exist() -> None:
    security_test_dir = (
        ROOT
        / "app"
        / "tests"
        / "core"
        / "security"
    )

    exists = (
        security_test_dir.is_dir()
    )

    add_check(
        "Security test directory",
        exists,
        str(security_test_dir)
        if exists
        else "missing",
    )

    config_test = (
        ROOT
        / "app"
        / "tests"
        / "core"
        / "test_config_security.py"
    )

    add_check(
        "Config security regression test",
        config_test.is_file(),
        "present"
        if config_test.is_file()
        else "missing",
    )


def run_targeted_tests() -> None:
    targets = [
        "app/tests/core/test_config_security.py",
        "app/tests/core/security",
    ]

    existing_targets = []

    for target in targets:
        if (ROOT / target).exists():
            existing_targets.append(
                target
            )

    if not existing_targets:
        add_check(
            "Focused security tests",
            False,
            "no focused test targets found",
        )
        return

    print()
    print(
        "=" * 72
    )
    print(
        "RUNNING FOCUSED SECURITY TESTS"
    )
    print(
        "=" * 72
    )

    code, output = run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *existing_targets,
        ],
        timeout=1800,
    )

    print(output)

    add_check(
        "Focused security tests",
        code == 0,
        "pytest passed"
        if code == 0
        else (
            f"pytest exited with code {code}"
        ),
    )


def check_git_state() -> None:
    code, output = run_command(
        [
            "git",
            "status",
            "--short",
        ]
    )

    add_check(
        "Git working-tree inspection",
        code == 0,
        (
            "git status available"
            if code == 0
            else output
        ),
    )

    if code == 0:
        print()
        print(
            "=" * 72
        )
        print(
            "CURRENT GIT WORKING TREE"
        )
        print(
            "=" * 72
        )
        print(
            output
            or "(clean)"
        )


def check_migrations() -> None:
    code, output = run_command(
        [
            "flask",
            "--app",
            "wsgi:app",
            "db",
            "current",
        ],
        timeout=120,
    )

    add_check(
        "Alembic/Flask-Migrate current revision",
        code == 0,
        output,
    )


def print_results() -> int:
    print()
    print(
        "=" * 72
    )
    print(
        "PRE-FULL-SUITE VERIFICATION RESULTS"
    )
    print(
        "=" * 72
    )

    failures = 0

    for (
        name,
        passed,
        detail,
    ) in CHECKS:
        status = (
            "PASS"
            if passed
            else "FAIL"
        )

        print(
            f"[{status}] {name}"
        )
        print(
            f"       {detail}"
        )

        if not passed:
            failures += 1

    print()
    print(
        "=" * 72
    )

    if failures:
        print(
            f"VERIFICATION BLOCKED: {failures} check(s) failed."
        )
        print(
            "Do NOT start the full suite yet."
        )
        print(
            "=" * 72
        )
        return 1

    print(
        "ALL PRE-FULL-SUITE CHECKS PASSED."
    )
    print(
        "The repository is ready for the full test suite."
    )
    print(
        "=" * 72
    )
    return 0


def main() -> int:
    print(
        "=" * 72
    )
    print(
        "CLINIC SYSTEM PRO v5"
    )
    print(
        "PRE-FULL-SUITE SECURITY / RESILIENCE VERIFICATION"
    )
    print(
        "=" * 72
    )
    print(
        f"Repository: {ROOT}"
    )
    print(
        f"Python: {sys.version.split()[0]}"
    )

    check_required_files()
    check_runbook()
    check_python_syntax()
    check_extensions()
    check_config()
    check_restore_drill_source()
    check_auth_rate_limits()
    check_backup_scheduling()
    check_imports()
    check_targeted_tests_exist()
    check_git_state()
    check_migrations()
    run_targeted_tests()

    return print_results()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )