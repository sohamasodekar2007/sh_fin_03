from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from services.collector.iam_governance_collector import IAMGovernanceCollector


def _factory_with_client(client_map: dict[str, MagicMock]) -> MagicMock:
    factory = MagicMock()
    factory.client.side_effect = lambda service, region_name=None: client_map[service]
    return factory


def test_get_account_overview_reads_root_mfa_and_password_policy():
    iam = MagicMock()
    iam.get_account_summary.return_value = {
        "SummaryMap": {"AccountMFAEnabled": 1, "AccountAccessKeysPresent": 0}
    }
    iam.list_account_aliases.return_value = {"AccountAliases": ["teamalpha"]}
    iam.get_account_password_policy.return_value = {"PasswordPolicy": {}}

    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "350381001148"}

    factory = _factory_with_client({"iam": iam, "sts": sts})
    collector = IAMGovernanceCollector(client_factory=factory)

    overview = collector.get_account_overview()

    assert overview.account_id == "350381001148"
    assert overview.alias == "teamalpha"
    assert overview.root_mfa_enabled is True
    assert overview.root_access_keys_present is False
    assert overview.password_policy_configured is True


def test_get_account_overview_treats_no_such_entity_as_not_configured():
    iam = MagicMock()
    iam.get_account_summary.return_value = {"SummaryMap": {}}
    iam.list_account_aliases.return_value = {"AccountAliases": []}
    iam.get_account_password_policy.side_effect = ClientError(
        {"Error": {"Code": "NoSuchEntity", "Message": "no policy"}}, "GetAccountPasswordPolicy"
    )

    sts = MagicMock()
    sts.get_caller_identity.return_value = {"Account": "350381001148"}

    factory = _factory_with_client({"iam": iam, "sts": sts})
    collector = IAMGovernanceCollector(client_factory=factory)

    overview = collector.get_account_overview()

    # No AccountMFAEnabled key at all -> genuinely unknown, not "disabled."
    assert overview.root_mfa_enabled is None
    assert overview.password_policy_configured is False


def test_get_users_and_policies_parses_managed_and_inline_policies():
    iam = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "UserDetailList": [
                {
                    "UserName": "cloudcare-bootstrap",
                    "Arn": "arn:aws:iam::350381001148:user/cloudcare-bootstrap",
                    "CreateDate": datetime.now(timezone.utc),
                    "GroupList": ["admins"],
                    "AttachedManagedPolicies": [
                        {"PolicyName": "AdministratorAccess", "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess"}
                    ],
                    "UserPolicyList": [
                        {"PolicyName": "InlineS3Read", "PolicyDocument": {"Version": "2012-10-17", "Statement": []}}
                    ],
                }
            ]
        }
    ]
    iam.get_paginator.return_value = paginator
    iam.list_access_keys.return_value = {"AccessKeyMetadata": []}

    factory = _factory_with_client({"iam": iam})
    collector = IAMGovernanceCollector(client_factory=factory)

    users = collector.get_users_and_policies()

    assert len(users) == 1
    user = users[0]
    assert user.groups == ["admins"]
    assert len(user.policies) == 2
    managed = next(p for p in user.policies if p.type == "managed")
    inline = next(p for p in user.policies if p.type == "inline")
    assert managed.name == "AdministratorAccess"
    assert managed.document is None
    assert inline.document == {"Version": "2012-10-17", "Statement": []}


def test_get_resource_creators_parses_cloudtrail_event_and_dedupes_by_creation_events():
    cloudtrail = MagicMock()
    paginator = MagicMock()

    event_time = datetime.now(timezone.utc)
    cloudtrail_event = json.dumps(
        {
            "userIdentity": {"arn": "arn:aws:iam::350381001148:user/soham", "userName": "soham"},
            "resources": [{"resourceName": "i-0a34c54ac18e0eb62", "resourceType": "AWS::EC2::Instance"}],
        }
    )

    def paginate_side_effect(LookupAttributes, StartTime):
        event_name = LookupAttributes[0]["AttributeValue"]
        if event_name == "RunInstances":
            return [
                {
                    "Events": [
                        {"CloudTrailEvent": cloudtrail_event, "EventTime": event_time}
                    ]
                }
            ]
        return [{"Events": []}]

    paginator.paginate.side_effect = paginate_side_effect
    cloudtrail.get_paginator.return_value = paginator

    factory = _factory_with_client({"cloudtrail": cloudtrail})
    collector = IAMGovernanceCollector(client_factory=factory)

    creators = collector.get_resource_creators(region="ap-south-1", lookback_days=90)

    assert len(creators) == 1
    creator = creators[0]
    assert creator.resource_id == "i-0a34c54ac18e0eb62"
    assert creator.event_name == "RunInstances"
    assert creator.principal_name == "soham"
    assert creator.principal_arn == "arn:aws:iam::350381001148:user/soham"


def test_get_resource_creators_skips_events_with_no_resource_name():
    cloudtrail = MagicMock()
    paginator = MagicMock()

    cloudtrail_event_no_resource = json.dumps({"userIdentity": {"arn": "arn:x"}, "resources": []})

    def paginate_side_effect(LookupAttributes, StartTime):
        event_name = LookupAttributes[0]["AttributeValue"]
        if event_name == "RunInstances":
            return [
                {
                    "Events": [
                        {"CloudTrailEvent": cloudtrail_event_no_resource, "EventTime": datetime.now(timezone.utc)}
                    ]
                }
            ]
        return [{"Events": []}]

    paginator.paginate.side_effect = paginate_side_effect
    cloudtrail.get_paginator.return_value = paginator

    factory = _factory_with_client({"cloudtrail": cloudtrail})
    collector = IAMGovernanceCollector(client_factory=factory)

    creators = collector.get_resource_creators(region="ap-south-1")

    assert creators == []
