"""
Azure Cost Management collector — daily ActualCost, scoped to
/subscriptions/{AZURE_SUBSCRIPTION_ID} and grouped by ResourceId.

Unlike AWS's Cost Explorer (services/collector/cost_collector.py — daily
totals with no resource dimension), Cost Management can group by ResourceId
directly, so services/focus/mappers/azure.py gets a real per-resource cost
instead of AWS's equal-split allocation.

RATE LIMITING: the Cost Management Query API is aggressively rate-limited —
a 429 comes with a Retry-After header that must be honoured, not retried
blindly. This collector retries once, waiting exactly as long as the header
says (capped, so a misbehaving header can't hang a request indefinitely),
then gives up and lets the caller (the FOCUS mapper) fall back to
synthesis rather than returning zero rows and pretending that's real data.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from packages.azure.session import AzureClientFactory
from packages.schemas.cloud_metrics import AzureResourceDailyCost

_MAX_RETRY_WAIT_SECONDS = 30


class AzureCostCollectionError(Exception):
    """Raised when Azure Cost Management data cannot be collected."""


class AzureCostRateLimitedError(AzureCostCollectionError):
    """Raised when the Cost Management API is still rate-limited after
    honouring one Retry-After wait."""


def _retry_after_seconds(error: HttpResponseError) -> float | None:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) if response else None
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return min(float(raw), _MAX_RETRY_WAIT_SECONDS)
    except (TypeError, ValueError):
        return None


def _is_rate_limited(error: HttpResponseError) -> bool:
    status_code = getattr(error, "status_code", None)
    return status_code == 429


def _build_query(start: date, end: date) -> Any:
    from azure.mgmt.costmanagement.models import (
        QueryAggregation,
        QueryDataset,
        QueryDefinition,
        QueryGrouping,
        QueryTimePeriod,
    )

    return QueryDefinition(
        type="ActualCost",
        timeframe="Custom",
        time_period=QueryTimePeriod(
            from_property=datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
            to=datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
        ),
        dataset=QueryDataset(
            granularity="Daily",
            aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
            grouping=[QueryGrouping(type="Dimension", name="ResourceId")],
        ),
    )


def _parse_usage_date(raw: Any) -> date:
    """Cost Management returns UsageDate as an int in YYYYMMDD form (e.g.
    20240915), not an ISO string."""
    if isinstance(raw, date):
        return raw
    if isinstance(raw, int):
        return datetime.strptime(str(raw), "%Y%m%d").date()
    return date.fromisoformat(str(raw))


class AzureCostCollector:
    def __init__(self, client_factory: AzureClientFactory) -> None:
        self.client_factory = client_factory

    def _query_once(self, query: Any) -> Any:
        client = self.client_factory.cost_management_client()
        scope = self.client_factory.subscription_scope()
        return client.query.usage(scope=scope, parameters=query)

    def collect_daily_costs(self, days: int = 30) -> list[AzureResourceDailyCost]:
        if days < 1:
            raise ValueError("days must be at least 1")

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        query = _build_query(start_date, end_date)

        try:
            result = self._query_once(query)
        except ClientAuthenticationError as error:
            raise AzureCostCollectionError(
                f"Azure cost collection failed: authentication error ({error})"
            ) from error
        except HttpResponseError as error:
            if not _is_rate_limited(error):
                error_code = error.error.code if error.error else "UNKNOWN_AZURE_ERROR"
                raise AzureCostCollectionError(f"Azure cost collection failed: {error_code}") from error

            wait_seconds = _retry_after_seconds(error)
            if wait_seconds is None:
                raise AzureCostRateLimitedError(
                    "Azure Cost Management API rate-limited (429) with no Retry-After header"
                ) from error

            time.sleep(wait_seconds)
            try:
                result = self._query_once(query)
            except HttpResponseError as retry_error:
                raise AzureCostRateLimitedError(
                    f"Azure Cost Management API still rate-limited after honouring "
                    f"a {wait_seconds}s Retry-After wait"
                ) from retry_error

        if not result or not result.columns or not result.rows:
            return []

        column_names = [c.name for c in result.columns]
        try:
            cost_idx = column_names.index("Cost")
        except ValueError:
            cost_idx = column_names.index("PreTaxCost")
        date_idx = column_names.index("UsageDate")
        resource_idx = column_names.index("ResourceId")
        currency_idx = column_names.index("Currency") if "Currency" in column_names else None

        costs: list[AzureResourceDailyCost] = []
        for row in result.rows:
            resource_id = row[resource_idx]
            if not resource_id:
                continue
            try:
                cost_value = Decimal(str(row[cost_idx]))
            except (InvalidOperation, TypeError):
                continue

            costs.append(
                AzureResourceDailyCost(
                    resource_id=str(resource_id),
                    usage_date=_parse_usage_date(row[date_idx]),
                    cost=cost_value,
                    currency=str(row[currency_idx]) if currency_idx is not None else "USD",
                )
            )

        return costs
