from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from app import extensions


REDIS_METRICS_STATE_KEY = "_clinic_redis_metrics"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _collect_keyspace_metrics(
    info: dict[str, Any],
) -> dict[str, int]:
    total_keys = 0
    total_expires = 0
    total_expired_keys = 0

    for key, value in info.items():
        if not str(key).startswith("db"):
            continue

        if not isinstance(value, dict):
            continue

        total_keys += _to_int(value.get("keys"))
        total_expires += _to_int(value.get("expires"))
        total_expired_keys += _to_int(value.get("expired"))

    return {
        "key_count": total_keys,
        "expiring_key_count": total_expires,
        "expired_key_count": total_expired_keys,
    }


def count_keys_by_prefix(
    prefixes: Iterable[str],
    *,
    client=None,
    scan_count: int = 1000,
) -> dict[str, int]:
    redis = client or extensions.redis_client

    if redis is None:
        raise RuntimeError(
            "Redis client is not initialized"
        )

    if scan_count <= 0:
        raise ValueError(
            "scan_count must be greater than zero"
        )

    results: dict[str, int] = {}

    for prefix in prefixes:
        if not isinstance(prefix, str) or not prefix:
            raise ValueError(
                "Redis key prefixes must be non-empty strings"
            )

        count = 0

        for _ in redis.scan_iter(
            match=f"{prefix}*",
            count=scan_count,
        ):
            count += 1

        results[prefix] = count

    return results


def collect_redis_metrics(
    *,
    client=None,
    key_prefixes: Iterable[str] | None = None,
) -> dict[str, Any]:
    redis = client or extensions.redis_client

    if redis is None:
        raise RuntimeError(
            "Redis client is not initialized"
        )

    started_at = datetime.now(timezone.utc)

    redis.ping()

    server_info = redis.info()
    memory_info = redis.info("memory")
    clients_info = redis.info("clients")
    stats_info = redis.info("stats")
    cpu_info = redis.info("cpu")

    keyspace_metrics = _collect_keyspace_metrics(
        server_info
    )

    keyspace_hits = _to_int(
        stats_info.get("keyspace_hits")
    )
    keyspace_misses = _to_int(
        stats_info.get("keyspace_misses")
    )

    cache_total = (
        keyspace_hits
        + keyspace_misses
    )

    cache_hit_ratio = (
        keyspace_hits / cache_total
        if cache_total > 0
        else 0.0
    )

    result: dict[str, Any] = {
        "timestamp": started_at.isoformat(),
        "healthy": True,
        "redis_version": str(
            server_info.get(
                "redis_version",
                "",
            )
        ),
        "uptime_seconds": _to_int(
            server_info.get(
                "uptime_in_seconds"
            )
        ),
        "connected_clients": _to_int(
            clients_info.get(
                "connected_clients"
            )
        ),
        "blocked_clients": _to_int(
            clients_info.get(
                "blocked_clients"
            )
        ),
        "tracking_clients": _to_int(
            clients_info.get(
                "tracking_clients"
            )
        ),
        "used_memory_bytes": _to_int(
            memory_info.get(
                "used_memory"
            )
        ),
        "used_memory_peak_bytes": _to_int(
            memory_info.get(
                "used_memory_peak"
            )
        ),
        "used_memory_rss_bytes": _to_int(
            memory_info.get(
                "used_memory_rss"
            )
        ),
        "memory_fragmentation_ratio": _to_float(
            memory_info.get(
                "mem_fragmentation_ratio"
            )
        ),
        "instantaneous_ops_per_sec": _to_int(
            stats_info.get(
                "instantaneous_ops_per_sec"
            )
        ),
        "total_commands_processed": _to_int(
            stats_info.get(
                "total_commands_processed"
            )
        ),
        "total_connections_received": _to_int(
            stats_info.get(
                "total_connections_received"
            )
        ),
        "rejected_connections": _to_int(
            stats_info.get(
                "rejected_connections"
            )
        ),
        "evicted_keys": _to_int(
            stats_info.get(
                "evicted_keys"
            )
        ),
        "expired_keys": _to_int(
            stats_info.get(
                "expired_keys"
            )
        ),
        "keyspace_hits": keyspace_hits,
        "keyspace_misses": keyspace_misses,
        "cache_hit_ratio": cache_hit_ratio,
        "total_net_input_bytes": _to_int(
            stats_info.get(
                "total_net_input_bytes"
            )
        ),
        "total_net_output_bytes": _to_int(
            stats_info.get(
                "total_net_output_bytes"
            )
        ),
        "total_reads_processed": _to_int(
            stats_info.get(
                "total_reads_processed"
            )
        ),
        "total_writes_processed": _to_int(
            stats_info.get(
                "total_writes_processed"
            )
        ),
        "instantaneous_input_kbps": _to_float(
            stats_info.get(
                "instantaneous_input_kbps"
            )
        ),
        "instantaneous_output_kbps": _to_float(
            stats_info.get(
                "instantaneous_output_kbps"
            )
        ),
        "used_cpu_sys_seconds": _to_float(
            cpu_info.get(
                "used_cpu_sys"
            )
        ),
        "used_cpu_user_seconds": _to_float(
            cpu_info.get(
                "used_cpu_user"
            )
        ),
        "used_cpu_sys_children_seconds": _to_float(
            cpu_info.get(
                "used_cpu_sys_children"
            )
        ),
        "used_cpu_user_children_seconds": _to_float(
            cpu_info.get(
                "used_cpu_user_children"
            )
        ),
        **keyspace_metrics,
    }

    if key_prefixes is not None:
        result["key_prefix_counts"] = (
            count_keys_by_prefix(
                key_prefixes,
                client=redis,
            )
        )

    return result