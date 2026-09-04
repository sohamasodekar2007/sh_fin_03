from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import paramiko
import pytest

from packages.vps.session import VPSConnection, VPSConnectionError
from services.collector.vps.inventory import (
    _parse_lxc_ls,
    _parse_qm_list,
    _parse_virsh_list,
    collect_vps_inventory,
)
from services.collector.vps.metrics import (
    VPSMetricsError,
    _cpu_percent_from_two_samples,
    _parse_sar_cpu,
    _parse_sar_memory,
    _read_proc_stat_cpu_fields,
    backfill_from_sar,
    read_memory_used_pct,
    sample_cpu_percent,
    sysstat_available,
)

TENANT = "demo-tenant"


class FakeVPSConnection:
    """A VPSConnection-shaped test double: same .run(argv) -> (stdout,
    stderr, exit_code) interface, driven by a dict of canned responses
    keyed by the first token of the command (so tests read as "when the
    collector runs `virsh`, it gets back this text"), with no real
    paramiko session underneath."""

    def __init__(self, responses: dict[str, tuple[str, str, int]], default: tuple[str, str, int] = ("", "", 1)):
        self.responses = responses
        self.default = default
        self.calls: list[list[str]] = []

    def run(self, command: list[str], timeout: float = 30) -> tuple[str, str, int]:
        self.calls.append(command)
        key = command[0]
        # Allow more specific keys like "virsh dominfo" to override the bare "virsh" default.
        joined = " ".join(command[:2])
        if joined in self.responses:
            return self.responses[joined]
        return self.responses.get(key, self.default)


_HOST_TOTALS_RESPONSES = {
    "nproc": ("4\n", "", 0),
    "cat /proc/meminfo": ("MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n", "", 0),
    "df -PB1": ("Filesystem 1024-blocks Used Available Capacity Mounted\n/dev/sda1 107374182400 0 0 0% /\n", "", 0),
}


# ---------------------------------------------------------------------------
# packages/vps/session.py — mocked paramiko
# ---------------------------------------------------------------------------


def test_run_rejects_raw_shell_string():
    conn = VPSConnection(host="h", username="u", key_path="/nonexistent")
    with pytest.raises(TypeError):
        conn.run("cat /proc/stat")  # type: ignore[arg-type]


def test_connect_raises_when_key_file_missing():
    conn = VPSConnection(host="h", username="u", key_path="/definitely/not/a/real/path")
    with pytest.raises(VPSConnectionError):
        conn.run(["echo", "hi"])


@patch("packages.vps.session.paramiko.SSHClient")
@patch("packages.vps.session._load_private_key")
def test_run_executes_argv_and_parses_result(mock_load_key, mock_ssh_client_cls):
    mock_load_key.return_value = Mock()

    mock_client = MagicMock()
    mock_ssh_client_cls.return_value = mock_client

    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b"hello\n"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_stdin = MagicMock()
    mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    conn = VPSConnection(host="h", username="u", key_path="/nonexistent")
    stdout, stderr, exit_code = conn.run(["echo", "hello"])

    assert stdout == "hello\n"
    assert stderr == ""
    assert exit_code == 0
    # shlex.join quotes each argv token individually — never hand-built
    # shell interpolation of a value that could contain injection.
    called_command = mock_client.exec_command.call_args.args[0]
    assert called_command == "echo hello"


@patch("packages.vps.session.paramiko.SSHClient")
@patch("packages.vps.session._load_private_key")
def test_run_shell_quotes_arguments_with_special_characters(mock_load_key, mock_ssh_client_cls):
    mock_load_key.return_value = Mock()
    mock_client = MagicMock()
    mock_ssh_client_cls.return_value = mock_client
    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stdout.read.return_value = b""
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    conn = VPSConnection(host="h", username="u", key_path="/nonexistent")
    # A value that came from "the database" containing a shell metacharacter.
    dangerous_resource_id = "vm1; rm -rf /"
    conn.run(["virsh", "dominfo", dangerous_resource_id])

    called_command = mock_client.exec_command.call_args.args[0]
    # shlex.join must quote the dangerous token as a single argument, so a
    # value pulled from the database can never break out of its argument
    # position into a second shell command.
    import shlex

    assert called_command == "virsh dominfo " + shlex.quote(dangerous_resource_id)
    assert called_command.count(";") == 0 or shlex.split(called_command) == ["virsh", "dominfo", dangerous_resource_id]


