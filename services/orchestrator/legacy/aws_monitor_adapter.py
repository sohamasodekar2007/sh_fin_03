from typing import Any, TypedDict

from services.collector.collector_service import AWSCollectorService


class MonitorState(TypedDict, total=False):
    cloud_snapshot: dict[str, Any]
    collection_status: str
    resource_count: int
    collection_issues: list[dict[str, Any]]


def build_monitor_node(
    collector_service: AWSCollectorService,
):
    def monitor_node(
        state: MonitorState,
    ) -> MonitorState:
        snapshot = collector_service.collect_snapshot()

        return {
            "cloud_snapshot": snapshot.model_dump(
                mode="json"
            ),
            "collection_status": snapshot.status,
            "resource_count": snapshot.resource_count,
            "collection_issues": [
                issue.model_dump(mode="json")
                for issue in snapshot.issues
            ],
        }

    return monitor_node
