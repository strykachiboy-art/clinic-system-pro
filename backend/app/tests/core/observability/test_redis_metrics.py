from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.core.observability import redis_metrics


def _redis_mock() -> Mock:
    redis = Mock()

    redis.info.side_effect = [
        {
            "redis_version": "7.2.4",
            "uptime_in_seconds": 3600,
            "keyspace_hits": 800,
            "keyspace_misses": 200,
            "db0": {
                "keys": 100,
                "expires": 40,
                "expired": 12,
            },
            "db1": {
                "keys": 50,
                "expires": 10,
                "expired": 3,
            },
        },
        {
            "used_memory": 1024,
            "used_memory_peak": 2048,
            "used_memory_rss": 4096,
            "mem_fragmentation_ratio": 1.25,
        },
        {
            "connected_clients": 12,
            "blocked_clients": 2,
            "tracking_clients": 1,
        },
        {
            "instantaneous_ops_per_sec": 75,
            "total_commands_processed": 10000,
            "total_connections_received": 500,
            "rejected_connections": 3,
            "evicted_keys": 4,
            "expired_keys": 15,
            "keyspace_hits": 800,
            "keyspace_misses": 200,
            "total_net_input_bytes": 100000,
            "total_net_output_bytes": 200000,
            "total_reads_processed": 3000,
            "total_writes_processed": 1800,
            "instantaneous_input_kbps": 12.5,
            "instantaneous_output_kbps": 25.0,
        },
        {
            "used_cpu_sys": 12.5,
            "used_cpu_user": 8.75,
            "used_cpu_sys_children": 1.5,
            "used_cpu_user_children": 0.75,
        },
    ]

    return redis


def test_collect_redis_metrics_returns_core_metrics():
    redis = _redis_mock()

    result = redis_metrics.collect_redis_metrics(
        client=redis,
    )

    assert result["healthy"] is True
    assert result["redis_version"] == "7.2.4"
    assert result["uptime_seconds"] == 3600

    assert result["connected_clients"] == 12
    assert result["blocked_clients"] == 2
    assert result["tracking_clients"] == 1

    assert result["used_memory_bytes"] == 1024
    assert result["used_memory_peak_bytes"] == 2048
    assert result["used_memory_rss_bytes"] == 4096
    assert result["memory_fragmentation_ratio"] == 1.25

    assert result["instantaneous_ops_per_sec"] == 75
    assert result["total_commands_processed"] == 10000
    assert result["total_connections_received"] == 500
    assert result["rejected_connections"] == 3
    assert result["evicted_keys"] == 4
    assert result["expired_keys"] == 15


def test_collect_redis_metrics_calculates_cache_hit_ratio():
    redis = _redis_mock()

    result = redis_metrics.collect_redis_metrics(
        client=redis,
    )

    assert result["keyspace_hits"] == 800
    assert result["keyspace_misses"] == 200
    assert result["cache_hit_ratio"] == pytest.approx(
        0.8
    )


def test_collect_redis_metrics_aggregates_keyspace():
    redis = _redis_mock()

    result = redis_metrics.collect_redis_metrics(
        client=redis,
    )

    assert result["key_count"] == 150
    assert result["expiring_key_count"] == 50
    assert result["expired_key_count"] == 15


def test_collect_redis_metrics_returns_network_metrics():
    redis = _redis_mock()

    result = redis_metrics.collect_redis_metrics(
        client=redis,
    )

    assert result["total_net_input_bytes"] == 100000
    assert result["total_net_output_bytes"] == 200000
    assert result["total_reads_processed"] == 3000
    assert result["total_writes_processed"] == 1800
    assert result["instantaneous_input_kbps"] == 12.5
    assert result["instantaneous_output_kbps"] == 25.0


def test_collect_redis_metrics_returns_cpu_metrics():
    redis = _redis_mock()

    result = redis_metrics.collect_redis_metrics(
        client=redis,
    )

    assert result["used_cpu_sys_seconds"] == 12.5
    assert result["used_cpu_user_seconds"] == 8.75
    assert (
        result["used_cpu_sys_children_seconds"]
        == 1.5
    )
    assert (
        result["used_cpu_user_children_seconds"]
        == 0.75
    )


def test_collect_redis_metrics_can_count_key_prefixes():
    redis = _redis_mock()

    redis.scan_iter.side_effect = [
        iter(
            [
                "auth:revoked:1",
                "auth:revoked:2",
            ]
        ),
        iter(
            [
                "session:1",
            ]
        ),
    ]

    result = redis_metrics.collect_redis_metrics(
        client=redis,
        key_prefixes=[
            "auth:revoked:",
            "session:",
        ],
    )

    assert result["key_prefix_counts"] == {
        "auth:revoked:": 2,
        "session:": 1,
    }


def test_count_keys_by_prefix_requires_initialized_client(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.extensions.redis_client",
        None,
    )

    with pytest.raises(RuntimeError):
        redis_metrics.count_keys_by_prefix(
            ["auth:revoked:"],
            client=None,
        )


def test_count_keys_by_prefix_rejects_invalid_scan_count():
    redis = Mock()

    with pytest.raises(ValueError):
        redis_metrics.count_keys_by_prefix(
            ["auth:revoked:"],
            client=redis,
            scan_count=0,
        )


def test_count_keys_by_prefix_rejects_empty_prefix():
    redis = Mock()

    with pytest.raises(ValueError):
        redis_metrics.count_keys_by_prefix(
            [""],
            client=redis,
        )