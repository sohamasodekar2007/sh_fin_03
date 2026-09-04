from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

import services.executor.actions as actions


# ---------------------------------------------------------------------------
# Reuses the same fake Motor db + settings pattern as test_executor_live.py
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, unique_field: str | None = None):
        self._docs: list[dict] = []
        self._unique_field = unique_field

    async def insert_one(self, doc):
        if self._unique_field and any(d.get(self._unique_field) == doc.get(self._unique_field) for d in self._docs):
            raise Exception("E11000 duplicate key error")
        self._docs.append(dict(doc))

    async def find_one(self, query, *_a, **_kw):
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def delete_one(self, query):
        for i, doc in enumerate(self._docs):
            if all(doc.get(k) == v for k, v in query.items()):
                del self._docs[i]
                return

    async def update_one(self, query, update):
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))
                return

    async def create_index(self, *a, **kw):
        pass

    def find(self, query=None, *_a, **_kw):
        query = query or {}
        matched = [d for d in self._docs if all(d.get(k) == v for k, v in query.items())]
        return _FakeCursor(matched)


class _FakeDB:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}

    def _get(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            unique_field = "resource_arn" if name == "execution_locks" else None
            self._collections[name] = _FakeCollection(unique_field=unique_field)
        return self._collections[name]

    def __getitem__(self, name):
        return self._get(name)

    def __getattr__(self, name):
        return self._get(name)


def _settings(execution_enabled=True, execution_mode="live", allowlist_tag="cloudcare:managed=true"):
    return SimpleNamespace(
        execution_enabled=execution_enabled,
        execution_mode=execution_mode,
        execution_allowlist_tag=allowlist_tag,
        aws_write_role_arn="arn:aws:iam::123456789012:role/CloudCareExecutorRole",
        aws_external_id="test-external-id",
        aws_region="us-east-1",
    )


def _proposal(asg_name: str, desired: int, proposed: int, status: str = "approved", **extra) -> dict:
    doc = {
        "proposal_id": "p-asg-1",
        "tenant_id": "demo-tenant",
        "resource_arn": f"arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:*:autoScalingGroupName/{asg_name}",
        "action_type": "adjust_asg_capacity",
        "template_id": "asg.adjust_capacity.v1",
        "parameters": {
            "asg_name": asg_name, "region": "us-east-1",
            "current_desired_capacity": desired, "proposed_desired_capacity": proposed,
        },
        "status": status,
        "environment": "development",
        "risk_level": "medium",
        "expected_monthly_savings": "0",
    }
    doc.update(extra)
    return doc


def _create_asg(tagged: bool = True, desired: int = 3, min_size: int = 1) -> str:
    asg_name = "asg-web"
    autoscaling = boto3.client("autoscaling", region_name="us-east-1")
    autoscaling.create_launch_configuration(
        LaunchConfigurationName="lc-1", ImageId="ami-12345678", InstanceType="t3.micro",
    )
    tags = (
        [{"Key": "cloudcare:managed", "Value": "true", "PropagateAtLaunch": True, "ResourceId": asg_name, "ResourceType": "auto-scaling-group"}]
        if tagged else []
    )
    autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=asg_name, LaunchConfigurationName="lc-1",
        MinSize=min_size, MaxSize=5, DesiredCapacity=desired,
        AvailabilityZones=["us-east-1a"], Tags=tags,
    )
    return asg_name


@mock_aws
def test_refuses_without_allowlist_tag():
    asg_name = _create_asg(tagged=False)
    db = _FakeDB()
    proposal = _proposal(asg_name, desired=3, proposed=2)

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["NOT_ALLOWLISTED"]
    assert record.actual_aws_call_made is False


@mock_aws
def test_refuses_without_approval():
    asg_name = _create_asg(tagged=True)
    db = _FakeDB()
    proposal = _proposal(asg_name, desired=3, proposed=2, status="pending_approval")

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["PROPOSAL_NOT_APPROVED"]
    assert record.actual_aws_call_made is False


@mock_aws
def test_adjusts_desired_capacity_when_approved_and_live():
    asg_name = _create_asg(tagged=True, desired=3, min_size=1)
    db = _FakeDB()
    proposal = _proposal(asg_name, desired=3, proposed=2, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "executed"
    assert record.actual_aws_call_made is True

    autoscaling = boto3.client("autoscaling", region_name="us-east-1")
    group = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]
    assert group["DesiredCapacity"] == 2


@mock_aws
def test_simulation_mode_makes_no_real_call():
    asg_name = _create_asg(tagged=True, desired=3, min_size=1)
    db = _FakeDB()
    proposal = _proposal(asg_name, desired=3, proposed=2, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="simulation")):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "executed"
    assert record.actual_aws_call_made is False

    autoscaling = boto3.client("autoscaling", region_name="us-east-1")
    group = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]
    assert group["DesiredCapacity"] == 3  # untouched in simulation mode


@mock_aws
def test_no_op_when_already_at_proposed_capacity():
    asg_name = _create_asg(tagged=True, desired=2, min_size=1)
    db = _FakeDB()
    proposal = _proposal(asg_name, desired=2, proposed=2, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "no_op"
    assert record.reason_codes == ["ALREADY_AT_DESIRED_CAPACITY"]
    assert record.actual_aws_call_made is False


@mock_aws
def test_idempotent_on_repeat_calls():
    asg_name = _create_asg(tagged=True, desired=3, min_size=1)
    db = _FakeDB()
    proposal = _proposal(asg_name, desired=3, proposed=2, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        first = asyncio.run(actions.execute_action(db, proposal))
        second = asyncio.run(actions.execute_action(db, proposal))

    assert first.status == "executed"
    if second.execution_id != first.execution_id:
        assert second.status == "no_op"
        assert second.actual_aws_call_made is False


def test_no_action_is_structurally_unexecutable():
    """no_action has no handler at all — the handlers.get() miss returns
    the existing UNSUPPORTED_ACTION refusal before any AWS call is even
    attempted, matching Phase 14's RDS/S3 'never executable' property."""
    db = _FakeDB()
    proposal = _proposal("asg-web", desired=3, proposed=2, status="approved")
    proposal["action_type"] = "no_action"

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["UNSUPPORTED_ACTION"]
