from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

import services.executor.actions as actions
import services.verifier.health as health


# ---------------------------------------------------------------------------
# A minimal in-memory fake of the Motor async collection/db interface —
# real enough to exercise the actual lock-acquire / idempotency-dedup code
# paths (unique-key duplicate detection included), not just return canned
# values for each call.
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


def _proposal(pid="p1", instance_id="i-1", action_type="stop_instance", status="approved", template_id="ec2.stop.v1", **extra):
    doc = {
        "proposal_id": pid,
        "tenant_id": "demo-tenant",
        "resource_arn": f"arn:aws:ec2:us-east-1:123456789012:instance/{instance_id}",
        "action_type": action_type,
        "template_id": template_id,
        "parameters": {"instance_id": instance_id, "region": "us-east-1"},
        "status": status,
        "environment": "development",
        "risk_level": "low",
        "expected_monthly_savings": "42.00",
    }
    doc.update(extra)
    return doc


def _launch_instance(tagged: bool = True) -> str:
    ec2 = boto3.client("ec2", region_name="us-east-1")
    tags = [{"Key": "cloudcare:managed", "Value": "true"}] if tagged else []
    resp = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t3.micro", TagSpecifications=[{"ResourceType": "instance", "Tags": tags}] if tags else [])
    return resp["Instances"][0]["InstanceId"]


# ---------------------------------------------------------------------------
# (a) Refuses without approval
# ---------------------------------------------------------------------------


@mock_aws
def test_refuses_without_approval():
    instance_id = _launch_instance(tagged=True)
    db = _FakeDB()
    proposal = _proposal(instance_id=instance_id, status="proposed")

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["PROPOSAL_NOT_APPROVED"]
    assert record.actual_aws_call_made is False


def test_refuses_when_execution_disabled():
    db = _FakeDB()
    proposal = _proposal(status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_enabled=False)):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["EXECUTION_DISABLED"]
    audit_docs = db._get("execution_audit")._docs
    assert len(audit_docs) == 1
    assert audit_docs[0]["status"] == "refused"
    assert audit_docs[0]["reason_codes"] == ["EXECUTION_DISABLED"]


def test_records_user_rejection_without_aws_call():
    db = _FakeDB()
    proposal = _proposal(status="pending_approval")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="simulation")):
        record = asyncio.run(
            actions.record_rejected_action(
                db,
                proposal,
                run_id=proposal["proposal_id"],
                rejected_by="user-1",
                reason="Not needed",
            )
        )

    assert record.status == "rejected"
    assert record.reason_codes == ["USER_REJECTED"]
    assert record.actual_aws_call_made is False
    assert record.after_state["rejected_by"] == "user-1"

    audit_docs = db._get("execution_audit")._docs
    assert len(audit_docs) == 1
    assert audit_docs[0]["status"] == "rejected"


# ---------------------------------------------------------------------------
# (b) Refuses without the allowlist tag
# ---------------------------------------------------------------------------


@mock_aws
def test_refuses_without_allowlist_tag():
    instance_id = _launch_instance(tagged=False)
    db = _FakeDB()
    proposal = _proposal(instance_id=instance_id, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["NOT_ALLOWLISTED"]
    assert record.actual_aws_call_made is False

    # The instance was never touched — still running.
    ec2 = boto3.client("ec2", region_name="us-east-1")
    state = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]
    assert state == "running"


# ---------------------------------------------------------------------------
# (c) Idempotent on repeat calls
# ---------------------------------------------------------------------------


@mock_aws
def test_idempotent_on_repeat_calls():
    instance_id = _launch_instance(tagged=True)
    db = _FakeDB()
    proposal = _proposal(instance_id=instance_id, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        first = asyncio.run(actions.execute_action(db, proposal))
        second = asyncio.run(actions.execute_action(db, proposal))

    assert first.status == "executed"
    assert first.actual_aws_call_made is True

    assert second.status in ("no_op", "executed")
    # The second call must not attempt another real mutation — either it
    # short-circuits on the idempotency_key (same execution_id as first)
    # or it re-describes and finds the instance already stopped (no_op).
    if second.execution_id == first.execution_id:
        pass  # idempotency-key cache hit
    else:
        assert second.status == "no_op"
        assert second.actual_aws_call_made is False

    ec2 = boto3.client("ec2", region_name="us-east-1")
    state = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]
    assert state == "stopped"


