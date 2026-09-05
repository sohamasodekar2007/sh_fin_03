from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from apps.api.config import get_settings

logger = logging.getLogger(__name__)


class ExecutionQueueDisabled(Exception):
    """Raised when callers request SQS but it is not configured."""


class ExecutionQueueMessage(BaseModel):
    type: str = "execute_proposal"
    proposal_id: str
    tenant_id: str
    run_id: str
    requested_by: str | None = None
    source: str = "approval"
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def sqs_execution_configured(settings: Any | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.sqs_execution_enabled and settings.sqs_execution_queue_url)


def _sqs_client(settings: Any | None = None) -> Any:
    settings = settings or get_settings()
    session = boto3.Session(
        aws_access_key_id=getattr(settings, "aws_access_key_id", None) or None,
        aws_secret_access_key=getattr(settings, "aws_secret_access_key", None) or None,
        profile_name=getattr(settings, "aws_profile", None) or None,
        region_name=settings.aws_region,
    )
    kwargs: dict[str, Any] = {
        "region_name": settings.aws_region,
        "config": Config(
            retries={"total_max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=max(10, int(getattr(settings, "sqs_wait_time_seconds", 20)) + 5),
            user_agent_extra="cloudcare-sqs-execution",
        ),
    }
    if getattr(settings, "sqs_endpoint_url", ""):
        kwargs["endpoint_url"] = settings.sqs_endpoint_url
    return session.client("sqs", **kwargs)


async def ensure_execution_queue_indexes(db: Any) -> None:
    await db.execution_queue_jobs.create_index("message_id", unique=True, sparse=True, name="message_id_unique")
    await db.execution_queue_jobs.create_index("proposal_id", name="proposal_id")
    await db.execution_queue_jobs.create_index("tenant_id", name="tenant_id")


def build_execution_message(
    *,
    proposal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    requested_by: str | None = None,
    source: str = "approval",
) -> ExecutionQueueMessage:
    return ExecutionQueueMessage(
        proposal_id=proposal_id,
        tenant_id=tenant_id,
        run_id=run_id or proposal_id,
        requested_by=requested_by,
        source=source,
    )


async def enqueue_execution_message(db: Any, message: ExecutionQueueMessage) -> dict[str, Any]:
    settings = get_settings()
    if not sqs_execution_configured(settings):
        raise ExecutionQueueDisabled("SQS execution queue is not enabled or queue URL is missing.")

    payload = message.model_dump(mode="json")
    try:
        response = await asyncio.to_thread(
            _sqs_client(settings).send_message,
            QueueUrl=settings.sqs_execution_queue_url,
            MessageBody=json.dumps(payload, separators=(",", ":")),
            MessageAttributes={
                "message_type": {"DataType": "String", "StringValue": message.type},
                "tenant_id": {"DataType": "String", "StringValue": message.tenant_id},
                "proposal_id": {"DataType": "String", "StringValue": message.proposal_id},
            },
        )
    except ClientError:
        logger.exception("sqs: failed to enqueue proposal %s", message.proposal_id)
        raise

    receipt = {
        "message_id": response.get("MessageId"),
        "md5_of_body": response.get("MD5OfMessageBody"),
        "proposal_id": message.proposal_id,
        "tenant_id": message.tenant_id,
        "run_id": message.run_id,
        "status": "queued",
        "queued_at": datetime.now(timezone.utc),
    }
    await db.execution_queue_jobs.insert_one(receipt)
    return {k: v for k, v in receipt.items() if k != "_id"}


async def receive_execution_messages(limit: int | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    if not sqs_execution_configured(settings):
        raise ExecutionQueueDisabled("SQS execution queue is not enabled or queue URL is missing.")

    max_messages = limit or settings.sqs_max_messages
    response = await asyncio.to_thread(
        _sqs_client(settings).receive_message,
        QueueUrl=settings.sqs_execution_queue_url,
        MaxNumberOfMessages=max(1, min(10, int(max_messages))),
        WaitTimeSeconds=max(0, min(20, int(settings.sqs_wait_time_seconds))),
        VisibilityTimeout=max(0, int(settings.sqs_visibility_timeout_seconds)),
        MessageAttributeNames=["All"],
        AttributeNames=["SentTimestamp", "ApproximateReceiveCount"],
    )
    return response.get("Messages", [])


async def delete_execution_message(receipt_handle: str) -> None:
    settings = get_settings()
    if not sqs_execution_configured(settings):
        raise ExecutionQueueDisabled("SQS execution queue is not enabled or queue URL is missing.")
    await asyncio.to_thread(
        _sqs_client(settings).delete_message,
        QueueUrl=settings.sqs_execution_queue_url,
        ReceiptHandle=receipt_handle,
    )