@patch("packages.vps.session.paramiko.SSHClient")
@patch("packages.vps.session._load_private_key")
def test_connect_retries_up_to_three_times_then_raises(mock_load_key, mock_ssh_client_cls):
    mock_load_key.return_value = Mock()
    mock_client = MagicMock()
    mock_client.connect.side_effect = paramiko.SSHException("connection refused")
    mock_ssh_client_cls.return_value = mock_client

    conn = VPSConnection(host="h", username="u", key_path="/nonexistent")
    with pytest.raises(VPSConnectionError):
        conn.run(["echo", "hi"])

    assert mock_client.connect.call_count == 3


# ---------------------------------------------------------------------------
# services/collector/vps/inventory.py — parsers
# ---------------------------------------------------------------------------


def test_parse_virsh_list_includes_shut_off_vms():
    output = " Id   Name       State\n-----------------------------\n 1    vm1        running\n -    vm2        shut off\n"
    result = _parse_virsh_list(output)
    assert result == [("vm1", "running"), ("vm2", "shut_off")]


def test_parse_qm_list_extracts_memory_and_disk():
    output = (
        "      VMID NAME       STATUS     MEM(MB)    BOOTDISK(GB) PID\n"
        "       100 vm1        running    2048       32.00        12345\n"
    )
    rows = _parse_qm_list(output)
    assert rows == [{"VMID": "100", "NAME": "vm1", "STATUS": "running", "MEM(MB)": "2048", "BOOTDISK(GB)": "32.00", "PID": "12345"}]


def test_parse_lxc_ls_extracts_name_and_state():
    output = "NAME  STATE   AUTOSTART GROUPS IPV4      IPV6\nc1    RUNNING 1         -      10.0.3.5  -\n"
    assert _parse_lxc_ls(output) == [("c1", "running")]


# ---------------------------------------------------------------------------
# services/collector/vps/inventory.py — detection cascade, each path
# ---------------------------------------------------------------------------


def test_detection_cascade_finds_kvm_virsh_first():
    responses = {
        **_HOST_TOTALS_RESPONSES,
        "virsh list": (" Id Name State\n---\n 1 vm1 running\n", "", 0),
        "virsh dominfo": ("CPU(s):         2\nMax memory:     2097152 KiB\nState:          running\n", "", 0),
    }
    conn = FakeVPSConnection(responses)

    result = collect_vps_inventory(conn, "vps-01")

    assert result.detection_path == "kvm_virsh"
    assert len(result.resources) == 1
    r = result.resources[0]
    assert r.resource_type == "vps_vm"
    assert r.unit_id == "vm1"
    assert r.resource_id == "vps-01:vm1"
    assert r.vcpu_count == 2.0
    assert r.memory_mb == 2048.0
    assert r.host_total_vcpu == 4.0


def test_detection_cascade_falls_back_to_proxmox_qm_when_virsh_absent():
    responses = {
        **_HOST_TOTALS_RESPONSES,
        "virsh list": ("", "virsh: command not found", 127),
        "qm list": (
            "      VMID NAME       STATUS     MEM(MB)    BOOTDISK(GB) PID\n"
            "       100 vm1        running    2048       32.00        12345\n",
            "",
            0,
        ),
        "qm config": ("cores: 2\nsockets: 1\nmemory: 2048\n", "", 0),
    }
    conn = FakeVPSConnection(responses)

    result = collect_vps_inventory(conn, "vps-01")

    assert result.detection_path == "kvm_proxmox_qm"
    assert len(result.resources) == 1
    r = result.resources[0]
    assert r.unit_id == "100"
    assert r.vcpu_count == 2.0
    assert r.memory_mb == 2048.0
    assert r.disk_gb == 32.0


def test_detection_cascade_falls_back_to_lxc_when_kvm_absent():
    responses = {
        **_HOST_TOTALS_RESPONSES,
        "virsh list": ("", "not found", 127),
        "qm list": ("", "not found", 127),
        "lxc-ls -f": ("NAME  STATE   AUTOSTART GROUPS IPV4      IPV6\nc1    RUNNING 1         -      10.0.3.5  -\n", "", 0),
    }
    conn = FakeVPSConnection(responses)

    result = collect_vps_inventory(conn, "vps-01")

    assert result.detection_path == "lxc"
    assert len(result.resources) == 1
    assert result.resources[0].resource_type == "vps_container"
    assert result.resources[0].unit_id == "c1"


def test_detection_cascade_falls_back_to_docker_when_lxc_absent():
    responses = {
        **_HOST_TOTALS_RESPONSES,
        "virsh list": ("", "not found", 127),
        "qm list": ("", "not found", 127),
        "lxc-ls -f": ("", "not found", 127),
        "docker ps": ('{"ID":"abc123","Names":"web1","State":"running"}\n', "", 0),
        "docker inspect": ('{"NanoCpus":1000000000,"Memory":536870912}\n', "", 0),
    }
    conn = FakeVPSConnection(responses)

    result = collect_vps_inventory(conn, "vps-01")

    assert result.detection_path == "docker"
    assert len(result.resources) == 1
    r = result.resources[0]
    assert r.unit_id == "abc123"
    assert r.name == "web1"
    assert r.vcpu_count == 1.0  # 1_000_000_000 NanoCpus == 1 vCPU
    assert r.memory_mb == 512.0  # 536870912 bytes == 512 MiB


