"""Notification sink is a Protocol so guard.py never depends on a
concrete transport. `LoggingNotificationSink` is demo-only. On merge,
add a sink that calls into services.notifications.email (or wire
straight into services/notifications/__init__.py's send path) and pass
that into SpendVelocityGuard instead."""

from __future__ import annotations

import logging
from typing import Protocol

from .schemas import VelocityAlert


class NotificationSink(Protocol):
    def send(self, alert: VelocityAlert) -> None: ...


class LoggingNotificationSink:
    def __init__(self) -> None:
        self._logger = logging.getLogger("spend_velocity")

    def send(self, alert: VelocityAlert) -> None:
        self._logger.warning(
            "SPEND VELOCITY ALERT [%s] scope=%s action=%s projected_24h=%.2f — %s",
            alert.severity,
            alert.scope,
            alert.recommended_action,
            alert.projected_24h_cost,
            alert.rationale,
        )


class NullNotificationSink:
    """Explicit no-op, for tests that want to assert on the returned
    alert without caring about side-effect delivery."""

    def send(self, alert: VelocityAlert) -> None:  # noqa: D401
        return None
