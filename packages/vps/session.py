"""
VPS SSH connection — key-only auth. VPS_SSH_KEY_PASSPHRASE unlocks an
*encrypted private key file*; it is never a login password, and this module
never accepts one (there is no password= path here at all).

One VPSConnection instance pools its underlying paramiko transport across
every run() call made on it — a collection pass that does inventory,
metrics and a df check reuses one SSH handshake instead of three. Callers
own the connection's lifetime and MUST close it in a finally block (see
services/collector/vps/inventory.py and metrics.py) — this module does not
manage a background pool across requests.
"""

from __future__ import annotations

import logging
import shlex
import threading
from pathlib import Path

import paramiko

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 30
MAX_CONNECT_RETRIES = 3

_KEY_CLASSES = tuple(
    key_cls
    for name in ("Ed25519Key", "RSAKey", "ECDSAKey", "DSSKey")
    if (key_cls := getattr(paramiko, name, None)) is not None
)


class VPSConnectionError(Exception):
    """Raised when an SSH connection to the VPS cannot be established."""


def _load_private_key(key_path: str, passphrase: str | None) -> paramiko.PKey:
    expanded = Path(key_path).expanduser()
    if not expanded.exists():
        raise VPSConnectionError(f"SSH private key not found at {expanded}")

    last_error: Exception | None = None
    for key_cls in _KEY_CLASSES:
        try:
            return key_cls.from_private_key_file(str(expanded), password=passphrase or None)
        except paramiko.SSHException as exc:
            last_error = exc
            continue

    raise VPSConnectionError(
        f"Could not load private key at {expanded} as any of "
        f"{[c.__name__ for c in _KEY_CLASSES]} — check the key format and passphrase"
    ) from last_error


class VPSConnection:
    def __init__(
        self,
        host: str,
        username: str,
        key_path: str,
        port: int = 22,
        key_passphrase: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.key_path = key_path
        self.key_passphrase = key_passphrase
        self._client: paramiko.SSHClient | None = None
        self._lock = threading.Lock()

    def _connect(self) -> paramiko.SSHClient:
        last_error: Exception | None = None
        pkey = _load_private_key(self.key_path, self.key_passphrase)

        for attempt in range(1, MAX_CONNECT_RETRIES + 1):
            client = paramiko.SSHClient()
            # Production deployments should pre-populate a known_hosts file
            # (client.load_host_keys(...)); RejectPolicy refuses to talk to
            # an unrecognized host rather than silently trusting it.
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.load_system_host_keys()
            try:
                client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=pkey,
                    timeout=CONNECT_TIMEOUT_SECONDS,
                    banner_timeout=CONNECT_TIMEOUT_SECONDS,
                    auth_timeout=CONNECT_TIMEOUT_SECONDS,
                    allow_agent=False,
                    look_for_keys=False,
                )
                return client
            except Exception as exc:  # noqa: BLE001 - retry on any connect failure
                last_error = exc
                logger.warning(
                    "vps.session: connect attempt %d/%d to %s:%d failed: %s",
                    attempt, MAX_CONNECT_RETRIES, self.host, self.port, exc,
                )
                client.close()

        raise VPSConnectionError(
            f"Could not connect to {self.host}:{self.port} after {MAX_CONNECT_RETRIES} attempts"
        ) from last_error

    def _get_client(self) -> paramiko.SSHClient:
        with self._lock:
            transport = self._client.get_transport() if self._client else None
            if transport is None or not transport.is_active():
                if self._client is not None:
                    self._client.close()
                self._client = self._connect()
            return self._client

    def run(self, command: list[str], timeout: float = CONNECT_TIMEOUT_SECONDS) -> tuple[str, str, int]:
        """
        Runs `command` over SSH and returns (stdout, stderr, exit_code).

        `command` MUST be a list of argv-style tokens, never a pre-built
        shell string. This builds the remote command line with shlex.join,
        which shell-quotes every token individually — a resource id or
        hostname pulled from the database or an API response can never
        break out of its argument position into shell interpolation.
        """
        if isinstance(command, str):
            raise TypeError(
                "VPSConnection.run() takes an argv-style list[str], never a raw shell string — "
                "pass e.g. ['sar', '-u', '-f', path] so every argument is quoted individually."
            )

        remote_command = shlex.join(command)
        client = self._get_client()
        stdin, stdout, stderr = client.exec_command(remote_command, timeout=timeout)
        try:
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
            return stdout_text, stderr_text, exit_code
        finally:
            stdin.close()
            stdout.close()
            stderr.close()

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    def __enter__(self) -> "VPSConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