@mock_aws
def test_refuses_on_fresh_policy_denial_even_when_enabled_approved_and_allowlisted():
    """The third gate — a FRESH policy_engine.evaluate() against the
    resource's CURRENT live tags — refuses independently of the other two.
    Here execution is enabled, the proposal is approved, and the allowlist
    tag is present, but the instance is ALSO tagged Protected — the
    deterministic engine blocks protected resources unconditionally
    (services/policy/engine.py), so this must still refuse."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    resp = ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1, InstanceType="t3.micro",
        TagSpecifications=[{"ResourceType": "instance", "Tags": [
            {"Key": "cloudcare:managed", "Value": "true"},
            {"Key": "Protected", "Value": "true"},
        ]}],
    )
    instance_id = resp["Instances"][0]["InstanceId"]

    db = _FakeDB()
    proposal = _proposal(instance_id=instance_id, status="approved")

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["POLICY_DENIED"]


@mock_aws
def test_refuses_unapproved_and_unallowlisted_are_independent_checks():
    """Both gates fail independently — an unapproved AND unallowlisted
    proposal is refused for being unapproved FIRST (cheaper check, no AWS
    call needed), proving the approval gate doesn't depend on the tag
    check having run, and vice versa (see test_refuses_without_allowlist_tag,
    which uses an APPROVED proposal to prove the tag gate fires on its own)."""
    instance_id = _launch_instance(tagged=False)
    db = _FakeDB()
    proposal = _proposal(instance_id=instance_id, status="proposed")

    with patch("services.executor.actions.get_settings", return_value=_settings()):
        record = asyncio.run(actions.execute_action(db, proposal))

    assert record.status == "refused"
    assert record.reason_codes == ["PROPOSAL_NOT_APPROVED"]


# ---------------------------------------------------------------------------
# (d) Rolls back on verification failure
# ---------------------------------------------------------------------------


@mock_aws
def test_rolls_back_on_verification_failure():
    instance_id = _launch_instance(tagged=True)
    db = _FakeDB()
    proposal = _proposal(instance_id=instance_id, status="approved")
    settings = _settings(execution_mode="live")

    with patch("services.executor.actions.get_settings", return_value=settings), patch(
        "services.verifier.health.get_settings", return_value=settings
    ):
        record = asyncio.run(actions.execute_action(db, proposal))
        assert record.status == "executed"
        assert record.actual_aws_call_made is True

        # Simulate a CloudWatch alarm that fired for this instance —
        # the verifier's alarm check should catch this and roll back.
        cw = boto3.client("cloudwatch", region_name="us-east-1")
        cw.put_metric_alarm(
            AlarmName=f"cloudcare-test-{instance_id}",
            MetricName="StatusCheckFailed",
            Namespace="AWS/EC2",
            Statistic="Maximum",
            Period=60,
            EvaluationPeriods=1,
            Threshold=1,
            ComparisonOperator="GreaterThanOrEqualToThreshold",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        )
        cw.set_alarm_state(AlarmName=f"cloudcare-test-{instance_id}", StateValue="ALARM", StateReason="test")

        session = boto3.Session(region_name="us-east-1")
        result = asyncio.run(health.verify_execution(db, record, session, wait_seconds=0))

    assert result["verified"] is False
    assert result["rolled_back"] is True

    ec2 = boto3.client("ec2", region_name="us-east-1")
    state = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]
    assert state == "running"  # rolled back: start_instance undid the stop


# ---------------------------------------------------------------------------
# resize_instance — stop -> modify -> start, each step its own audit entry
# ---------------------------------------------------------------------------


@mock_aws
def test_resize_instance_writes_one_audit_entry_per_step():
    instance_id = _launch_instance(tagged=True)
    db = _FakeDB()
    proposal = _proposal(
        instance_id=instance_id, action_type="resize_instance", template_id="ec2.resize.v1", status="approved",
        parameters={"instance_id": instance_id, "region": "us-east-1", "target_type": "t3.small"},
    )

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        result = asyncio.run(actions.execute_action(db, proposal))

    assert result.status == "executed"
    assert result.step == "start"  # instance was running, so the final step is the restart

    audit_docs = db._get("execution_audit")._docs
    steps = {d["step"] for d in audit_docs if d["proposal_id"] == proposal["proposal_id"]}
    assert steps == {"stop", "modify_type", "start"}

    ec2 = boto3.client("ec2", region_name="us-east-1")
    instance = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
    assert instance["InstanceType"] == "t3.small"
    assert instance["State"]["Name"] == "running"


@mock_aws
def test_resize_instance_no_op_when_already_target_type():
    instance_id = _launch_instance(tagged=True)
    db = _FakeDB()
    proposal = _proposal(
        instance_id=instance_id, action_type="resize_instance", template_id="ec2.resize.v1", status="approved",
        parameters={"instance_id": instance_id, "region": "us-east-1", "target_type": "t3.micro"},  # same as launched
    )

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        result = asyncio.run(actions.execute_action(db, proposal))

    assert result.status == "no_op"
    assert result.actual_aws_call_made is False


# ---------------------------------------------------------------------------
# delete_volume — snapshots before deleting; rollback is manual
# ---------------------------------------------------------------------------


@mock_aws
def test_delete_volume_snapshots_first_and_rollback_requires_manual_action():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    volume = ec2.create_volume(AvailabilityZone="us-east-1a", Size=8, TagSpecifications=[{"ResourceType": "volume", "Tags": [{"Key": "cloudcare:managed", "Value": "true"}]}])
    volume_id = volume["VolumeId"]

    db = _FakeDB()
    proposal = _proposal(
        pid="p-vol", instance_id="unused", action_type="delete_volume", template_id="ebs.delete.v1", status="approved",
        parameters={"volume_id": volume_id, "region": "us-east-1"},
    )
    proposal["resource_arn"] = f"arn:aws:ec2:us-east-1:123456789012:volume/{volume_id}"

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        result = asyncio.run(actions.execute_action(db, proposal))

    assert result.status == "executed"
    assert result.actual_aws_call_made is True
    assert result.rollback_descriptor["action"] == "restore_volume_from_snapshot"
    assert result.rollback_descriptor["manual_action_required"] is True

    with pytest.raises(Exception):
        ec2.describe_volumes(VolumeIds=[volume_id])

    with patch("services.executor.actions.get_settings", return_value=_settings(execution_mode="live")):
        rollback_result = asyncio.run(actions.execute_rollback(db, result))
    assert rollback_result is None  # not auto-rollback-capable — descriptor is preserved for a human
