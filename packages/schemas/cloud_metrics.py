from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EC2CpuMetric(BaseModel):
    instance_id: str
    region: str
    metric_name: str = "CPUUtilization"
    unit: str = "Percent"
    window_start: datetime
    window_end: datetime
    datapoint_count: int = 0
    average_cpu_percent: float | None = None
    maximum_cpu_percent: float | None = None
    # NetworkIn + NetworkOut (bytes), summed per period then averaged/maxed
    # across the window — real CloudWatch data (no agent required), unlike
    # memory which genuinely has no metric without one. None when the
    # instance had no datapoints in the window; never fabricated.
    average_network_bytes: float | None = None
    maximum_network_bytes: float | None = None
    latest_datapoint_at: datetime | None = None


class DailyCost(BaseModel):
    usage_date: date
    amount: Decimal = Field(default=Decimal("0"))
    currency: str = "USD"
    estimated: bool = False
    metric: str = "UnblendedCost"


class AzureResourceDailyCost(BaseModel):
    """Unlike AWS's DailyCost (account-level only — Cost Explorer's daily
    total has no resource dimension), Azure Cost Management can group
    ActualCost by ResourceId directly, so this carries a real per-resource
    figure rather than needing the equal-split allocation
    services/focus/mappers/aws.py has to fall back to."""

    resource_id: str
    usage_date: date
    cost: Decimal = Field(default=Decimal("0"))
    currency: str = "USD"
