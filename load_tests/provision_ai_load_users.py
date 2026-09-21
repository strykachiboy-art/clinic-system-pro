from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask_jwt_extended import create_access_token

from app import create_app
from app.core.auth.user.models.user_model import User
from app.core.enums.role_enums import Role
from app.extensions import db
from app.modules.patient.models.patient_model import Patient


AI_LOAD_TEST_ROLES = {
    Role.ADMIN,
    Role.DOCTOR,
    Role.NURSE,
    Role.PHARMACIST,
    Role.LAB_TECHNICIAN,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Provision synthetic AI users and generate JWTs "
            "for Locust capacity testing."
        )
    )

    parser.add_argument(
        "--users",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--patient-id",
        type=int,
        default=int(
            os.getenv(
                "LOCUST_PATIENT_ID",
                "0",
            )
        ),
    )

    parser.add_argument(
        "--role",
        default=os.getenv(
            "LOCUST_AI_ROLE",
            Role.DOCTOR.value,
        ),
    )

    parser.add_argument(
        "--tokens-file",
        default=os.getenv(
            "LOCUST_TOKENS_FILE",
            "load_tests/ai_tokens.txt",
        ),
    )

    return parser.parse_args()


def resolve_role(
    value: str,
) -> Role:
    normalized = value.strip().lower()

    try:
        role = Role(normalized)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid AI load-test role: {value}"
        ) from exc

    if role not in AI_LOAD_TEST_ROLES:
        raise RuntimeError(
            f"Role '{role.value}' is not allowed for AI load testing"
        )

    return role


def main() -> None:
    args = parse_args()

    if args.users <= 0:
        raise RuntimeError(
            "--users must be greater than zero"
        )

    if args.patient_id <= 0:
        raise RuntimeError(
            "--patient-id must be greater than zero"
        )

    role = resolve_role(
        args.role
    )

    app = create_app(
        os.getenv(
            "FLASK_ENV",
            "development",
        )
    )

    token_path = (
        Path(args.tokens_file)
        .expanduser()
        .resolve()
    )

    token_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with app.app_context():
        patient = db.session.get(
            Patient,
            args.patient_id,
        )

        if patient is None:
            raise RuntimeError(
                f"Patient {args.patient_id} was not found"
            )

        if patient.clinic_id is None:
            raise RuntimeError(
                f"Patient {args.patient_id} has no clinic"
            )

        clinic_id = patient.clinic_id

        users = []

        for index in range(
            1,
            args.users + 1,
        ):
            email = (
                f"ai-load-{index}@test.local"
            )

            user = db.session.scalar(
                db.select(User).where(
                    User.email == email
                )
            )

            if user is None:
                user = User(
                    email=email,
                    password_hash=None,
                    role=role,
                    is_active=True,
                    clinic_id=clinic_id,
                )

                db.session.add(user)

            else:
                user.role = role
                user.is_active = True
                user.clinic_id = clinic_id

            users.append(user)

        db.session.flush()

        tokens = []

        for user in users:
            token = create_access_token(
                identity=str(user.id),
                additional_claims={
                    "role": user.role.value,
                    "token_version": user.token_version,
                },
            )

            tokens.append(token)

        temp_path = token_path.with_suffix(
            token_path.suffix + ".tmp"
        )

        temp_path.write_text(
            "\n".join(tokens) + "\n",
            encoding="utf-8",
        )

        temp_path.replace(
            token_path
        )

        db.session.commit()

        print(
            f"Provisioned {len(users)} synthetic AI users."
        )

        print(
            f"Clinic ID: {clinic_id}"
        )

        print(
            f"Role: {role.value}"
        )

        print(
            f"Token file: {token_path}"
        )


if __name__ == "__main__":
    main()