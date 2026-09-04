from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def _mock_db_with_accounts(docs: list[dict]):
    mock_db = MagicMock()
    mock_collection = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=docs)
    mock_collection.find.return_value = fake_cursor
    mock_db.cloud_accounts = mock_collection
    return mock_db


def test_list_cloud_accounts_returns_only_safe_fields():
    docs = [
        {
            "provider": "aws",
            "account_id": "350381001148",
            "region": "ap-south-1",
            "connected": True,
            "status": "validated",
        },
        {
            "provider": "azure",
            "account_id": "955c7106-5f99-4b1a-8898-945ed8db3d2c",
            "region": "ap-south-1",
            "connected": False,
            "status": "failed",
        },
    ]

    with patch("apps.api.routers.accounts_runs.get_db", return_value=_mock_db_with_accounts(docs)):
        response = client.get(
            "/v1/cloud-accounts",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["provider"] == "aws"
    assert body[0]["connected"] is True
    assert body[1]["provider"] == "azure"
    assert body[1]["connected"] is False


def test_list_cloud_accounts_never_leaks_secret_fields_even_if_present_in_the_doc():
    # A doc from db.cloud_accounts CAN carry azure_client_secret /
    # gcp_service_account_json (CloudAccount's full persisted shape) — the
    # response model must drop them regardless of what's in Mongo.
    docs = [
        {
            "provider": "azure",
            "account_id": "sub-1",
            "region": "ap-south-1",
            "connected": True,
            "status": "validated",
            "azure_client_secret": "super-secret-value",
            "gcp_service_account_json": {"private_key": "also-secret"},
        }
    ]

    with patch("apps.api.routers.accounts_runs.get_db", return_value=_mock_db_with_accounts(docs)):
        response = client.get(
            "/v1/cloud-accounts",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "azure_client_secret" not in body[0]
    assert "gcp_service_account_json" not in body[0]
    assert set(body[0].keys()) == {"provider", "account_id", "region", "connected", "status"}


def test_list_cloud_accounts_scopes_query_by_tenant():
    mock_db = _mock_db_with_accounts([])
    with patch("apps.api.routers.accounts_runs.get_db", return_value=mock_db):
        client.get(
            "/v1/cloud-accounts",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    mock_db.cloud_accounts.find.assert_called_once()
    query_arg = mock_db.cloud_accounts.find.call_args.args[0]
    assert query_arg == {"tenant_id": "demo-tenant"}
