from __future__ import annotations

from typing import Any, Optional, Protocol


class HIEProvider(Protocol):
    def submit_patient(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def submit_clinical_data(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def submit_clinical_document(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    def query_patient(
        self,
        patient_identifier: str,
    ) -> dict[str, Any]:
        ...

    def query_clinical_data(
        self,
        patient_identifier: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ...


class MalaffiProvider:
    provider_name = "malaffi"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or timeout <= 0
        ):
            raise ValueError(
                "timeout must be a positive integer"
            )

        if endpoint is not None:
            endpoint = str(endpoint).strip()

            if not endpoint:
                endpoint = None

        self.endpoint = endpoint
        self.timeout = timeout

    def submit_patient(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_payload(payload)

        return self._send(
            operation="patient_submission",
            payload=payload,
        )

    def submit_clinical_data(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_payload(payload)

        return self._send(
            operation="clinical_data_submission",
            payload=payload,
        )

    def submit_clinical_document(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_payload(payload)

        return self._send(
            operation="clinical_document_submission",
            payload=payload,
        )

    def query_patient(
        self,
        patient_identifier: str,
    ) -> dict[str, Any]:
        patient_identifier = (
            self._validate_patient_identifier(
                patient_identifier
            )
        )

        return self._query(
            operation="patient_query",
            patient_identifier=patient_identifier,
        )

    def query_clinical_data(
        self,
        patient_identifier: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        patient_identifier = (
            self._validate_patient_identifier(
                patient_identifier
            )
        )

        filters = self._validate_filters(
            filters
        )

        return self._query(
            operation="clinical_data_query",
            patient_identifier=patient_identifier,
            filters=filters,
        )

    @staticmethod
    def _validate_payload(
        payload: dict[str, Any],
    ) -> None:
        if not isinstance(payload, dict):
            raise ValueError(
                "payload must be a dictionary"
            )

    @staticmethod
    def _validate_patient_identifier(
        patient_identifier: str,
    ) -> str:
        if patient_identifier is None:
            raise ValueError(
                "patient_identifier is required"
            )

        if not isinstance(
            patient_identifier,
            str,
        ):
            raise ValueError(
                "patient_identifier must be a string"
            )

        patient_identifier = patient_identifier.strip()

        if not patient_identifier:
            raise ValueError(
                "patient_identifier is required"
            )

        return patient_identifier

    @staticmethod
    def _validate_filters(
        filters: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if filters is not None and not isinstance(
            filters,
            dict,
        ):
            raise ValueError(
                "filters must be a dictionary"
            )

        return filters

    @staticmethod
    def _validate_operation(
        operation: str,
    ) -> str:
        if not isinstance(
            operation,
            str,
        ):
            raise ValueError(
                "operation must be a string"
            )

        operation = operation.strip()

        if not operation:
            raise ValueError(
                "operation is required"
            )

        return operation

    def _send(
        self,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        operation = self._validate_operation(
            operation
        )

        self._validate_payload(
            payload
        )

        if self.endpoint is None:
            raise NotImplementedError(
                "Malaffi transport is not configured "
                f"for operation '{operation}'"
            )

        raise NotImplementedError(
            "Malaffi transport is not implemented "
            f"for operation '{operation}'"
        )

    def _query(
        self,
        operation: str,
        patient_identifier: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        operation = self._validate_operation(
            operation
        )

        patient_identifier = (
            self._validate_patient_identifier(
                patient_identifier
            )
        )

        filters = self._validate_filters(
            filters
        )

        if self.endpoint is None:
            raise NotImplementedError(
                "Malaffi query transport is not configured "
                f"for operation '{operation}'"
            )

        raise NotImplementedError(
            "Malaffi query transport is not implemented "
            f"for operation '{operation}'"
        )