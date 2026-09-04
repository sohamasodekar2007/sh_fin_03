"""
MongoDB connection layer.

PLACEHOLDER: this module works out of the box against a local MongoDB
(mongodb://localhost:27017) for development, or against a real Atlas
cluster once you set MONGODB_URI in .env (see .env.example).

None of the routers actually query Mongo yet — they return mock data so the
frontend has something to render today. Each router has a `# TODO: replace
with Mongo query` comment showing exactly where to swap it in. A `seed.py`
script is provided to load the same mock data into Mongo once you're ready.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from apps.api.config import get_settings

import asyncio
import time

_client: AsyncIOMotorClient | None = None
_MONGO_UNAVAILABLE_UNTIL = 0.0
_MONGO_RECHECK_SECONDS = 5.0
_MONGO_SERVER_SELECTION_TIMEOUT_MS = 1500


def get_client() -> AsyncIOMotorClient:
    global _client
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _client is not None:
        # Check if the client is bound to a closed or different loop (common in pytest)
        client_loop = getattr(_client, "get_io_loop", lambda: None)()
        if client_loop is None or client_loop.is_closed() or (current_loop and client_loop != current_loop):
            _client = None

    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(
            settings.mongodb_uri,
            tz_aware=True,
            serverSelectionTimeoutMS=_MONGO_SERVER_SELECTION_TIMEOUT_MS,
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


async def ping() -> bool:
    """Health check used by /health. Returns False if Mongo isn't reachable
    yet — that's expected until you've filled in a real MONGODB_URI."""
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:
        return False


async def mongo_available(timeout_seconds: float = 1.5) -> bool:
    """Return quickly when Mongo is unreachable.

    Several development/demo endpoints have honest empty-state fallbacks. A
    short cached probe keeps those routes from blocking on Motor's full server
    selection timeout for every dashboard request while Mongo is down.
    """
    global _MONGO_UNAVAILABLE_UNTIL
    now = time.monotonic()
    if now < _MONGO_UNAVAILABLE_UNTIL:
        return False
    try:
        await asyncio.wait_for(get_client().admin.command("ping"), timeout=timeout_seconds)
        _MONGO_UNAVAILABLE_UNTIL = 0.0
        return True
    except Exception:
        _MONGO_UNAVAILABLE_UNTIL = time.monotonic() + _MONGO_RECHECK_SECONDS
        return False
