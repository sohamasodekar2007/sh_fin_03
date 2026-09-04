"""
HMAC-signed, single-use approval tokens for the Supervisor's email
approve/reject links (Phase 5, GET /v1/approvals/email/{token}).

Format:  base64url(payload_json) + "." + hex_hmac_sha256(payload_bytes, secret)
Payload: {"proposal_id": str, "action": "approve"|"reject", "tenant_id": str,
          "nonce": str (uuid4), "exp": unix_timestamp}

Signature + expiry are verified here, by decode_approval_token(). Single-use
is NOT enforced here — this module never touches a database — it's
enforced by consume_nonce_or_raise() recording the nonce in the
`used_approval_nonces` collection (unique index on `nonce`) before the
caller applies the decision. A duplicate insert (replayed link) raises
InvalidApprovalToken same as a bad signature, so every failure mode of
"click twice" — forwarded email, browser back-button, double-click —
collapses to the same refusal.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Literal
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

TOKEN_TTL_SECONDS = 24 * 60 * 60

ApprovalAction = Literal["approve", "reject"]


class InvalidApprovalToken(Exception):
    pass


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def issue_approval_token(proposal_id: str, action: ApprovalAction, tenant_id: str, secret: str) -> str:
    payload = {
        "proposal_id": proposal_id,
        "action": action,
        "tenant_id": tenant_id,
        "nonce": str(uuid4()),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = _sign(payload_bytes, secret)
    return f"{payload_b64}.{signature}"


def decode_approval_token(token: str, secret: str) -> dict[str, Any]:
    """Verifies signature + expiry. Raises InvalidApprovalToken on any
    tamper, malformed input, wrong secret, or expiry — never returns a
    payload that hasn't passed every check."""
    try:
        payload_b64, signature = token.split(".", 1)
        padding = "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
    except Exception as exc:
        raise InvalidApprovalToken("Malformed token") from exc

    expected_signature = _sign(payload_bytes, secret)
    if not hmac.compare_digest(expected_signature, signature):
        raise InvalidApprovalToken("Signature mismatch — tampered token or wrong secret")

    try:
        payload = json.loads(payload_bytes)
    except Exception as exc:
        raise InvalidApprovalToken("Malformed payload") from exc

    for key in ("proposal_id", "action", "tenant_id", "nonce", "exp"):
        if key not in payload:
            raise InvalidApprovalToken(f"Missing field: {key}")

    if payload["action"] not in ("approve", "reject"):
        raise InvalidApprovalToken("Invalid action")

    if int(payload["exp"]) < int(time.time()):
        raise InvalidApprovalToken("Token expired")

    return payload


async def consume_nonce_or_raise(db: AsyncIOMotorDatabase, nonce: str) -> None:
    """Atomically claims a nonce. Relies on a unique index on `nonce`
    (see ensure_approval_indexes) — a second insert of the same nonce
    raises a duplicate-key error, which is what makes this single-use."""
    try:
        from datetime import datetime, timezone

        await db.used_approval_nonces.insert_one({"nonce": nonce, "used_at": datetime.now(timezone.utc)})
    except Exception as exc:
        raise InvalidApprovalToken("Token already used") from exc


async def ensure_approval_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.used_approval_nonces.create_index("nonce", unique=True, name="nonce_unique")
    # A little over the 24h token TTL, so we never expire a nonce while its
    # token could still be valid.
    await db.used_approval_nonces.create_index("used_at", expireAfterSeconds=TOKEN_TTL_SECONDS + 3600, name="nonce_ttl")
