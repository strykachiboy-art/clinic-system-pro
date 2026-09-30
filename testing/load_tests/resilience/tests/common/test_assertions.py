from __future__ import annotations

from unittest.mock import Mock

import pytest

from load_tests.resilience.common import assertions


def test_assert_http_status_passes_for_expected_status():
    response = Mock()
    response.status_code = 200

    assertions.assert_http_status(
        response,
        200,
    )


def test_assert_http_status_fails_for_unexpected_status():
    response = Mock()
    response.status_code = 500

    with pytest.raises(
        AssertionError,
        match="Expected HTTP 200, got 500",
    ):
        assertions.assert_http_status(
            response,
            200,
        )


def test_assert_json_object_returns_response_json():
    response = Mock()

    body = {
        "success": True,
        "data": {
            "id": 1,
        },
    }

    response.json.return_value = body

    result = assertions.assert_json_object(
        response
    )

    assert result == body


def test_assert_json_object_rejects_invalid_json():
    response = Mock()

    response.json.side_effect = ValueError(
        "invalid json"
    )

    with pytest.raises(
        AssertionError,
        match="Response body is not valid JSON",
    ):
        assertions.assert_json_object(
            response
        )


@pytest.mark.parametrize(
    "value",
    [
        [],
        (),
        "invalid",
        123,
        True,
        None,
    ],
)
def test_assert_json_object_rejects_non_object_json(
    value,
):
    response = Mock()
    response.json.return_value = value

    with pytest.raises(
        AssertionError,
        match="Expected JSON object response",
    ):
        assertions.assert_json_object(
            response
        )


def test_assert_success_response_accepts_true():
    response = Mock()

    response.json.return_value = {
        "success": True,
        "data": {},
    }

    result = assertions.assert_success_response(
        response
    )

    assert result["success"] is True


def test_assert_success_response_accepts_expected_false():
    response = Mock()

    response.json.return_value = {
        "success": False,
        "error": {
            "code": "expected_failure",
        },
    }

    result = assertions.assert_success_response(
        response,
        expected=False,
    )

    assert result["success"] is False


def test_assert_success_response_rejects_unexpected_success_value():
    response = Mock()

    response.json.return_value = {
        "success": False,
    }

    with pytest.raises(
        AssertionError,
        match="Expected success=True, got False",
    ):
        assertions.assert_success_response(
            response
        )


def test_assert_socket_connected_passes_when_connected():
    client = Mock()

    client.is_connected.return_value = True

    assertions.assert_socket_connected(
        client,
        namespace="/chat",
    )

    client.is_connected.assert_called_once_with(
        "/chat"
    )


def test_assert_socket_connected_fails_when_disconnected():
    client = Mock()

    client.is_connected.return_value = False

    with pytest.raises(
        AssertionError,
        match="Socket is not connected to /chat",
    ):
        assertions.assert_socket_connected(
            client,
            namespace="/chat",
        )


def test_assert_socket_disconnected_passes_when_disconnected():
    client = Mock()

    client.is_connected.return_value = False

    assertions.assert_socket_disconnected(
        client,
        namespace="/chat",
    )

    client.is_connected.assert_called_once_with(
        "/chat"
    )


def test_assert_socket_disconnected_fails_when_connected():
    client = Mock()

    client.is_connected.return_value = True

    with pytest.raises(
        AssertionError,
        match="Socket is still connected to /chat",
    ):
        assertions.assert_socket_disconnected(
            client,
            namespace="/chat",
        )


def test_assert_event_present_returns_matching_event():
    events = [
        {
            "name": "chat.connected",
            "args": [],
        },
        {
            "name": "conversation.joined",
            "args": [
                {
                    "conversation_id": 42,
                }
            ],
        },
    ]

    result = assertions.assert_event_present(
        events,
        "conversation.joined",
    )

    assert result["name"] == "conversation.joined"
    assert result["args"][0]["conversation_id"] == 42


def test_assert_event_present_fails_when_event_is_missing():
    events = [
        {
            "name": "chat.connected",
            "args": [],
        }
    ]

    with pytest.raises(
        AssertionError,
        match="Expected event 'conversation.joined'",
    ):
        assertions.assert_event_present(
            events,
            "conversation.joined",
        )


def test_assert_event_count_passes():
    events = [
        {
            "name": "message.created",
            "args": [],
        },
        {
            "name": "message.created",
            "args": [],
        },
        {
            "name": "chat.connected",
            "args": [],
        },
    ]

    assertions.assert_event_count(
        events,
        "message.created",
        2,
    )


def test_assert_event_count_fails_on_wrong_count():
    events = [
        {
            "name": "message.created",
            "args": [],
        }
    ]

    with pytest.raises(
        AssertionError,
        match="Expected 2 occurrences of 'message.created', got 1",
    ):
        assertions.assert_event_count(
            events,
            "message.created",
            2,
        )


def test_assert_no_duplicate_values_passes():
    assertions.assert_no_duplicate_values(
        [1, 2, 3]
    )


def test_assert_no_duplicate_values_fails():
    with pytest.raises(
        AssertionError,
        match="Duplicate values detected",
    ):
        assertions.assert_no_duplicate_values(
            [1, 2, 2, 3]
        )


def test_assert_no_duplicate_values_supports_custom_label():
    with pytest.raises(
        AssertionError,
        match="Duplicate message IDs detected",
    ):
        assertions.assert_no_duplicate_values(
            [10, 10],
            label="message IDs",
        )


def test_assert_unique_entity_ids_passes():
    entities = [
        {
            "id": 1,
        },
        {
            "id": 2,
        },
        {
            "id": 3,
        },
    ]

    assertions.assert_unique_entity_ids(
        entities
    )


def test_assert_unique_entity_ids_rejects_duplicates():
    entities = [
        {
            "id": 1,
        },
        {
            "id": 1,
        },
    ]

    with pytest.raises(
        AssertionError,
        match="Duplicate id values detected",
    ):
        assertions.assert_unique_entity_ids(
            entities
        )


def test_assert_unique_entity_ids_rejects_missing_ids():
    entities = [
        {
            "id": 1,
        },
        {
            "name": "missing",
        },
    ]

    with pytest.raises(
        AssertionError,
        match="Missing 'id' in entities",
    ):
        assertions.assert_unique_entity_ids(
            entities
        )


def test_assert_unique_entity_ids_supports_custom_key():
    entities = [
        {
            "message_id": 100,
        },
        {
            "message_id": 101,
        },
    ]

    assertions.assert_unique_entity_ids(
        entities,
        key="message_id",
    )