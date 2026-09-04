"""
VPS inventory detection cascade. Tries, in order, and stops at the first
that succeeds:

    1. KVM/Proxmox — `virsh list --all` (raw libvirt/KVM); if that's
       unavailable (Proxmox VE doesn't expose libvirtd by default — it
       talks to QEMU directly through its own `qm` tool), try `qm list`.
    2. LXC        — `lxc-ls -f`
    3. Docker     — `docker ps -a --format '{{json .}}'`
    4. Neither    — the whole host is ONE resource (resource_type "vps_host")

Which path succeeded is recorded on the result (detection_path) — this is
the first thing you check when a box you know is running containers shows
up as a bare host.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from packages.schemas.cloud_resource import VPSResourceRecord
from packages.vps.session import VPSConnection

logger = logging.getLogger(__name__)

DetectionPath = str  # "kvm_virsh" | "kvm_proxmox_qm" | "lxc" | "docker" | "host_only"


@dataclass(frozen=True)
class VPSInventoryResult:
    detection_path: DetectionPath
    resources: list[VPSResourceRecord]


def _command_available(conn: VPSConnection, argv: list[str]) -> tuple[str, int]:
    stdout, _stderr, exit_code = conn.run(argv)
    return stdout, exit_code


def _host_totals(conn: VPSConnection) -> tuple[float, float, float]:
    """(total_vcpu, total_memory_mb, total_disk_gb) for the whole host."""
    nproc_out, nproc_rc = _command_available(conn, ["nproc"])
    total_vcpu = float(nproc_out.strip()) if nproc_rc == 0 and nproc_out.strip().isdigit() else 1.0

    meminfo_out, meminfo_rc = _command_available(conn, ["cat", "/proc/meminfo"])
    total_memory_mb = 0.0
    if meminfo_rc == 0:
        for line in meminfo_out.splitlines():
            if line.startswith("MemTotal:"):
                # "MemTotal:       16384000 kB"
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    total_memory_mb = int(parts[1]) / 1024
                break

    df_out, df_rc = _command_available(conn, ["df", "-PB1", "/"])
    total_disk_gb = 0.0
    if df_rc == 0:
        lines = df_out.strip().splitlines()
        if len(lines) >= 2:
            fields = lines[1].split()
            if len(fields) >= 2 and fields[1].isdigit():
                total_disk_gb = int(fields[1]) / (1024**3)

    return total_vcpu, total_memory_mb, total_disk_gb


def _parse_virsh_list(output: str) -> list[tuple[str, str]]:
    """Parses `virsh list --all` tabular output into [(name, state), ...].
    Format:
         Id   Name       State
        -----------------------------
         1    vm1        running
         -    vm2        shut off
    """
    results: list[tuple[str, str]] = []
    lines = output.strip().splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("id "):
            continue
        # The header/body separator is a run of dashes ("-----..."), unlike
        # a shut-off VM's row, which starts with a lone "-" in the Id
        # column (virsh's "no id" placeholder) followed by real fields —
        # only the former should be skipped.
        if set(stripped) == {"-"}:
            continue
        parts = stripped.split(None, 2)
        if len(parts) < 3:
            continue
        _id, name, state = parts[0], parts[1], parts[2]
        results.append((name, state.strip().lower().replace(" ", "_")))
    return results


def _parse_virsh_dominfo(output: str) -> tuple[float, float]:
    """(vcpu_count, memory_mb) from `virsh dominfo <name>` key: value lines."""
    vcpu = 1.0
    memory_mb = 0.0
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "cpu(s)" and value.isdigit():
            vcpu = float(value)
        elif key == "max memory":
            # "2097152 KiB"
            tokens = value.split()
            if tokens and tokens[0].isdigit():
                memory_mb = int(tokens[0]) / 1024
    return vcpu, memory_mb


def _collect_kvm_virsh(
    conn: VPSConnection, host: str, collected_at: datetime, host_totals: tuple[float, float, float]
) -> list[VPSResourceRecord] | None:
    list_out, list_rc = _command_available(conn, ["virsh", "list", "--all"])
    if list_rc != 0:
        return None

    vms = _parse_virsh_list(list_out)
    total_vcpu, total_mem, total_disk = host_totals
    resources: list[VPSResourceRecord] = []

    for name, state in vms:
        info_out, info_rc = _command_available(conn, ["virsh", "dominfo", name])
        vcpu, memory_mb = _parse_virsh_dominfo(info_out) if info_rc == 0 else (1.0, 0.0)
        warnings = [] if info_rc == 0 else ["dominfo_unavailable"]

        resources.append(
            VPSResourceRecord(
                resource_type="vps_vm",
                host=host,
                unit_id=name,
                resource_id=f"{host}:{name}",
                name=name,
                vcpu_count=vcpu,
                memory_mb=memory_mb,
                disk_gb=0.0,  # not reliably obtainable without extra per-disk SSH round trips
                state=state,
                host_total_vcpu=total_vcpu,
                host_total_memory_mb=total_mem,
                host_total_disk_gb=total_disk,
                collected_at=collected_at,
                warnings=warnings or ["disk_size_unavailable_for_kvm"],
            )
        )

    return resources


def _parse_qm_list(output: str) -> list[dict[str, str]]:
    """Parses Proxmox `qm list` tabular output:
          VMID NAME       STATUS     MEM(MB)    BOOTDISK(GB) PID
           100 vm1        running    2048       32.00        12345
    """
    lines = output.strip().splitlines()
    if len(lines) < 2:
        return []
    header = lines[0].split()
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < len(header):
            continue
        rows.append(dict(zip(header, fields)))
    return rows


def _collect_kvm_proxmox(
    conn: VPSConnection, host: str, collected_at: datetime, host_totals: tuple[float, float, float]
) -> list[VPSResourceRecord] | None:
    list_out, list_rc = _command_available(conn, ["qm", "list"])
    if list_rc != 0:
        return None

    rows = _parse_qm_list(list_out)
    total_vcpu, total_mem, total_disk = host_totals
    resources: list[VPSResourceRecord] = []

    for row in rows:
        vmid = row.get("VMID", "")
        name = row.get("NAME", vmid)
        state = row.get("STATUS", "unknown").lower()
        memory_mb = float(row["MEM(MB)"]) if row.get("MEM(MB)", "").replace(".", "", 1).isdigit() else 0.0
        disk_gb = (
            float(row["BOOTDISK(GB)"]) if row.get("BOOTDISK(GB)", "").replace(".", "", 1).isdigit() else 0.0
        )

        warnings: list[str] = []
        vcpu = 1.0
        if vmid:
            config_out, config_rc = _command_available(conn, ["qm", "config", vmid])
            if config_rc == 0:
                cores = 1
                sockets = 1
                for line in config_out.splitlines():
                    if line.startswith("cores:"):
                        cores_str = line.split(":", 1)[1].strip()
                        cores = int(cores_str) if cores_str.isdigit() else 1
                    elif line.startswith("sockets:"):
                        sockets_str = line.split(":", 1)[1].strip()
                        sockets = int(sockets_str) if sockets_str.isdigit() else 1
                vcpu = float(cores * sockets)
            else:
                warnings.append("qm_config_unavailable")

        resources.append(
            VPSResourceRecord(
                resource_type="vps_vm",
                host=host,
                unit_id=vmid or name,
                resource_id=f"{host}:{vmid or name}",
                name=name,
                vcpu_count=vcpu,
                memory_mb=memory_mb,
                disk_gb=disk_gb,
                state=state,
                host_total_vcpu=total_vcpu,
                host_total_memory_mb=total_mem,
                host_total_disk_gb=total_disk,
                collected_at=collected_at,
                warnings=warnings,
            )
        )

    return resources


def _parse_lxc_ls(output: str) -> list[tuple[str, str]]:
    """Parses `lxc-ls -f` tabular output:
        NAME  STATE   AUTOSTART GROUPS IPV4      IPV6
        c1    RUNNING 1         -      10.0.3.5  -
    """
    lines = output.strip().splitlines()
    if len(lines) < 2:
        return []
    results: list[tuple[str, str]] = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 2:
            continue
        results.append((fields[0], fields[1].lower()))
    return results


def _collect_lxc(
    conn: VPSConnection, host: str, collected_at: datetime, host_totals: tuple[float, float, float]
) -> list[VPSResourceRecord] | None:
    list_out, list_rc = _command_available(conn, ["lxc-ls", "-f"])
    if list_rc != 0:
        return None

    containers = _parse_lxc_ls(list_out)
    total_vcpu, total_mem, total_disk = host_totals
    resources: list[VPSResourceRecord] = []

    for name, state in containers:
        # LXC containers don't reliably enforce a vcpu/memory limit unless
        # explicitly cgroup-configured — rather than fabricate a number,
        # this is left at the host's own total (an honest "unconstrained")
        # with a warning, not zero (which would allocate it no cost at all).
        resources.append(
            VPSResourceRecord(
                resource_type="vps_container",
                host=host,
                unit_id=name,
                resource_id=f"{host}:{name}",
                name=name,
                vcpu_count=total_vcpu,
                memory_mb=total_mem,
                disk_gb=0.0,
                state=state,
                host_total_vcpu=total_vcpu,
                host_total_memory_mb=total_mem,
                host_total_disk_gb=total_disk,
                collected_at=collected_at,
                warnings=["lxc_resource_limits_unavailable_using_host_totals"],
            )
        )

    return resources


def _collect_docker(
    conn: VPSConnection, host: str, collected_at: datetime, host_totals: tuple[float, float, float]
) -> list[VPSResourceRecord] | None:
    list_out, list_rc = _command_available(conn, ["docker", "ps", "-a", "--format", "{{json .}}"])
    if list_rc != 0:
        return None

    total_vcpu, total_mem, total_disk = host_totals
    resources: list[VPSResourceRecord] = []

    for line in list_out.strip().splitlines():
        if not line.strip():
            continue
        try:
            container = json.loads(line)
        except json.JSONDecodeError:
            continue

        container_id = container.get("ID", "")
        name = container.get("Names", container_id)
        state = str(container.get("State", "unknown")).lower()

        warnings: list[str] = []
        vcpu = total_vcpu
        memory_mb = 0.0
        if container_id:
            inspect_out, inspect_rc = _command_available(
                conn, ["docker", "inspect", container_id, "--format", "{{json .HostConfig}}"]
            )
            if inspect_rc == 0:
                try:
                    host_config = json.loads(inspect_out.strip())
                    nano_cpus = host_config.get("NanoCpus") or 0
                    memory_bytes = host_config.get("Memory") or 0
                    if nano_cpus:
                        vcpu = nano_cpus / 1_000_000_000
                    if memory_bytes:
                        memory_mb = memory_bytes / (1024**2)
                    if not nano_cpus:
                        warnings.append("docker_cpu_limit_unset_using_host_total")
                except json.JSONDecodeError:
                    warnings.append("docker_inspect_unparseable")
            else:
                warnings.append("docker_inspect_unavailable")

        resources.append(
            VPSResourceRecord(
                resource_type="vps_container",
                host=host,
                unit_id=container_id or name,
                resource_id=f"{host}:{container_id or name}",
                name=name,
                vcpu_count=vcpu,
                memory_mb=memory_mb,
                disk_gb=0.0,
                state=state,
                host_total_vcpu=total_vcpu,
                host_total_memory_mb=total_mem,
                host_total_disk_gb=total_disk,
                collected_at=collected_at,
                warnings=warnings,
            )
        )

    return resources


def _collect_host_only(
    host: str, collected_at: datetime, host_totals: tuple[float, float, float]
) -> list[VPSResourceRecord]:
    total_vcpu, total_mem, total_disk = host_totals
    return [
        VPSResourceRecord(
            resource_type="vps_host",
            host=host,
            unit_id="host",
            resource_id=f"{host}:host",
            name=host,
            vcpu_count=total_vcpu,
            memory_mb=total_mem,
            disk_gb=total_disk,
            state="running",
            host_total_vcpu=total_vcpu,
            host_total_memory_mb=total_mem,
            host_total_disk_gb=total_disk,
            collected_at=collected_at,
        )
    ]


def collect_vps_inventory(conn: VPSConnection, host: str) -> VPSInventoryResult:
    collected_at = datetime.now(timezone.utc)
    host_totals = _host_totals(conn)

    virsh_resources = _collect_kvm_virsh(conn, host, collected_at, host_totals)
    if virsh_resources is not None:
        if virsh_resources:
            return VPSInventoryResult(detection_path="kvm_virsh", resources=virsh_resources)
        # virsh present but zero VMs defined — still a real detection, but
        # keep looking in case this is actually a Proxmox/LXC/Docker box
        # whose virsh happens to be installed unused.
        logger.info("vps.inventory: virsh available but reported no VMs on %s, trying other detectors", host)

    proxmox_resources = _collect_kvm_proxmox(conn, host, collected_at, host_totals)
    if proxmox_resources is not None and proxmox_resources:
        return VPSInventoryResult(detection_path="kvm_proxmox_qm", resources=proxmox_resources)

    lxc_resources = _collect_lxc(conn, host, collected_at, host_totals)
    if lxc_resources is not None and lxc_resources:
        return VPSInventoryResult(detection_path="lxc", resources=lxc_resources)

    docker_resources = _collect_docker(conn, host, collected_at, host_totals)
    if docker_resources is not None and docker_resources:
        return VPSInventoryResult(detection_path="docker", resources=docker_resources)

    logger.info("vps.inventory: no VM/container runtime detected on %s, treating host as one resource", host)
    return VPSInventoryResult(
        detection_path="host_only", resources=_collect_host_only(host, collected_at, host_totals)
    )
