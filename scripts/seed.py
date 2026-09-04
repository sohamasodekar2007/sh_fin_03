"""
Seed script — creates demo data across all four Day-1 collections
(users, cloud_accounts, resources, proposals) so the app has real Mongo
documents to run against instead of the in-memory mock_data.py.

Run it with:  python -m scripts.seed
(requires MONGODB_URI to be set in backend/.env, pointing at a real Atlas
cluster or a local `mongod` instance)
"""

import asyncio
from decimal import Decimal
from uuid import uuid4

from apps.api.db import get_db
from apps.api.mock_data import AGENT_ACTIVITY, RESOURCES
from packages.schemas.schemas import ActionProposal, CloudAccount
from apps.api.security import hash_password


async def seed():
    db = get_db()

    # --- users ---------------------------------------------------------
    await db.users.delete_many({})
    await db.users.insert_many([
        {
            "user_id": "sumaira",
            "tenant_id": "demo-tenant",
            "hashed_password": hash_password("changeme123"),
            "full_name": "Sumaira",
            "email": "teamalpha817@gmail.com",
        },
    ])
    print("Seeded 1 demo user (user_id=sumaira, email=teamalpha817@gmail.com, password=changeme123 — change after first login)")

    # --- cloud_accounts --------------------------------------------------
    await db.cloud_accounts.delete_many({})
    await db.cloud_accounts.insert_one(
        CloudAccount(
            tenant_id="demo-tenant",
            account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/CloudCareReadOnly",
            external_id=str(uuid4()),
            region="ap-south-1",
            status="pending",
        ).model_dump()
    )
    print("Seeded 1 demo cloud account (status=pending until Soham validates it via STS)")

    # --- resources ---------------------------------------------------------
    # tenant_id defaults to "demo-tenant" on the Resource model, matching
    # the demo user's tenant — this is what makes /v1/resources (now
    # tenant-scoped, Days 5-7) return this seed data for the demo user.
    await db.resources.delete_many({})
    await db.resources.insert_many([r.model_dump() for r in RESOURCES])
    print(f"Seeded {len(RESOURCES)} resources")

    # --- proposals -----------------------------------------------------
    await db.proposals.delete_many({})
    proposals = [
        ActionProposal(
            proposal_id=uuid4(),
            resource_arn="arn:aws:ec2:ap-south-1:demo:instance/i-0912ab3c4d5e6f701",
            action_type="stop_instance",
            template_id="ec2.stop.v1",
            parameters={"instance_id": "i-0912ab3c4d5e6f701", "region": "ap-south-1"},
            expected_monthly_savings=Decimal("14.20"),
            risk_level="low",
            confidence=0.92,
            requires_human_approval=False,
            status="executed",
        ),
        ActionProposal(
            proposal_id=uuid4(),
            resource_arn="arn:aws:ec2:ap-south-1:demo:instance/i-0455cd8e9f0a1b234",
            action_type="resize_instance",
            template_id="ec2.resize.v1",
            parameters={"instance_id": "i-0455cd8e9f0a1b234", "region": "ap-south-1", "target_type": "t3.medium"},
            expected_monthly_savings=Decimal("22.00"),
            risk_level="medium",
            confidence=0.74,
            requires_human_approval=True,
            status="proposed",
        ),
    ]
    docs = []
    for p in proposals:
        d = p.model_dump()
        d["proposal_id"] = str(d["proposal_id"])
        d["expected_monthly_savings"] = float(d["expected_monthly_savings"])
        docs.append(d)
    await db.proposals.insert_many(docs)
    print(f"Seeded {len(proposals)} proposals")

    # --- agent_activity --------------------------------------------------
    await db.agent_activity.delete_many({})
    await db.agent_activity.insert_many([a.model_dump() for a in AGENT_ACTIVITY])
    print(f"Seeded {len(AGENT_ACTIVITY)} agent activity entries")

    # --- indexes ---------------------------------------------------------
    await db.users.create_index("user_id", unique=True)
    await db.cloud_accounts.create_index("tenant_id")
    await db.resources.create_index("environment")
    await db.proposals.create_index("status")
    print("Indexes created. Done.")


if __name__ == "__main__":
    asyncio.run(seed())
