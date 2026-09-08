import os

from gevent.lock import Semaphore
from locust import HttpUser, between, task


class AIUser(HttpUser):
    wait_time = between(6.0, 7.0)

    # Shared across all AIUser instances in this Locust process.
    access_token = None
    token_lock = Semaphore()

    def on_start(self):
        patient_id = os.getenv("LOCUST_PATIENT_ID")
        raw_drugs = os.getenv(
            "LOCUST_DRUGS",
            "aspirin,ibuprofen",
        )

        if not patient_id:
            raise RuntimeError("LOCUST_PATIENT_ID is required")

        try:
            self.patient_id = int(patient_id)
        except ValueError as exc:
            raise RuntimeError(
                "LOCUST_PATIENT_ID must be an integer"
            ) from exc

        self.drug_names = [
            drug.strip()
            for drug in raw_drugs.split(",")
            if drug.strip()
        ]

        if not self.drug_names:
            raise RuntimeError(
                "LOCUST_DRUGS must contain at least one drug name"
            )

        # Only the first virtual user logs in.
        # All other users reuse the same access token.
        if AIUser.access_token is None:
            with AIUser.token_lock:
                if AIUser.access_token is None:
                    self._login_once()

        self.headers = {
            "Authorization": f"Bearer {AIUser.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _login_once(self):
        email = os.getenv("LOCUST_EMAIL")
        password = os.getenv("LOCUST_PASSWORD")

        if not email:
            raise RuntimeError("LOCUST_EMAIL is required")

        if not password:
            raise RuntimeError("LOCUST_PASSWORD is required")

        login_payload = {
            "email": email,
            "password": password,
        }

        with self.client.post(
            "/api/auth/login",
            json=login_payload,
            name="POST /api/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Login failed: HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
                raise RuntimeError("Locust login failed")

            try:
                body = response.json()
            except ValueError as exc:
                response.failure(
                    "Login response was not JSON"
                )
                raise RuntimeError(
                    "Locust login returned non-JSON"
                ) from exc

            data = body.get("data") or {}
            access_token = data.get("access_token")

            if not access_token:
                response.failure(
                    "Login response has no access_token"
                )
                raise RuntimeError(
                    "Locust login returned no access token"
                )

            AIUser.access_token = access_token

            response.success()

    @task
    def drug_interactions(self):
        payload = {
            "drug_names": self.drug_names,
            "patient_id": self.patient_id,
        }

        with self.client.post(
            "/api/ai/drug-interactions",
            json=payload,
            headers=self.headers,
            name="POST /api/ai/drug-interactions",
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
                # Expected when the AI route rate limiter is triggered
                # during high-concurrency load testing.
                response.success()
                return

            response.failure(
                f"Unexpected HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )