from threading import Lock
from typing import Protocol

from packages.schemas.execution import ExecutionRecord


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
