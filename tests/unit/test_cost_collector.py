from decimal import Decimal
from unittest.mock import Mock

from botocore.exceptions import ClientError

from services.collector.cost_collector import CostExplorerCollector


def test_collect_daily_costs_returns_normalized_results() -> None:
    client = Mock()

    client.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {
                    "Start": "2026-07-16",
                    "End": "2026-07-17",
                },
                "Total": {
                    "UnblendedCost": {
                        "Amount": "0.125",
                        "Unit": "USD",
                    }
                },
                "Estimated": False,
            }
        ]
    }

    collector = CostExplorerCollector(client)
    result = collector.collect_daily_costs(days=7)

    assert len(result) == 1
    assert result[0].amount == Decimal("0.125")
    assert result[0].currency == "USD"
    assert result[0].estimated is False


def test_collect_daily_costs_handles_zero_cost() -> None:
    client = Mock()

    client.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {
                    "Start": "2026-07-17",
                    "End": "2026-07-18",
                },
                "Total": {},
                "Estimated": True,
            }
        ]
    }

    collector = CostExplorerCollector(client)
    result = collector.collect_daily_costs(days=1)

    assert result[0].amount == Decimal("0")
    assert result[0].estimated is True


def test_collect_daily_costs_handles_unavailable_cost_data() -> None:
    client = Mock()
    client.get_cost_and_usage.side_effect = ClientError(
        error_response={
            "Error": {
                "Code": "DataUnavailableException",
                "Message": "Data is not available",
            }
        },
        operation_name="GetCostAndUsage",
    )

    collector = CostExplorerCollector(client)
    result = collector.collect_daily_costs(days=7)

    assert result == []