def test_detection_cascade_falls_back_to_host_only_when_nothing_detected():
    responses = {
        **_HOST_TOTALS_RESPONSES,
        "virsh list": ("", "not found", 127),
        "qm list": ("", "not found", 127),
        "lxc-ls -f": ("", "not found", 127),
        "docker ps": ("", "not found", 127),
    }
    conn = FakeVPSConnection(responses)

    result = collect_vps_inventory(conn, "vps-01")

    assert result.detection_path == "host_only"
    assert len(result.resources) == 1
    r = result.resources[0]
    assert r.resource_type == "vps_host"
    assert r.unit_id == "host"
    assert r.vcpu_count == 4.0  # the whole host's nproc


def test_detection_cascade_records_detection_path_for_debugging():
    """Every branch must surface which detector actually ran — this is
    the field you check first when a box you know runs containers shows
    up as a bare host."""
    responses = {**_HOST_TOTALS_RESPONSES, "virsh list": ("", "not found", 127), "qm list": ("", "not found", 127),
                 "lxc-ls -f": ("", "not found", 127), "docker ps": ("", "not found", 127)}
    conn = FakeVPSConnection(responses)
    result = collect_vps_inventory(conn, "vps-01")
    assert isinstance(result.detection_path, str) and result.detection_path


# ---------------------------------------------------------------------------
# services/collector/vps/metrics.py — the two-sample CPU bug, specifically
# ---------------------------------------------------------------------------


def test_single_proc_stat_sample_cannot_produce_a_percent_alone():
    """/proc/stat is cumulative since boot — this documents why
    sample_cpu_percent() insists on two reads, not one."""
    fields = _read_proc_stat_cpu_fields(
        FakeVPSConnection({"cat": ("cpu  1000 0 1000 8000 0 0 0 0 0 0\n", "", 0)})
    )
    assert fields == [1000, 0, 1000, 8000, 0, 0, 0, 0, 0, 0]
    # A single sample is just raw cumulative counters — turning it directly
    # into a percentage (e.g. idle / total) gives the lifetime average, not
    # current utilization; only a second sample and a delta fixes that.


def test_cpu_percent_from_two_samples_computes_the_delta_correctly():
    sample1 = [1000, 0, 1000, 8000, 0, 0, 0, 0, 0, 0]
    sample2 = [1100, 0, 1100, 8200, 0, 0, 0, 0, 0, 0]
    # total delta = 400, idle delta = 200 -> 50% busy
    assert _cpu_percent_from_two_samples(sample1, sample2) == 50.0


def test_cpu_percent_from_two_samples_zero_delta_is_zero_not_error():
    sample = [1000, 0, 1000, 8000, 0, 0, 0, 0, 0, 0]
    assert _cpu_percent_from_two_samples(sample, sample) == 0.0


def test_sample_cpu_percent_takes_exactly_two_reads_one_second_apart():
    conn = FakeVPSConnection(
        {}, default=("", "", 1)
    )
    call_log: list[list[str]] = []
    responses = iter(
        [
            "cpu  1000 0 1000 8000 0 0 0 0 0 0\n",
            "cpu  1100 0 1100 8200 0 0 0 0 0 0\n",
        ]
    )

    def fake_run(command, timeout=30):
        call_log.append(command)
        return next(responses), "", 0

    conn.run = fake_run

    with patch("services.collector.vps.metrics.time.sleep") as mock_sleep:
        percent = sample_cpu_percent(conn, sleep_seconds=1.0)

    assert percent == 50.0
    assert len(call_log) == 2  # exactly two /proc/stat reads
    mock_sleep.assert_called_once_with(1.0)


def test_read_proc_stat_raises_on_unexpected_format():
    conn = FakeVPSConnection({"cat": ("garbage output\n", "", 0)})
    with pytest.raises(VPSMetricsError):
        _read_proc_stat_cpu_fields(conn)


def test_read_memory_used_pct_computes_from_meminfo():
    conn = FakeVPSConnection(
        {"cat": ("MemTotal:       16384000 kB\nMemAvailable:    4096000 kB\n", "", 0)}
    )
    pct = read_memory_used_pct(conn)
    assert pct == pytest.approx(75.0, rel=1e-3)


