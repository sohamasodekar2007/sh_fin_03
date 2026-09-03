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
    latest_datapoint_at: datetime | None = None


class DailyCost(BaseModel):
    usage_date: date
    amount: Decimal = Field(default=Decimal("0"))
    currency: str = "USD"
    estimated: bool = False
    metric: str = "UnblendedCost"
