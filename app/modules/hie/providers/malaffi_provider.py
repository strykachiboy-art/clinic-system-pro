from typing import Any, Optional, Protocol


class HIEProvider(Protocol):
    """
    Contract implemented by external Health Information Exchange providers.

    The service layer depends on this interface instead of depending directly
    on Malaffi, HL7, HTTP, or any other transport implementation.
    """

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
    """
    Malaffi HIE integration adapter.

    This class is responsible only for communication with the external
    Malaffi HIE layer.

    It must NOT:
        - query SQLAlchemy models
        - modify clinic or patient records
        - consume AI credits
        - create HIESubmission records
        - contain application business rules
        - perform authorization checks

    Those responsibilities belong to the HIE service layer.

    The concrete transport implementation will be added once the approved
    Malaffi onboarding, authentication, and integration specifications
    are available.
    """

    provider_name = "malaffi"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        if timeout <= 0:
            raise ValueError(
                "timeout must be greater than zero"
            )

        if endpoint is not None:
            endpoint = str(endpoint).strip()

            if not endpoint:
                endpoint = None

        self.endpoint = endpoint
        self.timeout = timeout

    # ==================================================================
    # OUTBOUND SUBMISSIONS
    # ==================================================================

    def submit_patient(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Submit patient demographic information to Malaffi.

        The final implementation will transform the internal payload into
        the required Malaffi message format and send it through the
        approved integration channel.
        """
        self._validate_payload(payload)

        return self._send(
            operation="patient_submission",
            payload=payload,
        )

    def submit_clinical_data(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Submit clinical information to Malaffi.

        This may eventually cover supported domains such as:
            - encounters
            - diagnoses/problems
            - allergies
            - medications
            - procedures
            - laboratory results
            - vital signs
            - appointments
            - other supported clinical data
        """
        self._validate_payload(payload)

        return self._send(
            operation="clinical_data_submission",
            payload=payload,
        )

    def submit_clinical_document(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Submit a clinical document to Malaffi.
        """
        self._validate_payload(payload)

        return self._send(
            operation="clinical_document_submission",
            payload=payload,
        )

    # ==================================================================
    # INBOUND QUERIES
    # ==================================================================

    def query_patient(
        self,
        patient_identifier: str,
    ) -> dict[str, Any]:
        """
        Query Malaffi for a patient.

        The exact query mechanism depends on the approved Malaffi
        integration interface and credentials provided during onboarding.
        """
        patient_identifier = self._validate_patient_identifier(
            patient_identifier
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
        """
        Query clinical information for a patient from Malaffi.
        """
        patient_identifier = self._validate_patient_identifier(
            patient_identifier
        )

        if filters is not None and not isinstance(
            filters,
            dict,
        ):
            raise ValueError(
                "filters must be a dictionary"
            )

        return self._query(
            operation="clinical_data_query",
            patient_identifier=patient_identifier,
            filters=filters,
        )

    # ==================================================================
    # VALIDATION HELPERS
    # ==================================================================

    @staticmethod
    def _validate_payload(
        payload: dict[str, Any],
    ) -> None:
        """
        Validate the basic transport payload contract.

        Detailed payload/business validation belongs in the service or
        provider-specific transformation layer.
        """
        if not isinstance(payload, dict):
            raise ValueError(
                "payload must be a dictionary"
            )

    @staticmethod
    def _validate_patient_identifier(
        patient_identifier: str,
    ) -> str:
        """
        Normalize and validate a patient identifier before transport.
        """
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

    # ==================================================================
    # TRANSPORT BOUNDARIES
    # ==================================================================

    def _send(
        self,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Transport boundary for outbound Malaffi messages.

        The actual Malaffi transport will be implemented here once the
        approved integration specifications and connectivity details
        are available.

        Keeping transport isolated here means the HIE service does not
        need to change when the actual HL7/network implementation is
        introduced.
        """
        self._validate_payload(payload)

        if not operation or not operation.strip():
            raise ValueError(
                "operation is required"
            )

        if self.endpoint is None:
            raise NotImplementedError(
                f"Malaffi transport is not configured for operation "
                f"'{operation}'"
            )

        raise NotImplementedError(
            f"Malaffi transport is not implemented for operation "
            f"'{operation}'"
        )

    def _query(
        self,
        operation: str,
        patient_identifier: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Transport boundary for inbound Malaffi queries.

        The concrete implementation will be added when the approved
        Malaffi query/integration interface is available.
        """
        patient_identifier = self._validate_patient_identifier(
            patient_identifier
        )

        if filters is not None and not isinstance(
            filters,
            dict,
        ):
            raise ValueError(
                "filters must be a dictionary"
            )

        if not operation or not operation.strip():
            raise ValueError(
                "operation is required"
            )

        if self.endpoint is None:
            raise NotImplementedError(
                f"Malaffi query transport is not configured for operation "
                f"'{operation}'"
            )

        raise NotImplementedError(
            f"Malaffi query transport is not implemented for operation "
            f"'{operation}'"
        )