def test_read_memory_used_pct_returns_none_when_unavailable_missing():
    conn = FakeVPSConnection({"cat": ("MemTotal:       16384000 kB\n", "", 0)})
    assert read_memory_used_pct(conn) is None


# ---------------------------------------------------------------------------
# sysstat / sar backfill + graceful degradation when sysstat is missing
# ---------------------------------------------------------------------------


def test_sysstat_available_true_when_directory_exists():
    conn = FakeVPSConnection({"test": ("", "", 0)})
    assert sysstat_available(conn) is True


def test_sysstat_available_false_when_directory_missing():
    conn = FakeVPSConnection({"test": ("", "", 1)})
    assert sysstat_available(conn) is False


def test_parse_sar_cpu_extracts_busy_percent_from_idle_column():
    output = (
        "Linux 5.15.0 (host) \t01/01/2026 \t_x86_64_\t(4 CPU)\n\n"
        "12:00:01 AM     CPU     %user     %nice   %system   %iowait    %steal     %idle\n"
        "12:10:01 AM     all      5.00      0.00      2.00      0.10      0.00     92.90\n"
        "12:20:01 AM     all     10.00      0.00      3.00      0.10      0.00     86.90\n"
        "Average:        all      7.50      0.00      2.50      0.10      0.00     89.90\n"
    )
    values = _parse_sar_cpu(output)
    assert values == [pytest.approx(7.1), pytest.approx(13.1)]  # 100 - %idle, "Average" line excluded


def test_parse_sar_memory_locates_memused_column_by_header_name():
    output = (
        "Linux 5.15.0 (host) \t01/01/2026 \t_x86_64_\t(4 CPU)\n\n"
        "12:00:01 AM kbmemfree kbavail kbmemused  %memused kbbuffers kbcached\n"
        "12:10:01 AM   1000000 8000000   7000000     70.00    100000  200000\n"
        "12:20:01 AM   1200000 7800000   6800000     68.00    100000  200000\n"
        "Average:      1100000 7900000   6900000     69.00    100000  200000\n"
    )
    values = _parse_sar_memory(output)
    assert values == [70.0, 68.0]


def test_backfill_from_sar_produces_metric_per_resource_with_full_sample_count():
    sar_files = "sa01\nsa02\n"
    cpu_output = (
        "Linux 5.15.0 (host)\n\n"
        "time     CPU     %idle\n"
        "00:00:01 all     90.00\n"
        "01:00:01 all     80.00\n"
        "Average: all     85.00\n"
    )
    mem_output = (
        "time kbmemfree kbavail kbmemused %memused\n"
        "00:00:01 1 2 3 60.00\n"
        "01:00:01 1 2 3 62.00\n"
        "Average: 1 2 3 61.00\n"
    )
    responses = {
        "ls /var/log/sa": (sar_files, "", 0),
        "sar -u": (cpu_output, "", 0),
        "sar -r": (mem_output, "", 0),
    }
    conn = FakeVPSConnection(responses)

    resources = [
        Mock(resource_id="vps-01:vm1"),
        Mock(resource_id="vps-01:vm2"),
    ]
    metrics, days_covered = backfill_from_sar(conn, TENANT, resources, days=14)

    assert days_covered == 2
    assert len(metrics) == 2  # one per resource, same host-level proxy data
    assert {m.resource_id for m in metrics} == {"vps-01:vm1", "vps-01:vm2"}
    for m in metrics:
        assert m.sample_count == 4  # 2 CPU datapoints per file x 2 files
        assert m.cpu_avg is not None
        assert m.mem_p95 is not None


def test_backfill_from_sar_degrades_gracefully_when_sysstat_absent():
    """No /var/log/sa listing at all (empty `ls`) -> no crash, an empty
    result the caller uses to set vps_history_warm=false."""
    conn = FakeVPSConnection({"ls /var/log/sa": ("", "No such file or directory", 2)})

    metrics, days_covered = backfill_from_sar(conn, TENANT, [Mock(resource_id="vps-01:vm1")], days=14)

    assert metrics == []
    assert days_covered == 0


def test_backfill_from_sar_degrades_gracefully_when_cpu_files_unreadable():
    responses = {
        "ls /var/log/sa": ("sa01\n", "", 0),
        "sar -u": ("", "sar: Cannot open /var/log/sa/sa01", 1),
        "sar -r": ("", "sar: Cannot open /var/log/sa/sa01", 1),
    }
    conn = FakeVPSConnection(responses)

    metrics, days_covered = backfill_from_sar(conn, TENANT, [Mock(resource_id="vps-01:vm1")], days=14)

    assert metrics == []
    assert days_covered == 0
