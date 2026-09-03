"""
Fuse a real FOCUS 1.0 sample dataset (or an AWS Cost and Usage Report
export) into Mongo, for judging with real external data gravity instead of
only the synthetic fleets in services/collector/mock_provider.py and
services/focus/sample_data.py.

Not bundled in the repo — FOCUS sample files run tens of MB and are
licensed separately by the FinOps Foundation. To use this:

    1. Download a FOCUS 1.0 sample CSV from https://focus.finops.org
       ("FOCUS Sample Data Files") or export an AWS CUR 2.0 report
       (which is natively FOCUS-conformant) to CSV.
    2. Save it as scripts/data/focus_sample.csv (gitignored).
    3. pip install pandas (not in apps/api/requirements.txt — this script
       is a one-off, not a runtime dependency).
    4. Run: python -m scripts.seed_focus_sample

Column mapping is deliberately thin: a real FOCUS export already uses the
same column names as packages/schemas/unified_resource.py::UnifiedResource
(BilledCost, EffectiveCost, ServiceCategory, ChargePeriodStart/End, ...) —
this script lower-snake-cases them and fills in the runtime-telemetry
fields UnifiedResource has that FOCUS itself doesn't (metrics_*) with
None, since a cost export carries no utilization data.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "focus_sample.csv"

_FOCUS_COLUMN_MAP = {
    "ResourceId": "id",
    "ProviderName": "provider",
    "BillingAccountId": "account_id",
    "ResourceName": "resource_name",
    "ResourceType": "resource_type",
    "ServiceCategory": "service_category",
    "ServiceName": "service_name",
    "RegionId": "region",
    "AvailabilityZone": "availability_zone",
    "BilledCost": "billed_cost",
    "EffectiveCost": "effective_cost",
    "ListCost": "list_cost",
    "BillingCurrency": "pricing_currency",
    "ChargeCategory": "charge_category",
    "ChargePeriodStart": "billing_period_start",
    "ChargePeriodEnd": "billing_period_end",
}


async def seed_from_csv(path: Path) -> None:
    import pandas as pd

    from apps.api.db import get_db

    df = pd.read_csv(path)
    df = df.rename(columns=_FOCUS_COLUMN_MAP)
    df["provider"] = df["provider"].str.lower().replace({"amazon web services": "aws", "microsoft azure": "azure", "google cloud": "gcp"})

    records = df.to_dict(orient="records")
    db = get_db()
    await db.focus_sample_resources.delete_many({})
    await db.focus_sample_resources.insert_many(records)
    print(f"Loaded {len(records)} FOCUS rows from {path} into the focus_sample_resources collection.")


if __name__ == "__main__":
    if not DATA_PATH.exists():
        print(f"No FOCUS sample file at {DATA_PATH} — see this script's module docstring for how to get one.")
        sys.exit(1)
    asyncio.run(seed_from_csv(DATA_PATH))
