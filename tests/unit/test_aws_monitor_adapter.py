from datetime import datetime, timezone
from unittest.mock import Mock

from services.orchestrator.legacy.aws_monitor_adapter import (
    build_monitor_node,
)
from packages.schemas.cloud_snapshot import CloudSnapshot


def test_monitor_node_returns_state_update() -> None:
    service = Mock()

    service.collect_snapshot.return_value = CloudSnapshot(
        account_id="000000000000",
        region="ap-south-1",
        collected_at=datetime.now(timezone.utc),
        status="success",
        resource_count=0,
        metric_count=0,
        cost_day_count=0,
    )

    monitor_node = build_monitor_node(service)

    original_state = {
        "collection_status": "not_started"
    }

    result = monitor_node(original_state)

    assert result["collection_status"] == "success"
    assert result["resource_count"] == 0
    assert "cloud_snapshot" in result

    assert original_state == {
        "collection_status": "not_started"
    }
