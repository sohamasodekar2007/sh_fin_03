import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.api.routers import pipeline


def test_pipeline_run_returns_live_aws_fallback_when_pipeline_storage_fails():
    settings = SimpleNamespace(
        aws_account_id="123456789012",
        aws_region="ap-south-1",
        azure_subscription_id="",
        vps_host="",
    )
    fallback_doc = {
        "status": "degraded",
        "summary": {"resources": 3, "findings": 2, "proposals": 1},
        "proposals": [{"proposal_id": "prop-1"}],
    }

    with patch("apps.api.routers.pipeline.get_settings", return_value=settings), patch(
        "apps.api.routers.pipeline.get_db"
    ), patch("apps.api.routers.pipeline._mongo_available", new_callable=AsyncMock, return_value=True), patch(
        "apps.api.routers.pipeline.run_pipeline_for_account", new_callable=AsyncMock
    ) as run_pipeline, patch(
        "apps.api.routers.pipeline._live_aws_agent_command_doc", return_value=fallback_doc
    ) as live_fallback:
        run_pipeline.side_effect = RuntimeError("MongoDB unavailable")
        result = asyncio.run(
            pipeline.trigger_pipeline_run(
                provider="aws",
                account_id=None,
                region=None,
                current_user={"tenant_id": "tenant-1"},
            )
        )

    assert result["status"] == "degraded"
    assert result["persistence_error"] == "MongoDB unavailable"
    assert result["monitor"]["resource_count"] == 3
    assert result["analyzer"]["findings_count"] == 2
    assert result["decision"]["proposals_count"] == 1
    assert result["decision"]["proposals"] == [{"proposal_id": "prop-1"}]
    assert result["agent_command_doc"] == fallback_doc
    run_pipeline.assert_awaited_once()
    live_fallback.assert_called_once()


def test_pipeline_run_skips_mongo_backed_chain_when_mongo_is_unavailable():
    settings = SimpleNamespace(
        aws_account_id="123456789012",
        aws_region="ap-south-1",
        azure_subscription_id="",
        vps_host="",
    )
    fallback_doc = {
        "status": "degraded",
        "summary": {"resources": 5, "findings": 4, "proposals": 3},
        "proposals": [{"proposal_id": "prop-1"}, {"proposal_id": "prop-2"}, {"proposal_id": "prop-3"}],
    }

    with patch("apps.api.routers.pipeline.get_settings", return_value=settings), patch(
        "apps.api.routers.pipeline.get_db"
    ), patch("apps.api.routers.pipeline._mongo_available", new_callable=AsyncMock, return_value=False), patch(
        "apps.api.routers.pipeline.run_pipeline_for_account", new_callable=AsyncMock
    ) as run_pipeline, patch(
        "apps.api.routers.pipeline._live_aws_agent_command_doc", return_value=fallback_doc
    ):
        result = asyncio.run(
            pipeline.trigger_pipeline_run(
                provider="aws",
                account_id=None,
                region=None,
                current_user={"tenant_id": "tenant-1"},
            )
        )

    assert result["status"] == "degraded"
    assert result["persistence_error"].startswith("MongoDB is unavailable")
    assert result["monitor"]["resource_count"] == 5
    assert result["analyzer"]["findings_count"] == 4
    assert result["decision"]["proposals_count"] == 3
    run_pipeline.assert_not_awaited()
