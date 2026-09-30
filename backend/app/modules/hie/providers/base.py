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