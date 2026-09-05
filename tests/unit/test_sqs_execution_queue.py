from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError

from apps.api.routers import supervisor
from packages.schemas.execution import LiveExecutionRecord
from services.messaging import sqs_execution_queue as queue
from services.messaging import sqs_execution_worker as worker


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self.indexes: list[tuple] = []
        self.updates: list[tuple[dict, dict]] = []

    async def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))
                return

    async def find_one(self, query, *_args):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None


class _FakeDB:
    def __init__(self):
        self.execution_queue_jobs = _FakeCollection()
        self.proposals = _FakeCollection()


class _FakeSqsClient:
    def __init__(self):
        self.sent: list[dict] = []

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "msg-123", "MD5OfMessageBody": "abc"}


def _settings(enabled=True):
    return SimpleNamespace(
        sqs_execution_enabled=enabled,
        sqs_execution_queue_url="https://sqs.ap-south-1.amazonaws.com/123456789012/cloudcare-execution",
        sqs_endpoint_url="",
        sqs_wait_time_seconds=20,
        sqs_visibility_timeout_seconds=300,
        sqs_max_messages=5,
        aws_region="ap-south-1",
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_profile=None,
    )


def test_enqueue_execution_message_sends_minimal_payload_and_records_receipt():
    db = _FakeDB()
    client = _FakeSqsClient()
    message = queue.build_execution_message(
        proposal_id="prop-1",
        tenant_id="tenant-1",
        run_id="run-1",
        requested_by="user-1",
        source="approval",
    )

    with patch("services.messaging.sqs_execution_queue.get_settings", return_value=_settings()), patch(
        "services.messaging.sqs_execution_queue._sqs_client", return_value=client
    ):
        receipt = asyncio.run(queue.enqueue_execution_message(db, message))

    assert receipt["message_id"] == "msg-123"
    assert db.execution_queue_jobs.docs[0]["status"] == "queued"
    sent = client.sent[0]
    assert sent["QueueUrl"].endswith("/cloudcare-execution")
    body = json.loads(sent["MessageBody"])
    assert body["type"] == "execute_proposal"
    assert body["proposal_id"] == "prop-1"
    assert body["tenant_id"] == "tenant-1"
    assert "resource_arn" not in body
    assert sent["MessageAttributes"]["proposal_id"]["StringValue"] == "prop-1"


def test_enqueue_execution_message_refuses_when_disabled():
    db = _FakeDB()
    message = queue.build_execution_message(proposal_id="prop-1", tenant_id="tenant-1")

    with patch("services.messaging.sqs_execution_queue.get_settings", return_value=_settings(enabled=False)):
        try:
            asyncio.run(queue.enqueue_execution_message(db, message))
        except queue.ExecutionQueueDisabled as exc:
            assert "not enabled" in str(exc)
        else:
            raise AssertionError("Expected ExecutionQueueDisabled")


def test_approval_flow_enqueues_execution_when_sqs_enabled():
    db = _FakeDB()
    proposal = {"proposal_id": "prop-1", "tenant_id": "tenant-1"}

    async def fake_enqueue(_db, message):
        assert message.proposal_id == "prop-1"
        assert message.tenant_id == "tenant-1"
        assert message.source == "approval"
        return {"message_id": "msg-approval"}

    with patch("apps.api.routers.supervisor.get_settings", return_value=_settings()), patch(
        "apps.api.routers.supervisor.sqs_execution_configured", return_value=True
    ), patch("apps.api.routers.supervisor.enqueue_execution_message", side_effect=fake_enqueue), patch(
        "services.executor.actions.execute_action"
    ) as execute_action:
        result = asyncio.run(
            supervisor._execute_after_approval(
                db,
                proposal,
                tenant_id="tenant-1",
                run_id="run-1",
            )
        )

    execute_action.assert_not_called()
    assert result["execution_status"] == "queued"
    assert result["execution_mode"] == "sqs"
    assert result["queue_message_id"] == "msg-approval"
    assert db.proposals.updates == [
        (
            {"proposal_id": "prop-1", "tenant_id": "tenant-1"},
            {"$set": {"status": "queued_for_execution", "execution_queue_message_id": "msg-approval"}},
        )
    ]


def test_worker_processes_queued_message_and_sends_completion_email():
    db = _FakeDB()
    db.proposals.docs.append(
        {
            "proposal_id": "prop-1",
            "tenant_id": "tenant-1",
            "status": "queued_for_execution",
            "resource_arn": "arn:aws:ec2:ap-south-1:123456789012:instance/i-1",
            "action_type": "stop_instance",
            "expected_monthly_savings": "42.00",
        }
    )
    db.users = _FakeCollection()
    db.users.docs.append({"tenant_id": "tenant-1", "email": "owner@example.com"})
    record = LiveExecutionRecord(
        idempotency_key="prop-1:stop_instance",
        proposal_id="prop-1",
        tenant_id="tenant-1",
        run_id="run-1",
        resource_arn="arn:aws:ec2:ap-south-1:123456789012:instance/i-1",
        resource_id="i-1",
        action_type="stop_instance",
        status="executed",
        reason_codes=["STOP_INSTANCE_REQUESTED"],
        execution_mode="simulation",
        actual_aws_call_made=False,
    )
    raw = {
        "MessageId": "msg-1",
        "ReceiptHandle": "receipt-1",
        "Body": json.dumps({"proposal_id": "prop-1", "tenant_id": "tenant-1", "run_id": "run-1"}),
    }

    with patch("services.messaging.sqs_execution_worker.execute_action", return_value=record) as execute_action, patch(
        "services.messaging.sqs_execution_worker.delete_execution_message"
    ) as delete_message, patch(
        "services.messaging.sqs_execution_worker.send_completion_email_sync", return_value=True
    ) as send_email, patch(
        "services.messaging.sqs_execution_worker.get_settings",
        return_value=SimpleNamespace(app_base_url="http://localhost:3000"),
    ):
        result = asyncio.run(worker._process_one_message(db, raw))

    assert result["status"] == "processed"
    execute_action.assert_awaited_once()
    delete_message.assert_awaited_once_with("receipt-1")
    send_email.assert_called_once()
    assert db.proposals.updates[0][1]["$set"]["status"] == "executing"
    assert db.proposals.updates[-1][1]["$set"]["status"] == "executed"
    assert db.execution_queue_jobs.updates[-1][1]["$set"]["status"] == "processed"


def test_worker_stops_on_sqs_access_denied_poll_error():
    error = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "not authorized"}},
        "ReceiveMessage",
    )

    worker._worker_state.update(
        {
            "running": False,
            "started_at": None,
            "last_poll_at": None,
            "last_processed_at": None,
            "last_error": None,
            "last_error_at": None,
            "processed_total": 0,
        }
    )
    with patch(
        "services.messaging.sqs_execution_worker.process_execution_queue_batch",
        new_callable=AsyncMock,
        side_effect=error,
    ), patch(
        "services.messaging.sqs_execution_worker.get_settings",
        return_value=SimpleNamespace(sqs_max_messages=5),
    ):
        asyncio.run(worker._worker_loop())

    assert worker._worker_state["running"] is False
    assert "not authorized" in worker._worker_state["last_error"]
    assert worker._worker_state["last_error_at"]
