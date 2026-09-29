from __future__ import annotations

import inspect
from typing import Any, Optional, get_type_hints

from app.modules.hie.providers.base import HIEProvider


class FakeHIEProvider:
    def submit_patient(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return payload

    def submit_clinical_data(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return payload

    def submit_clinical_document(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return payload

    def query_patient(
        self,
        patient_identifier: str,
    ) -> dict[str, Any]:
        return {
            "patient_identifier": patient_identifier,
        }

    def query_clinical_data(
        self,
        patient_identifier: str,
        filters: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {
            "patient_identifier": patient_identifier,
            "filters": filters,
        }


def test_hie_provider_protocol_defines_required_methods():
    required_methods = {
        "submit_patient",
        "submit_clinical_data",
        "submit_clinical_document",
        "query_patient",
        "query_clinical_data",
    }

    protocol_methods = {
        name
        for name in HIEProvider.__dict__
        if not name.startswith("_")
    }

    assert required_methods.issubset(protocol_methods)


def test_hie_provider_protocol_is_structurally_implementable():
    provider: HIEProvider = FakeHIEProvider()

    assert provider.submit_patient(
        {"patient": "123"}
    ) == {"patient": "123"}

    assert provider.submit_clinical_data(
        {"diagnosis": "test"}
    ) == {"diagnosis": "test"}

    assert provider.submit_clinical_document(
        {"document": "test"}
    ) == {"document": "test"}

    assert provider.query_patient(
        "patient-123"
    ) == {
        "patient_identifier": "patient-123",
    }

    assert provider.query_clinical_data(
        "patient-123",
        {"status": "active"},
    ) == {
        "patient_identifier": "patient-123",
        "filters": {"status": "active"},
    }


def test_submit_patient_signature():
    signature = inspect.signature(
        HIEProvider.submit_patient
    )

    assert list(signature.parameters) == [
        "self",
        "payload",
    ]

    assert signature.parameters["payload"].annotation == (
        "dict[str, Any]"
    )


def test_submit_clinical_data_signature():
    signature = inspect.signature(
        HIEProvider.submit_clinical_data
    )

    assert list(signature.parameters) == [
        "self",
        "payload",
    ]

    assert signature.parameters["payload"].annotation == (
        "dict[str, Any]"
    )


def test_submit_clinical_document_signature():
    signature = inspect.signature(
        HIEProvider.submit_clinical_document
    )

    assert list(signature.parameters) == [
        "self",
        "payload",
    ]

    assert signature.parameters["payload"].annotation == (
        "dict[str, Any]"
    )


def test_query_patient_signature():
    signature = inspect.signature(
        HIEProvider.query_patient
    )

    assert list(signature.parameters) == [
        "self",
        "patient_identifier",
    ]

    assert (
        signature.parameters[
            "patient_identifier"
        ].annotation
        == "str"
    )


def test_query_clinical_data_signature():
    signature = inspect.signature(
        HIEProvider.query_clinical_data
    )

    assert list(signature.parameters) == [
        "self",
        "patient_identifier",
        "filters",
    ]

    assert (
        signature.parameters[
            "patient_identifier"
        ].annotation
        == "str"
    )

    assert (
        signature.parameters["filters"].annotation
        == "Optional[dict[str, Any]]"
    )

    assert (
        signature.parameters["filters"].default
        is None
    )


def test_hie_provider_method_return_types():
    methods = (
        "submit_patient",
        "submit_clinical_data",
        "submit_clinical_document",
        "query_patient",
        "query_clinical_data",
    )

    for method_name in methods:
        method = getattr(HIEProvider, method_name)
        hints = get_type_hints(method)

        assert hints["return"] == dict[str, Any]