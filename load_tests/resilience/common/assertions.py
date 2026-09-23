from __future__ import annotations

from typing import Any


def assert_http_status(
    response: Any,
    expected_status: int,
) -> None:
    actual_status = getattr(
        response,
        "status_code",
        None,
    )

    assert actual_status == expected_status, (
        f"Expected HTTP {expected_status}, "
        f"got {actual_status}"
    )


def assert_json_object(
    response: Any,
) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise AssertionError(
            "Response body is not valid JSON"
        ) from exc

    assert isinstance(body, dict), (
        "Expected JSON object response"
    )

    return body


def assert_success_response(
    response: Any,
    *,
    expected: bool = True,
) -> dict[str, Any]:
    body = assert_json_object(
        response
    )

    actual = body.get(
        "success"
    )

    assert actual is expected, (
        f"Expected success={expected!r}, "
        f"got {actual!r}"
    )

    return body


def assert_socket_connected(
    client: Any,
    *,
    namespace: str = "/chat",
) -> None:
    assert client.is_connected(
        namespace
    ), (
        f"Socket is not connected to {namespace}"
    )


def assert_socket_disconnected(
    client: Any,
    *,
    namespace: str = "/chat",
) -> None:
    assert not client.is_connected(
        namespace
    ), (
        f"Socket is still connected to {namespace}"
    )


def assert_event_present(
    events: list[dict[str, Any]],
    event_name: str,
) -> dict[str, Any]:
    for event in events:
        if event.get("name") == event_name:
            return event

    names = [
        event.get("name")
        for event in events
    ]

    raise AssertionError(
        f"Expected event {event_name!r}; "
        f"received events={names!r}"
    )


def assert_event_count(
    events: list[dict[str, Any]],
    event_name: str,
    expected_count: int,
) -> None:
    actual_count = sum(
        1
        for event in events
        if event.get("name") == event_name
    )

    assert actual_count == expected_count, (
        f"Expected {expected_count} occurrences "
        f"of {event_name!r}, got {actual_count}"
    )


def assert_no_duplicate_values(
    values: list[Any],
    *,
    label: str = "values",
) -> None:
    assert len(values) == len(set(values)), (
        f"Duplicate {label} detected: {values!r}"
    )


def assert_unique_entity_ids(
    entities: list[dict[str, Any]],
    *,
    key: str = "id",
) -> None:
    ids = [
        entity.get(key)
        for entity in entities
    ]

    assert None not in ids, (
        f"Missing {key!r} in entities"
    )

    assert_no_duplicate_values(
        ids,
        label=f"{key} values",
    )