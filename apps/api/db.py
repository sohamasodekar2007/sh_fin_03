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

_client: AsyncIOMotorClient | None = None


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
        _client = AsyncIOMotorClient(settings.mongodb_uri, tz_aware=True)
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
