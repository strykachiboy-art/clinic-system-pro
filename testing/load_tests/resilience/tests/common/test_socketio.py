from __future__ import annotations

from unittest.mock import Mock

import pytest

from load_tests.resilience.common import socketio


def test_connect_socket_uses_socketio_test_client():
    app = Mock()
    socketio_extension = Mock()
    expected_client = Mock()

    socketio_extension.test_client.return_value = (
        expected_client
    )

    auth = {
        "access_token": "test-token",
    }

    result = socketio.connect_socket(
        app,
        socketio_extension,
        auth=auth,
        namespace="/chat",
    )

    assert result is expected_client

    socketio_extension.test_client.assert_called_once_with(
        app,
        namespace="/chat",
        auth=auth,
    )


def test_connect_socket_supports_missing_auth():
    app = Mock()
    socketio_extension = Mock()

    socketio_extension.test_client.return_value = (
        Mock()
    )

    socketio.connect_socket(
        app,
        socketio_extension,
    )

    socketio_extension.test_client.assert_called_once_with(
        app,
        namespace="/chat",
        auth=None,
    )


def test_is_connected_delegates_to_client():
    client = Mock()

    client.is_connected.return_value = True

    result = socketio.is_connected(
        client,
        namespace="/chat",
    )

    assert result is True

    client.is_connected.assert_called_once_with(
        "/chat",
    )


def test_is_connected_returns_false_when_client_is_disconnected():
    client = Mock()

    client.is_connected.return_value = False

    result = socketio.is_connected(
        client,
        namespace="/chat",
    )

    assert result is False


def test_emit_event_sends_event_and_payload():
    client = Mock()

    payload = {
        "conversation_id": 10,
    }

    socketio.emit_event(
        client,
        "conversation.join",
        payload,
        namespace="/chat",
    )

    client.emit.assert_called_once_with(
        "conversation.join",
        payload,
        namespace="/chat",
    )


def test_emit_event_supports_none_payload():
    client = Mock()

    socketio.emit_event(
        client,
        "ping",
    )

    client.emit.assert_called_once_with(
        "ping",
        None,
        namespace="/chat",
    )


def test_receive_events_returns_received_events_as_list():
    client = Mock()

    events = [
        {
            "name": "chat.connected",
            "args": [],
        },
        {
            "name": "conversation.joined",
            "args": [
                {
                    "conversation_id": 10,
                }
            ],
        },
    ]

    client.get_received.return_value = events

    result = socketio.receive_events(
        client,
        namespace="/chat",
    )

    assert result == events
    assert isinstance(result, list)

    client.get_received.assert_called_once_with(
        "/chat",
    )


def test_wait_for_event_returns_matching_event():
    client = Mock()

    client.get_received.return_value = [
        {
            "name": "chat.connected",
            "args": [
                {
                    "user_id": 1,
                }
            ],
        }
    ]

    result = socketio.wait_for_event(
        client,
        "chat.connected",
        timeout_seconds=1,
        poll_interval_seconds=0.01,
    )

    assert result is not None
    assert result["name"] == "chat.connected"
    assert result["args"][0]["user_id"] == 1


def test_wait_for_event_ignores_non_matching_events():
    client = Mock()

    client.get_received.side_effect = [
        [
            {
                "name": "other.event",
                "args": [],
            }
        ],
        [
            {
                "name": "target.event",
                "args": [
                    {
                        "value": 123,
                    }
                ],
            }
        ],
    ]

    result = socketio.wait_for_event(
        client,
        "target.event",
        timeout_seconds=1,
        poll_interval_seconds=0.001,
    )

    assert result is not None
    assert result["name"] == "target.event"
    assert result["args"][0]["value"] == 123

    assert client.get_received.call_count == 2


def test_wait_for_event_returns_none_after_timeout(
    monkeypatch,
):
    client = Mock()

    client.get_received.return_value = []

    clock = {"now": 0.0}

    def fake_monotonic():
        clock["now"] += 0.01
        return clock["now"]

    monkeypatch.setattr(
        socketio,
        "monotonic",
        fake_monotonic,
    )

    monkeypatch.setattr(
        socketio,
        "sleep",
        lambda seconds: None,
    )

    result = socketio.wait_for_event(
        client,
        "missing.event",
        timeout_seconds=0.05,
        poll_interval_seconds=0.01,
    )

    assert result is None

    assert client.get_received.call_count >= 1


@pytest.mark.parametrize(
    "timeout_seconds",
    [
        0,
        -1,
        -0.5,
    ],
)
def test_wait_for_event_rejects_invalid_timeout(
    timeout_seconds,
):
    client = Mock()

    with pytest.raises(
        ValueError,
        match="timeout_seconds must be greater than zero",
    ):
        socketio.wait_for_event(
            client,
            "event",
            timeout_seconds=timeout_seconds,
        )


@pytest.mark.parametrize(
    "poll_interval_seconds",
    [
        0,
        -1,
        -0.5,
    ],
)
def test_wait_for_event_rejects_invalid_poll_interval(
    poll_interval_seconds,
):
    client = Mock()

    with pytest.raises(
        ValueError,
        match="poll_interval_seconds must be greater than zero",
    ):
        socketio.wait_for_event(
            client,
            "event",
            poll_interval_seconds=poll_interval_seconds,
        )


def test_disconnect_socket_delegates_to_client():
    client = Mock()

    socketio.disconnect_socket(
        client,
        namespace="/chat",
    )

    client.disconnect.assert_called_once_with(
        namespace="/chat",
    )


def test_reconnect_socket_creates_new_client():
    app = Mock()
    socketio_extension = Mock()
    expected_client = Mock()

    socketio_extension.test_client.return_value = (
        expected_client
    )

    auth = {
        "access_token": "test-token",
    }

    result = socketio.reconnect_socket(
        app,
        socketio_extension,
        auth=auth,
        namespace="/chat",
    )

    assert result is expected_client

    socketio_extension.test_client.assert_called_once_with(
        app,
        namespace="/chat",
        auth=auth,
    )


def test_clear_received_events_returns_received_events():
    client = Mock()

    events = [
        {
            "name": "chat.connected",
            "args": [],
        }
    ]

    client.get_received.return_value = events

    result = socketio.clear_received_events(
        client,
        namespace="/chat",
    )

    assert result == events

    client.get_received.assert_called_once_with(
        "/chat",
    )


def test_default_namespace_is_chat():
    assert socketio.DEFAULT_NAMESPACE == "/chat"