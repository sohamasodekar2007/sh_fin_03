"""
Seed script — onboards one demo CloudAccount per provider (aws/gcp/azure/
onprem) for the demo tenant, so POST /v1/runs has real Mongo-persisted
accounts to iterate instead of always falling back to
services/orchestrator/nodes.py::monitor()'s in-memory default fleet.

Users are NOT seeded here — NextAuth + FastAPI's auto-provisioning
(apps/api/dependencies.py::get_current_user) creates a `users` document the
first time someone actually signs in, so there's nothing meaningful to
pre-seed.

Run with (from the repo root, apps/api/.env populated):
    python -m scripts.seed
"""

import asyncio

from apps.api.db import get_db
from packages.schemas.schemas import CloudAccount

TENANT_ID = "demo-tenant"


async def seed() -> None:
    db = get_db()

    await db.cloud_accounts.delete_many({"tenant_id": TENANT_ID})
    accounts = [
        CloudAccount(tenant_id=TENANT_ID, provider="aws", display_name="Demo AWS Sandbox", account_id="123456789012", region="us-east-1"),
        CloudAccount(tenant_id=TENANT_ID, provider="gcp", display_name="Demo GCP Project", account_id="cloudcare-demo-project", region="us-central1"),
        CloudAccount(tenant_id=TENANT_ID, provider="azure", display_name="Demo Azure Subscription", account_id="cloudcare-demo-subscription", region="eastus"),
        CloudAccount(tenant_id=TENANT_ID, provider="onprem", display_name="Demo Datacenter", account_id="dc-pune-01", region="dc-pune-01"),
    ]
    await db.cloud_accounts.insert_many([a.model_dump() for a in accounts])
    print(f"Seeded {len(accounts)} demo cloud accounts for tenant={TENANT_ID}.")

    await db.cloud_accounts.create_index("tenant_id")
    await db.runs.create_index("tenant_id")
    print("Indexes created. Done.")


if __name__ == "__main__":
    asyncio.run(seed())
