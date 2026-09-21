from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.observability import (
    system_metrics,
)


def _virtual_memory():
    return SimpleNamespace(
        total=16000,
        available=10000,
        used=6000,
        free=10000,
        percent=37.5,
    )


def _swap_memory():
    return SimpleNamespace(
        total=8000,
        used=1000,
        free=7000,
        percent=12.5,
    )


def _network():
    return SimpleNamespace(
        bytes_sent=100000,
        bytes_recv=200000,
        packets_sent=1000,
        packets_recv=2000,
        errin=2,
        errout=3,
        dropin=4,
        dropout=5,
    )


def test_collect_system_metrics_returns_host_metrics(
    monkeypatch,
):
    process = Mock()
    process.pid = 1234
    process.memory_info.return_value = (
        SimpleNamespace(
            rss=4000,
            vms=8000,
        )
    )
    process.cpu_percent.return_value = 5.5
    process.memory_percent.return_value = 10.0
    process.num_threads.return_value = 8
    process.open_files.return_value = [
        "one",
        "two",
    ]

    monkeypatch.setattr(
        system_metrics.psutil,
        "Process",
        lambda: process,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "cpu_percent",
        lambda interval=None: 42.5,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "cpu_count",
        lambda logical=True: (
            8 if logical else 4
        ),
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "virtual_memory",
        _virtual_memory,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "swap_memory",
        _swap_memory,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "net_io_counters",
        lambda pernic=False: (
            {
                "Ethernet": _network(),
            }
            if pernic
            else _network()
        ),
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "getloadavg",
        lambda: (
            1.0,
            2.0,
            3.0,
        ),
    )

    result = (
        system_metrics.collect_system_metrics(
            cpu_interval=0
        )
    )

    assert result["healthy"] is True

    assert (
        result["cpu"]["percent"]
        == 42.5
    )

    assert (
        result["cpu"]["logical_count"]
        == 8
    )

    assert (
        result["cpu"]["physical_count"]
        == 4
    )

    assert (
        result["memory"]["total_bytes"]
        == 16000
    )

    assert (
        result["memory"]["used_bytes"]
        == 6000
    )

    assert (
        result["memory"]["percent"]
        == 37.5
    )

    assert (
        result["swap"]["used_bytes"]
        == 1000
    )

    assert (
        result["swap"]["percent"]
        == 12.5
    )

    assert (
        result["process"]["pid"]
        == 1234
    )

    assert (
        result["process"]["cpu_percent"]
        == 5.5
    )

    assert (
        result["process"]["rss_bytes"]
        == 4000
    )

    assert (
        result["process"]["thread_count"]
        == 8
    )

    assert (
        result["process"]["open_file_count"]
        == 2
    )


def test_collect_system_metrics_returns_network_metrics(
    monkeypatch,
):
    monkeypatch.setattr(
        system_metrics.psutil,
        "Process",
        lambda: Mock(
            pid=1,
            memory_info=Mock(
                return_value=SimpleNamespace(
                    rss=1,
                    vms=2,
                )
            ),
            cpu_percent=Mock(
                return_value=0.0
            ),
            memory_percent=Mock(
                return_value=0.0
            ),
            num_threads=Mock(
                return_value=1
            ),
            open_files=Mock(
                return_value=[]
            ),
        ),
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "cpu_percent",
        lambda interval=None: 0.0,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "cpu_count",
        lambda logical=True: 1,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "virtual_memory",
        _virtual_memory,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "swap_memory",
        _swap_memory,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "getloadavg",
        lambda: (0.0, 0.0, 0.0),
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "net_io_counters",
        lambda pernic=False: (
            {
                "Ethernet": _network(),
            }
            if pernic
            else _network()
        ),
    )

    result = (
        system_metrics.collect_system_metrics(
            cpu_interval=0
        )
    )

    network = result["network"]

    assert network["available"] is True
    assert network["bytes_sent"] == 100000
    assert network["bytes_received"] == 200000
    assert network["packets_sent"] == 1000
    assert network["packets_received"] == 2000
    assert network["errors_in"] == 2
    assert network["errors_out"] == 3
    assert network["drops_in"] == 4
    assert network["drops_out"] == 5

    assert (
        network["interfaces"]["Ethernet"][
            "bytes_received"
        ]
        == 200000
    )


def test_collect_system_metrics_returns_load_average(
    monkeypatch,
):
    monkeypatch.setattr(
        system_metrics.psutil,
        "Process",
        lambda: Mock(
            pid=1,
            memory_info=Mock(
                return_value=SimpleNamespace(
                    rss=1,
                    vms=2,
                )
            ),
            cpu_percent=Mock(
                return_value=0.0
            ),
            memory_percent=Mock(
                return_value=0.0
            ),
            num_threads=Mock(
                return_value=1
            ),
            open_files=Mock(
                return_value=[]
            ),
        ),
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "cpu_percent",
        lambda interval=None: 0.0,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "cpu_count",
        lambda logical=True: 1,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "virtual_memory",
        _virtual_memory,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "swap_memory",
        _swap_memory,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "net_io_counters",
        lambda pernic=False: None,
    )

    monkeypatch.setattr(
        system_metrics.psutil,
        "getloadavg",
        lambda: (
            1.5,
            2.5,
            3.5,
        ),
    )

    result = (
        system_metrics.collect_system_metrics(
            cpu_interval=0
        )
    )

    assert result["load_average"] == {
        "one_minute": 1.5,
        "five_minutes": 2.5,
        "fifteen_minutes": 3.5,
    }


def test_collect_system_metrics_handles_missing_load_average(
    monkeypatch,
):
    monkeypatch.setattr(
        system_metrics.psutil,
        "getloadavg",
        Mock(
            side_effect=(
                AttributeError(
                    "not supported"
                )
            )
        ),
    )

    result = (
        system_metrics._collect_load_average()
    )

    assert result is None


def test_collect_system_metrics_handles_process_failure(
    monkeypatch,
):
    process = Mock()

    process.pid = 1234

    process.memory_info.side_effect = (
        system_metrics.psutil.NoSuchProcess(
            1234
        )
    )

    result = (
        system_metrics._collect_process_metrics(
            process
        )
    )

    assert result["available"] is False
    assert result["pid"] == 1234
    assert result["rss_bytes"] == 0
    assert result["thread_count"] == 0


def test_collect_system_metrics_rejects_negative_interval():
    with pytest.raises(ValueError):
        system_metrics.collect_system_metrics(
            cpu_interval=-1
        )