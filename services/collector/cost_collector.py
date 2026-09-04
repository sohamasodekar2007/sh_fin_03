from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from packages.schemas.cloud_metrics import DailyCost


class CostExplorerCollectionError(Exception):
    """Raised when Cost Explorer data cannot be collected."""


class CostExplorerCollector:
    def __init__(self, cost_explorer_client: Any) -> None:
        self.cost_explorer_client = cost_explorer_client

    def collect_daily_costs(self, days: int = 7) -> list[DailyCost]:
        if days < 1:
            raise ValueError("days must be at least 1")

        # Cost Explorer End date is exclusive.
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)

        request = {
            "TimePeriod": {
                "Start": start_date.isoformat(),
                "End": end_date.isoformat(),
            },
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
        }

        collected_costs: list[DailyCost] = []
        next_page_token: str | None = None

        while True:
            if next_page_token:
                request["NextPageToken"] = next_page_token
            else:
                request.pop("NextPageToken", None)

            try:
                response = self.cost_explorer_client.get_cost_and_usage(**request)
            except ClientError as error:
                error_code = error.response.get("Error", {}).get(
                    "Code",
                    "UNKNOWN_AWS_ERROR",
                )

                if error_code == "DataUnavailableException":
                    return collected_costs

                raise CostExplorerCollectionError(
                    f"Cost Explorer collection failed: {error_code}"
                ) from error

            for result in response.get("ResultsByTime", []):
                total = result.get("Total", {}).get("UnblendedCost", {})

                collected_costs.append(
                    DailyCost(
                        usage_date=result["TimePeriod"]["Start"],
                        amount=Decimal(total.get("Amount", "0")),
                        currency=total.get("Unit", "USD"),
                        estimated=result.get("Estimated", False),
                    )
                )

            next_page_token = response.get("NextPageToken")

            if not next_page_token:
                break

        return collected_costs
