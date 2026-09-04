from threading import Lock
from typing import Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase

from packages.schemas.execution import ExecutionRecord, LiveExecutionRecord


class ExecutionAuditRepository(Protocol):
    def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ExecutionRecord | None:
        ...

    def save(
        self,
        record: ExecutionRecord,
    ) -> ExecutionRecord:
        ...


class InMemoryExecutionAuditRepository:
    """
    Local development and unit-test repository.
    """

    def __init__(self) -> None:
        self._records: dict[str, ExecutionRecord] = {}
        self._lock = Lock()

    def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ExecutionRecord | None:
        with self._lock:
            return self._records.get(idempotency_key)

    def save(
        self,
        record: ExecutionRecord,
    ) -> ExecutionRecord:
        with self._lock:
            existing = self._records.get(
                record.idempotency_key
            )

            if existing is not None:
                return existing

            self._records[
                record.idempotency_key
            ] = record

            return record

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def all(self) -> list[ExecutionRecord]:
        with self._lock:
            return list(self._records.values())


# ---------------------------------------------------------------------------
# Real Executor (Phase 6) — same repository shape (get_by_idempotency_key /
# save), a different record type. See packages/schemas/execution.py's
# module docstring for why LiveExecutionRecord is a separate model rather
# than a relaxed ExecutionRecord.
# ---------------------------------------------------------------------------

LIVE_AUDIT_COLLECTION = "execution_audit"


class LiveExecutionAuditRepository(Protocol):
    async def get_by_idempotency_key(self, idempotency_key: str) -> LiveExecutionRecord | None: ...

    async def save(self, record: LiveExecutionRecord) -> LiveExecutionRecord: ...


class MongoLiveExecutionAuditRepository:
    """Persists to the `execution_audit` collection. Idempotency is
    enforced the same way InMemoryExecutionAuditRepository does it — the
    first save for a given idempotency_key wins, a later save with the
    same key returns the original record untouched rather than
    overwriting it. Each resize_instance sub-step (stop/modify_type/start)
    gets its own idempotency_key (suffixed with the step name), so this
    natural per-key idempotency also gives resize its "each step needs its
    own audit entry" behaviour for free."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def get_by_idempotency_key(self, idempotency_key: str) -> LiveExecutionRecord | None:
        doc = await self._db[LIVE_AUDIT_COLLECTION].find_one({"idempotency_key": idempotency_key}, {"_id": 0})
        return LiveExecutionRecord(**doc) if doc else None

    async def save(self, record: LiveExecutionRecord) -> LiveExecutionRecord:
        existing = await self.get_by_idempotency_key(record.idempotency_key)
        if existing is not None:
            return existing
        await self._db[LIVE_AUDIT_COLLECTION].insert_one(record.model_dump(mode="json"))
        return record


async def ensure_live_audit_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[LIVE_AUDIT_COLLECTION].create_index("idempotency_key", unique=True, name="idempotency_key_unique")
    await db[LIVE_AUDIT_COLLECTION].create_index([("proposal_id", 1)], name="proposal_id")
    await db[LIVE_AUDIT_COLLECTION].create_index([("run_id", 1)], name="run_id")
