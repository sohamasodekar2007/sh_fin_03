"""
VPS telemetry: live SSH sampling, sysstat (`sar`) backfill, and an optional
Prometheus/node_exporter path preferred over SSH when configured. All three
paths produce services/focus/metrics.py:ResourceMetric rows — no second
schema.

THE ONE BUG TO NOT WRITE: /proc/stat's cpu line is cumulative since boot,
so a single read gives lifetime-average utilization, not current. CPU
percent needs two reads roughly a second apart, then a delta — see
sample_cpu_percent().

LIMITATION, disclosed rather than hidden: neither `sar` nor node_exporter
know about individual VMs/containers — both report host-level CPU/memory
only. Per-unit history from either path is a proxy (the host's own
utilization, applied to every unit on it), not a real per-VM reading. Real
per-unit CPU only exists for the "live sample" path where Docker
(`docker stats`) or a two-sample virsh domstats delta can isolate one
unit — see sample_live_metrics().
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from packages.schemas.cloud_resource import VPSResourceRecord
from packages.vps.session import VPSConnection
from services.focus.metrics import ResourceMetric

logger = logging.getLogger(__name__)

DEFAULT_CPU_SAMPLE_INTERVAL_SECONDS = 1.0
DEFAULT_BACKFILL_DAYS = 14


class VPSMetricsError(Exception):
    """Raised when VPS telemetry cannot be collected at all."""


# ---------------------------------------------------------------------------
# Live SSH sampling
# ---------------------------------------------------------------------------


def _read_proc_stat_cpu_fields(conn: VPSConnection) -> list[int]:
    stdout, _stderr, exit_code = conn.run(["cat", "/proc/stat"])
    if exit_code != 0 or not stdout.strip():
        raise VPSMetricsError("failed to read /proc/stat")
    first_line = stdout.splitlines()[0]
    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        raise VPSMetricsError(f"unexpected /proc/stat format: {first_line!r}")
    return [int(x) for x in parts[1:]]


def _cpu_percent_from_two_samples(sample1: list[int], sample2: list[int]) -> float:
    """user+nice+system+... vs idle+iowait, both cumulative — the percent
    is the share of the *delta* between two points in time that wasn't
    idle, never an absolute value from one read."""
    total1, total2 = sum(sample1), sum(sample2)
    # fields: user nice system idle iowait irq softirq steal guest guest_nice
    idle1 = sample1[3] + (sample1[4] if len(sample1) > 4 else 0)
    idle2 = sample2[3] + (sample2[4] if len(sample2) > 4 else 0)

    total_delta = total2 - total1
    idle_delta = idle2 - idle1

    if total_delta <= 0:
        return 0.0
    return max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100))


def sample_cpu_percent(conn: VPSConnection, sleep_seconds: float = DEFAULT_CPU_SAMPLE_INTERVAL_SECONDS) -> float:
    """Two /proc/stat reads `sleep_seconds` apart. A single read gives
    uptime-average CPU, not current utilization — this is the most common
    bug in /proc-based collectors, so this function exists specifically to
    make getting it wrong hard to do by accident."""
    sample1 = _read_proc_stat_cpu_fields(conn)
    time.sleep(sleep_seconds)
    sample2 = _read_proc_stat_cpu_fields(conn)
    return _cpu_percent_from_two_samples(sample1, sample2)


def read_memory_used_pct(conn: VPSConnection) -> float | None:
    stdout, _stderr, exit_code = conn.run(["cat", "/proc/meminfo"])
    if exit_code != 0:
        return None

    total_kb: int | None = None
    available_kb: int | None = None
    for line in stdout.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                total_kb = int(parts[1])
        elif line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                available_kb = int(parts[1])

    if not total_kb or available_kb is None:
        return None
    return round((1 - available_kb / total_kb) * 100, 2)


def _docker_stats_cpu_percent(conn: VPSConnection, container_id: str) -> float | None:
    stdout, _stderr, exit_code = conn.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_id]
    )
    if exit_code != 0 or not stdout.strip():
        return None
    try:
        stats = json.loads(stdout.strip().splitlines()[0])
    except (json.JSONDecodeError, IndexError):
        return None
    raw = str(stats.get("CPUPerc", "")).strip().rstrip("%")
    try:
        return float(raw)
    except ValueError:
        return None


def sample_live_metrics(
    conn: VPSConnection,
    tenant_id: str,
    resources: list[VPSResourceRecord],
) -> list[ResourceMetric]:
    """
    One current-moment ResourceMetric per resource. Docker units get a real
    per-container reading (docker computes CPUPerc itself); everything else
    falls back to the host-level two-sample CPU reading as a proxy, with
    that fact recorded — see module docstring.
    """
    now = datetime.now(timezone.utc)
    host_cpu_percent = sample_cpu_percent(conn)
    host_mem_pct = read_memory_used_pct(conn)

    metrics: list[ResourceMetric] = []
    for resource in resources:
        cpu_percent = host_cpu_percent
        if resource.resource_type == "vps_container":
            docker_cpu = _docker_stats_cpu_percent(conn, resource.unit_id)
            if docker_cpu is not None:
                cpu_percent = docker_cpu

        metrics.append(
            ResourceMetric(
                resource_id=resource.resource_id,
                tenant_id=tenant_id,
                window_start=now,
                window_end=now,
                cpu_p95=cpu_percent,
                cpu_avg=cpu_percent,
                mem_p95=host_mem_pct,
                network_p95_bytes=None,
                sample_count=1,
            )
        )
    return metrics


# ---------------------------------------------------------------------------
# sysstat (`sar`) backfill — run once, on first connect
# ---------------------------------------------------------------------------


def sysstat_available(conn: VPSConnection) -> bool:
    _stdout, _stderr, exit_code = conn.run(["test", "-d", "/var/log/sa"])
    return exit_code == 0


def _list_sar_files(conn: VPSConnection) -> list[str]:
    stdout, _stderr, exit_code = conn.run(["ls", "/var/log/sa"])
    if exit_code != 0:
        return []
    # sysstat names daily files saDD (day-of-month, zero-padded); sort so
    # the most recent days come last regardless of month rollover noise.
    return sorted(name for name in stdout.split() if name.startswith("sa") and name[2:].isdigit())


def _parse_sar_cpu(output: str) -> list[float]:
    """`sar -u -f <file>` prints one line per sampled interval plus a
    trailing "Average:" summary line — %idle is always the last column."""
    values: list[float] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Linux") or "CPU" in stripped or stripped.startswith("Average"):
            continue
        fields = stripped.split()
        if len(fields) < 3:
            continue
        try:
            idle_pct = float(fields[-1])
        except ValueError:
            continue
        values.append(round(100 - idle_pct, 2))
    return values


def _parse_sar_memory(output: str) -> list[float]:
    """`sar -r -f <file>` — %memused is one of the columns; header names
    it explicitly so we locate it by name instead of a fixed index (the
    column layout has changed across sysstat versions)."""
    lines = [line for line in output.splitlines() if line.strip()]
    header_index = None
    mem_col = None
    for i, line in enumerate(lines):
        fields = line.split()
        if "%memused" in fields:
            header_index = i
            mem_col = fields.index("%memused")
            break
    if header_index is None or mem_col is None:
        return []

    values: list[float] = []
    for line in lines[header_index + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("Average"):
            continue
        fields = stripped.split()
        if len(fields) <= mem_col:
            continue
        try:
            values.append(float(fields[mem_col]))
        except ValueError:
            continue
    return values


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def backfill_from_sar(
    conn: VPSConnection,
    tenant_id: str,
    resources: list[VPSResourceRecord],
    days: int = DEFAULT_BACKFILL_DAYS,
) -> tuple[list[ResourceMetric], int]:
    """
    Returns (metrics, days_covered). Applies the host's own sar-derived
    history to every resource on it — sar has no per-VM/per-container
    visibility, so a multi-unit box's backfill is a host-level proxy, not a
    real per-unit reading (see module docstring).
    """
    sar_files = _list_sar_files(conn)[-days:]
    if not sar_files:
        return [], 0

    all_cpu: list[float] = []
    all_mem: list[float] = []
    for filename in sar_files:
        path = f"/var/log/sa/{filename}"
        cpu_out, _stderr, cpu_rc = conn.run(["sar", "-u", "-f", path])
        if cpu_rc == 0:
            all_cpu.extend(_parse_sar_cpu(cpu_out))

        mem_out, _stderr, mem_rc = conn.run(["sar", "-r", "-f", path])
        if mem_rc == 0:
            all_mem.extend(_parse_sar_memory(mem_out))

    if not all_cpu:
        return [], 0

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=len(sar_files))
    cpu_p95 = round(_percentile(all_cpu, 95), 2)
    cpu_avg = round(sum(all_cpu) / len(all_cpu), 2)
    mem_p95 = round(_percentile(all_mem, 95), 2) if all_mem else None

    metrics = [
        ResourceMetric(
            resource_id=resource.resource_id,
            tenant_id=tenant_id,
            window_start=window_start,
            window_end=now,
            cpu_p95=cpu_p95,
            cpu_avg=cpu_avg,
            mem_p95=mem_p95,
            network_p95_bytes=None,
            sample_count=len(all_cpu),
        )
        for resource in resources
    ]
    return metrics, len(sar_files)


# ---------------------------------------------------------------------------
# Prometheus / node_exporter path — preferred over SSH when configured
# ---------------------------------------------------------------------------


def _prometheus_query_range(endpoint: str, promql: str, start: datetime, end: datetime, step_seconds: int) -> list[float]:
    params = urllib.parse.urlencode(
        {
            "query": promql,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step_seconds,
        }
    )
    url = f"{endpoint.rstrip('/')}/api/v1/query_range?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("vps.metrics: Prometheus query_range failed for %s: %s", endpoint, exc)
        return []

    if payload.get("status") != "success":
        return []

    values: list[float] = []
    for series in payload.get("data", {}).get("result", []):
        for _timestamp, raw_value in series.get("values", []):
            try:
                values.append(float(raw_value))
            except (TypeError, ValueError):
                continue
    return values


def sample_prometheus_metrics(
    endpoint: str,
    tenant_id: str,
    resources: list[VPSResourceRecord],
    window_days: int = DEFAULT_BACKFILL_DAYS,
) -> list[ResourceMetric]:
    """node_exporter reports the host only (same per-unit limitation as
    sar — see module docstring), so this is applied to every resource as a
    proxy, exactly like backfill_from_sar()."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)
    step_seconds = 3600

    cpu_busy_pct = _prometheus_query_range(
        endpoint,
        '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        window_start,
        now,
        step_seconds,
    )
    mem_used_pct = _prometheus_query_range(
        endpoint,
        "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100",
        window_start,
        now,
        step_seconds,
    )

    if not cpu_busy_pct:
        return []

    cpu_p95 = round(_percentile(cpu_busy_pct, 95), 2)
    cpu_avg = round(sum(cpu_busy_pct) / len(cpu_busy_pct), 2)
    mem_p95 = round(_percentile(mem_used_pct, 95), 2) if mem_used_pct else None

    return [
        ResourceMetric(
            resource_id=resource.resource_id,
            tenant_id=tenant_id,
            window_start=window_start,
            window_end=now,
            cpu_p95=cpu_p95,
            cpu_avg=cpu_avg,
            mem_p95=mem_p95,
            network_p95_bytes=None,
            sample_count=len(cpu_busy_pct),
        )
        for resource in resources
    ]
