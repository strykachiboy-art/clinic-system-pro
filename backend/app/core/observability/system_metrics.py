from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any

import psutil


SYSTEM_METRICS_STATE_KEY = (
    "_clinic_system_metrics"
)


def _to_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _collect_process_metrics(
    process: psutil.Process,
) -> dict[str, Any]:
    process_pid = getattr(
        process,
        "pid",
        os.getpid(),
    )

    try:
        memory = process.memory_info()

        return {
            "available": True,
            "pid": process_pid,
            "cpu_percent": _to_float(
                process.cpu_percent(
                    interval=None
                )
            ),
            "rss_bytes": _to_int(
                memory.rss
            ),
            "vms_bytes": _to_int(
                memory.vms
            ),
            "memory_percent": _to_float(
                process.memory_percent()
            ),
            "thread_count": _to_int(
                process.num_threads()
            ),
            "open_file_count": _safe_open_file_count(
                process
            ),
        }

    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        psutil.ZombieProcess,
    ):
        return {
            "available": False,
            "pid": process_pid,
            "cpu_percent": 0.0,
            "rss_bytes": 0,
            "vms_bytes": 0,
            "memory_percent": 0.0,
            "thread_count": 0,
            "open_file_count": 0,
        }


def _safe_open_file_count(
    process: psutil.Process,
) -> int:
    try:
        return len(
            process.open_files()
        )
    except (
        psutil.NoSuchProcess,
        psutil.AccessDenied,
        psutil.ZombieProcess,
    ):
        return 0


def _collect_load_average() -> dict[str, float] | None:
    try:
        values = psutil.getloadavg()

        return {
            "one_minute": _to_float(
                values[0]
            ),
            "five_minutes": _to_float(
                values[1]
            ),
            "fifteen_minutes": _to_float(
                values[2]
            ),
        }

    except (
        AttributeError,
        OSError,
    ):
        return None


def _collect_network_metrics() -> dict[str, Any]:
    aggregate = psutil.net_io_counters()

    if aggregate is None:
        return {
            "available": False,
            "bytes_sent": 0,
            "bytes_received": 0,
            "packets_sent": 0,
            "packets_received": 0,
            "errors_in": 0,
            "errors_out": 0,
            "drops_in": 0,
            "drops_out": 0,
            "interfaces": {},
        }

    interfaces = {}

    try:
        per_interface = (
            psutil.net_io_counters(
                pernic=True
            )
        )

        for name, stats in (
            per_interface.items()
        ):
            interfaces[name] = {
                "bytes_sent": _to_int(
                    stats.bytes_sent
                ),
                "bytes_received": _to_int(
                    stats.bytes_recv
                ),
                "packets_sent": _to_int(
                    stats.packets_sent
                ),
                "packets_received": _to_int(
                    stats.packets_recv
                ),
                "errors_in": _to_int(
                    stats.errin
                ),
                "errors_out": _to_int(
                    stats.errout
                ),
                "drops_in": _to_int(
                    stats.dropin
                ),
                "drops_out": _to_int(
                    stats.dropout
                ),
            }

    except OSError:
        interfaces = {}

    return {
        "available": True,
        "bytes_sent": _to_int(
            aggregate.bytes_sent
        ),
        "bytes_received": _to_int(
            aggregate.bytes_recv
        ),
        "packets_sent": _to_int(
            aggregate.packets_sent
        ),
        "packets_received": _to_int(
            aggregate.packets_recv
        ),
        "errors_in": _to_int(
            aggregate.errin
        ),
        "errors_out": _to_int(
            aggregate.errout
        ),
        "drops_in": _to_int(
            aggregate.dropin
        ),
        "drops_out": _to_int(
            aggregate.dropout
        ),
        "interfaces": interfaces,
    }


def collect_system_metrics(
    *,
    process: psutil.Process | None = None,
    cpu_interval: float | None = 0.1,
) -> dict[str, Any]:
    if cpu_interval is not None and cpu_interval < 0:
        raise ValueError(
            "cpu_interval cannot be negative"
        )

    if process is None:
        process = psutil.Process()

    cpu_percent = _to_float(
        psutil.cpu_percent(
            interval=cpu_interval
        )
    )

    virtual_memory = psutil.virtual_memory()
    swap_memory = psutil.swap_memory()

    load_average = (
        _collect_load_average()
    )

    network = (
        _collect_network_metrics()
    )

    process_metrics = (
        _collect_process_metrics(
            process
        )
    )

    result: dict[str, Any] = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "healthy": True,
        "hostname": socket.gethostname(),
        "cpu": {
            "percent": cpu_percent,
            "logical_count": _to_int(
                psutil.cpu_count(
                    logical=True
                )
            ),
            "physical_count": _to_int(
                psutil.cpu_count(
                    logical=False
                )
            ),
        },
        "memory": {
            "total_bytes": _to_int(
                virtual_memory.total
            ),
            "available_bytes": _to_int(
                virtual_memory.available
            ),
            "used_bytes": _to_int(
                virtual_memory.used
            ),
            "free_bytes": _to_int(
                virtual_memory.free
            ),
            "percent": _to_float(
                virtual_memory.percent
            ),
        },
        "swap": {
            "total_bytes": _to_int(
                swap_memory.total
            ),
            "used_bytes": _to_int(
                swap_memory.used
            ),
            "free_bytes": _to_int(
                swap_memory.free
            ),
            "percent": _to_float(
                swap_memory.percent
            ),
        },
        "process": process_metrics,
        "network": network,
        "load_average": load_average,
    }

    return result
