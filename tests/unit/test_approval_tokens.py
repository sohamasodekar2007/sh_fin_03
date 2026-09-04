from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.supervisor.approval_tokens import (
    InvalidApprovalToken,
    consume_nonce_or_raise,
    decode_approval_token,
    issue_approval_token,
)

SECRET = "test-approval-secret"


def _mock_db_with_unique_nonces():
    """A unique index on `nonce` means a second insert of the same nonce
    raises — this fakes that behaviour without a real Mongo."""
    mock_db = MagicMock()
    used: set[str] = set()

    async def insert_one(doc):
        if doc["nonce"] in used:
            raise Exception("E11000 duplicate key error")
        used.add(doc["nonce"])

    mock_db.used_approval_nonces.insert_one = AsyncMock(side_effect=insert_one)
    return mock_db


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------


def test_issued_token_decodes_back_to_the_same_payload():
    token = issue_approval_token("p1", "approve", "demo-tenant", SECRET)
    payload = decode_approval_token(token, SECRET)

    assert payload["proposal_id"] == "p1"
    assert payload["action"] == "approve"
    assert payload["tenant_id"] == "demo-tenant"
    assert "nonce" in payload


# ---------------------------------------------------------------------------
# Expired token rejected
# ---------------------------------------------------------------------------


def test_expired_token_is_rejected():
    token = issue_approval_token("p1", "approve", "demo-tenant", SECRET)

    # decode_approval_token only checks the "exp" field embedded in the
    # signed payload — so forging an already-expired payload with the same
    # secret is the correct way to test the expiry branch (mocking `time`
    # would also freeze token issuance, which isn't what we want to test).
    import base64
    import hashlib
    import hmac
    import json

    payload = {
        "proposal_id": "p1",
        "action": "approve",
        "tenant_id": "demo-tenant",
        "nonce": "fixed-nonce",
        "exp": int(time.time()) - 10,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(SECRET.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    expired_token = f"{payload_b64}.{signature}"

    with pytest.raises(InvalidApprovalToken):
        decode_approval_token(expired_token, SECRET)


# ---------------------------------------------------------------------------
# Tampered payload rejected
# ---------------------------------------------------------------------------


def test_tampered_payload_is_rejected():
    token = issue_approval_token("p1", "approve", "demo-tenant", SECRET)
    payload_b64, signature = token.split(".", 1)

    # Flip the action from "approve" to "reject" by re-encoding a modified
    # payload but keeping the ORIGINAL signature — simulates an attacker
    # editing the token without knowing the secret.
    import base64
    import json

    padding = "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    payload["action"] = "reject"
    tampered_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    tampered_token = f"{tampered_b64}.{signature}"

    with pytest.raises(InvalidApprovalToken):
        decode_approval_token(tampered_token, SECRET)


def test_token_signed_with_wrong_secret_is_rejected():
    token = issue_approval_token("p1", "approve", "demo-tenant", "a-different-secret")

    with pytest.raises(InvalidApprovalToken):
        decode_approval_token(token, SECRET)


def test_malformed_token_is_rejected():
    with pytest.raises(InvalidApprovalToken):
        decode_approval_token("not-a-real-token", SECRET)


# ---------------------------------------------------------------------------
# Replayed nonce rejected
# ---------------------------------------------------------------------------


def test_replayed_nonce_is_rejected():
    db = _mock_db_with_unique_nonces()

    async def _run():
        await consume_nonce_or_raise(db, "nonce-123")  # first use succeeds
        with pytest.raises(InvalidApprovalToken):
            await consume_nonce_or_raise(db, "nonce-123")  # replay — rejected

    asyncio.run(_run())


def test_two_different_nonces_both_succeed():
    db = _mock_db_with_unique_nonces()

    async def _run():
        await consume_nonce_or_raise(db, "nonce-a")
        await consume_nonce_or_raise(db, "nonce-b")  # different nonce — not a replay

    asyncio.run(_run())
