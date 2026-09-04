from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from apps.api.routers.observation import _resurface_rejected_proposals


def _mock_db_with_proposals(stale_rejections: list[dict]):
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=stale_rejections)
    mock_db.proposals.find = MagicMock(return_value=mock_cursor)
    mock_db.proposals.insert_many = AsyncMock()
    return mock_db, mock_cursor


def _resources(*ids: str) -> list[dict]:
    return [{"resource_id": rid} for rid in ids]


@patch("apps.api.routers.observation.datetime")
def test_rejected_proposal_older_than_an_hour_resurfaces_with_supersedes_link(mock_datetime):
    frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = frozen_now

    old_proposal = {
        "proposal_id": "old-1",
        "tenant_id": "demo-tenant",
        "status": "rejected",
        "rejected_at": frozen_now - timedelta(hours=2),
        "resource_arn": "arn:aws:ec2:ap-south-1:demo:instance/i-stale",
        "parameters": {"instance_id": "i-stale", "region": "ap-south-1"},
        "action_type": "stop_instance",
        "template_id": "ec2.stop.v1",
        "expected_monthly_savings": 14.2,
        "risk_level": "low",
        "confidence": 0.9,
    }
    mock_db, mock_cursor = _mock_db_with_proposals([old_proposal])

    resurfaced = asyncio.run(
        _resurface_rejected_proposals(mock_db, "demo-tenant", _resources("i-stale"))
    )

    assert len(resurfaced) == 1
    new_doc = resurfaced[0]
    assert new_doc["proposal_id"] != "old-1"
    assert new_doc["status"] == "proposed"
    assert new_doc["supersedes_proposal_id"] == "old-1"
    assert new_doc["rejected_at"] is None
    # Everything else about the proposal carries over unchanged.
    assert new_doc["resource_arn"] == old_proposal["resource_arn"]
    assert new_doc["template_id"] == "ec2.stop.v1"

    mock_db.proposals.insert_many.assert_awaited_once_with([new_doc])

    # The query used the 1-hour cutoff computed from frozen "now".
    query = mock_db.proposals.find.call_args.args[0]
    assert query["status"] == "rejected"
    assert query["rejected_at"]["$lt"] == frozen_now - timedelta(hours=1)


@patch("apps.api.routers.observation.datetime")
def test_rejected_proposal_for_resource_not_in_snapshot_does_not_resurface(mock_datetime):
    frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = frozen_now

    old_proposal = {
        "proposal_id": "old-2",
        "status": "rejected",
        "rejected_at": frozen_now - timedelta(hours=5),
        "parameters": {"instance_id": "i-decommissioned"},
    }
    # The Mongo query itself already filters by rejected_at < cutoff, so the
    # mock only returns proposals that passed that filter — this test
    # exercises the resource-presence filter that happens after the fetch.
    mock_db, _ = _mock_db_with_proposals([old_proposal])

    resurfaced = asyncio.run(
        _resurface_rejected_proposals(mock_db, "demo-tenant", _resources("i-still-here"))
    )

    assert resurfaced == []
    mock_db.proposals.insert_many.assert_not_awaited()


def test_no_stale_rejections_returns_empty_list_without_inserting():
    mock_db, _ = _mock_db_with_proposals([])

    resurfaced = asyncio.run(
        _resurface_rejected_proposals(mock_db, "demo-tenant", _resources("i-1", "i-2"))
    )

    assert resurfaced == []
    mock_db.proposals.insert_many.assert_not_awaited()


def test_no_resources_in_snapshot_skips_the_query_entirely():
    mock_db, _ = _mock_db_with_proposals([])

    resurfaced = asyncio.run(_resurface_rejected_proposals(mock_db, "demo-tenant", []))

    assert resurfaced == []
    mock_db.proposals.find.assert_not_called()


@patch("apps.api.routers.observation.datetime")
def test_multiple_stale_rejections_all_resurface_independently(mock_datetime):
    frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = frozen_now

    old_proposals = [
        {
            "proposal_id": "old-1",
            "status": "rejected",
            "rejected_at": frozen_now - timedelta(hours=3),
            "parameters": {"instance_id": "i-1"},
        },
        {
            "proposal_id": "old-2",
            "status": "rejected",
            "rejected_at": frozen_now - timedelta(hours=4),
            "parameters": {"instance_id": "i-2"},
        },
    ]
    mock_db, _ = _mock_db_with_proposals(old_proposals)

    resurfaced = asyncio.run(
        _resurface_rejected_proposals(mock_db, "demo-tenant", _resources("i-1", "i-2"))
    )

    assert len(resurfaced) == 2
    supersedes = {d["supersedes_proposal_id"] for d in resurfaced}
    assert supersedes == {"old-1", "old-2"}
    # New proposal_ids are distinct from each other and from the originals.
    new_ids = {d["proposal_id"] for d in resurfaced}
    assert len(new_ids) == 2
    assert not new_ids & {"old-1", "old-2"}
