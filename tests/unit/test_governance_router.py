from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from apps.api.main import app
from packages.schemas.governance import AccountOverview, IAMUserDetail, ResourceCreator
from services.collector.iam_governance_collector import IAMGovernanceCollectionError

client = TestClient(app)


def test_iam_overview_returns_all_sections_on_success():
    account = AccountOverview(
        account_id="350381001148",
        alias="teamalpha",
        root_mfa_enabled=True,
        root_access_keys_present=False,
        password_policy_configured=True,
    )
    users = [
        IAMUserDetail(user_name="cloudcare-bootstrap", arn="arn:aws:iam::350381001148:user/cloudcare-bootstrap", groups=[], policies=[])
    ]
    creators = []

    with patch("apps.api.routers.governance.IAMGovernanceCollector") as collector_class:
        instance = collector_class.return_value
        instance.get_account_overview.return_value = account
        instance.get_users_and_policies.return_value = users
        instance.get_resource_creators.return_value = creators

        response = client.get(
            "/v1/governance/iam-overview",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["account"]["root_mfa_enabled"] is True
    assert len(body["users"]) == 1
    assert body["errors"] == {}


def test_iam_overview_survives_one_section_failing():
    """A CloudTrail-access failure must not take the whole endpoint down —
    account + users still come back, with the failure surfaced in `errors`,
    not hidden as an empty-looking success."""
    account = AccountOverview(account_id="350381001148")
    users = [
        IAMUserDetail(user_name="cloudcare-bootstrap", arn="arn:aws:iam::350381001148:user/cloudcare-bootstrap", groups=[], policies=[])
    ]

    with patch("apps.api.routers.governance.IAMGovernanceCollector") as collector_class:
        instance = collector_class.return_value
        instance.get_account_overview.return_value = account
        instance.get_users_and_policies.return_value = users
        instance.get_resource_creators.side_effect = IAMGovernanceCollectionError(
            "Resource-creator lookup failed: AccessDeniedException"
        )

        response = client.get(
            "/v1/governance/iam-overview",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["users"]) == 1
    assert body["resource_creators"] == []
    assert "resource_creators" in body["errors"]
    assert "AccessDeniedException" in body["errors"]["resource_creators"]


def test_iam_overview_all_sections_failing_still_returns_200_with_errors():
    with patch("apps.api.routers.governance.IAMGovernanceCollector") as collector_class:
        instance = collector_class.return_value
        instance.get_account_overview.side_effect = IAMGovernanceCollectionError("Account overview failed: AccessDenied")
        instance.get_users_and_policies.side_effect = IAMGovernanceCollectionError("Users/policies collection failed: AccessDenied")
        instance.get_resource_creators.side_effect = IAMGovernanceCollectionError("Resource-creator lookup failed: AccessDeniedException")

        response = client.get(
            "/v1/governance/iam-overview",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["users"] == []
    assert body["resource_creators"] == []
    assert set(body["errors"].keys()) == {"account", "users", "resource_creators"}
