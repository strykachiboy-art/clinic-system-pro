from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from gevent.lock import Semaphore
from locust import HttpUser, between, task


def _create_load_test_id() -> str:
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    return (
        f"locust-{timestamp}-{uuid4().hex[:8]}"
    )


def _env_float(
    name: str,
    default: float,
) -> float:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must be a number"
        ) from exc

    if parsed < 0:
        raise RuntimeError(
            f"{name} must be greater than or equal to zero"
        )

    return parsed


class AIUser(HttpUser):
    wait_min = _env_float(
        "LOCUST_WAIT_MIN",
        6.0,
    )

    wait_max = _env_float(
        "LOCUST_WAIT_MAX",
        7.0,
    )

    if wait_min > wait_max:
        raise RuntimeError(
            "LOCUST_WAIT_MIN must be less than or equal to "
            "LOCUST_WAIT_MAX"
        )

    wait_time = between(
        wait_min,
        wait_max,
    )

    load_test_id = (
        os.getenv("LOCUST_RUN_ID")
        or _create_load_test_id()
    )

    mode = os.getenv(
        "LOCUST_AI_MODE",
        "capacity",
    ).strip().lower()

    tokens_file = os.getenv(
        "LOCUST_TOKENS_FILE"
    )

    shared_access_token = None
    shared_token_lock = Semaphore()

    tokens = None
    token_index = 0
    token_lock = Semaphore()

    def on_start(self):
        patient_id = os.getenv(
            "LOCUST_PATIENT_ID"
        )

        raw_drugs = os.getenv(
            "LOCUST_DRUGS",
            "aspirin,ibuprofen",
        )

        if self.mode not in {
            "capacity",
            "protection",
        }:
            raise RuntimeError(
                "LOCUST_AI_MODE must be "
                "'capacity' or 'protection'"
            )

        if not patient_id:
            raise RuntimeError(
                "LOCUST_PATIENT_ID is required"
            )

        try:
            self.patient_id = int(patient_id)
        except ValueError as exc:
            raise RuntimeError(
                "LOCUST_PATIENT_ID must be an integer"
            ) from exc

        if self.patient_id <= 0:
            raise RuntimeError(
                "LOCUST_PATIENT_ID must be greater than zero"
            )

        self.drug_names = [
            drug.strip()
            for drug in raw_drugs.split(",")
            if drug.strip()
        ]

        if not self.drug_names:
            raise RuntimeError(
                "LOCUST_DRUGS must contain at least one drug name"
            )

        access_token = self._get_access_token()

        self.headers = {
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

    def _get_access_token(self) -> str:
        if self.mode == "capacity":
            return self._get_capacity_token()

        return self._get_protection_token()

    def _get_capacity_token(self) -> str:
        if not self.tokens_file:
            raise RuntimeError(
                "LOCUST_TOKENS_FILE is required "
                "in capacity mode"
            )

        if AIUser.tokens is None:
            with AIUser.token_lock:
                if AIUser.tokens is None:
                    path = Path(
                        self.tokens_file
                    ).expanduser()

                    if not path.is_file():
                        raise RuntimeError(
                            f"Token file not found: {path}"
                        )

                    tokens = [
                        line.strip()
                        for line in path.read_text(
                            encoding="utf-8"
                        ).splitlines()
                        if line.strip()
                    ]

                    if not tokens:
                        raise RuntimeError(
                            "LOCUST_TOKENS_FILE contains no tokens"
                        )

                    AIUser.tokens = tokens

        with AIUser.token_lock:
            index = AIUser.token_index

            if index >= len(AIUser.tokens):
                raise RuntimeError(
                    "Not enough synthetic JWTs for "
                    "the requested Locust users"
                )

            access_token = AIUser.tokens[index]
            AIUser.token_index += 1

        if not access_token:
            raise RuntimeError(
                "Synthetic JWT is empty"
            )

        return access_token

    def _get_protection_token(self) -> str:
        if AIUser.shared_access_token is not None:
            return AIUser.shared_access_token

        with AIUser.shared_token_lock:
            if AIUser.shared_access_token is not None:
                return AIUser.shared_access_token

            AIUser.shared_access_token = (
                self._login_once()
            )

            return AIUser.shared_access_token

    def _login_once(self) -> str:
        email = os.getenv(
            "LOCUST_EMAIL"
        )

        password = os.getenv(
            "LOCUST_PASSWORD"
        )

        if not email:
            raise RuntimeError(
                "LOCUST_EMAIL is required"
            )

        if not password:
            raise RuntimeError(
                "LOCUST_PASSWORD is required"
            )

        payload = {
            "email": email,
            "password": password,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Load-Test-ID": self.load_test_id,
        }

        with self.client.post(
            "/api/v1/auth/login",
            json=payload,
            headers=headers,
            name="POST /api/v1/auth/login [setup]",
            catch_response=True,
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"Login failed: HTTP "
                    f"{response.status_code}: "
                    f"{response.text[:200]}"
                )

                raise RuntimeError(
                    "Locust login failed"
                )

            try:
                body = response.json()
            except ValueError as exc:
                response.failure(
                    "Login response was not JSON"
                )

                raise RuntimeError(
                    "Locust login returned non-JSON"
                ) from exc

            if body.get("success") is not True:
                response.failure(
                    "Login response success != true"
                )

                raise RuntimeError(
                    "Locust login was unsuccessful"
                )

            data = body.get("data") or {}

            access_token = data.get(
                "access_token"
            )

            if not access_token:
                response.failure(
                    "Login response has no access_token"
                )

                raise RuntimeError(
                    "Locust login returned no access token"
                )

            response.success()

            return access_token

    @task
    def drug_interactions(self):
        payload = {
            "drug_names": self.drug_names,
            "patient_id": self.patient_id,
        }

        with self.client.post(
            "/api/v1/ai/drug-interactions",
            json=payload,
            headers=self.headers,
            name="POST /api/v1/ai/drug-interactions",
            catch_response=True,
        ) as response:

            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    response.failure(
                        "HTTP 200 but response was not JSON"
                    )
                    return

                if body.get("success") is not True:
                    response.failure(
                        "HTTP 200 but success != true"
                    )
                    return

                if "data" not in body:
                    response.failure(
                        "HTTP 200 but response has no data"
                    )
                    return

                response.success()
                return

            if response.status_code == 429:
                if self.mode == "protection":
                    response.success()
                else:
                    response.failure(
                        "HTTP 429 rate limited during capacity test"
                    )

                return

            response.failure(
                f"Unexpected HTTP "
                f"{response.status_code}: "
                f"{response.text[:200]}"
            )