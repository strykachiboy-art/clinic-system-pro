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

    This class is intentionally responsible only for communication with the
    external HIE layer.

    It must NOT:
        - query SQLAlchemy models
        - modify clinic/patient records
        - consume AI credits
        - create HIESubmission records
        - contain business rules
        - perform authorization checks

    Those responsibilities belong to the HIE service layer.

    The concrete transport implementation will be added once the Malaffi
    onboarding/integration specifications are available.
    """

    provider_name = "malaffi"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def submit_patient(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Submit patient demographic information to Malaffi.

        The final implementation will transform the internal payload into
        the required Malaffi HL7 message and send it through the approved
        integration channel.
        """

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

        This may eventually cover domains such as:
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

        return self._send(
            operation="clinical_document_submission",
            payload=payload,
        )

    def query_patient(
        self,
        patient_identifier: str,
    ) -> dict[str, Any]:
        """
        Query Malaffi for a patient.

        The exact query mechanism will depend on the approved Malaffi
        integration interface and credentials provided during onboarding.
        """

        if not patient_identifier or not patient_identifier.strip():
            raise ValueError("patient_identifier is required")

        return self._query(
            operation="patient_query",
            patient_identifier=patient_identifier.strip(),
        )

    def query_clinical_data(
        self,
        patient_identifier: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Query clinical information for a patient from Malaffi.
        """

        if not patient_identifier or not patient_identifier.strip():
            raise ValueError("patient_identifier is required")

        return self._query(
            operation="clinical_data_query",
            patient_identifier=patient_identifier.strip(),
            filters=filters,
        )

    def _send(
        self,
        operation: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Transport boundary for outbound Malaffi messages.

        i will replace this method with the actual Malaffi transport once the
        integration specifications and connectivity details are available.

        Keeping transport isolated here means the HIE service does not need
        to change when the actual HL7/network implementation is introduced.
        """

        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")

        raise NotImplementedError(
            f"Malaffi transport is not configured for operation "
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

        raise NotImplementedError(
            f"Malaffi query transport is not configured for operation "
            f"'{operation}'"
        )