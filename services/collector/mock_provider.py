"""
Mock AWS Data Provider — Generates realistic observation bundles for Monitor Agent (Observe).
Outputs ~20-30 EC2 instances + EBS volumes matching the CloudCareState.observation contract.
Includes idle, oversized, unattached EBS, non-prod schedule, and spend anomaly patterns.
"""

import random
from datetime import datetime, date, timedelta, timezone
from typing import Any

from packages.schemas.cloud_metrics import EC2CpuMetric, DailyCost
from packages.schemas.cloud_snapshot import CloudSnapshot, CollectionIssue


def generate_mock_observation_bundle(account_id: str = "123456789012", region: str = "us-east-1") -> CloudSnapshot:
    """Generate 25 synthetic resources with CloudWatch CPU metrics and 30-day cost history."""
    now = datetime.now(timezone.utc)
    today = date.today()
    random.seed(101)  # Stable deterministic seed

    resources: list[dict[str, Any]] = []
    cpu_metrics: list[EC2CpuMetric] = []
    
    # ---------------------------------------------------------------------------
    # 1. Generate 20 EC2 Instances
    # ---------------------------------------------------------------------------
    instance_specs = [
        # Idle instances (CPU < 5%)
        {"type": "t3.large", "env": "dev", "owner": "team-alpha", "pattern": "idle", "cost": 6.80},
        {"type": "c5.xlarge", "env": "staging", "owner": "data-eng", "pattern": "idle", "cost": 12.40},
        {"type": "t3.medium", "env": "dev", "owner": "qa-team", "pattern": "idle", "cost": 3.20},
        {"type": "m5.large", "env": "staging", "owner": "backend-team", "pattern": "idle", "cost": 8.50},
        {"type": "t3.xlarge", "env": "dev", "owner": "mobile-team", "pattern": "idle", "cost": 14.10},

        # Oversized instances (CPU < 25%, High Cost)
        {"type": "c5.4xlarge", "env": "staging", "owner": "analytics", "pattern": "oversized", "cost": 42.50},
        {"type": "r5.2xlarge", "env": "staging", "owner": "data-eng", "pattern": "oversized", "cost": 31.20},
        {"type": "m5.4xlarge", "env": "production", "owner": "core-services", "pattern": "oversized", "cost": 48.00},

        # Non-prod off-hours schedule candidate (low overnight CPU)
        {"type": "c5.2xlarge", "env": "staging", "owner": "qa-team", "pattern": "nonprod_schedule", "cost": 21.00},
        {"type": "t3.2xlarge", "env": "dev", "owner": "frontend-team", "pattern": "nonprod_schedule", "cost": 18.50},

        # Normal / Healthy instances
        {"type": "t3.medium", "env": "production", "owner": "core-services", "pattern": "normal", "cost": 3.50},
        {"type": "m5.large", "env": "production", "owner": "backend-team", "pattern": "normal", "cost": 8.20},
        {"type": "c5.large", "env": "production", "owner": "api-gateway", "pattern": "normal", "cost": 7.10},
        {"type": "t3.large", "env": "production", "owner": "auth-service", "pattern": "normal", "cost": 6.50},
        {"type": "m5.xlarge", "env": "production", "owner": "database-team", "pattern": "normal", "cost": 16.00},
        {"type": "r5.xlarge", "env": "production", "owner": "cache-cluster", "pattern": "normal", "cost": 18.20},
        {"type": "t3.small", "env": "dev", "owner": "sandbox", "pattern": "normal", "cost": 1.80},
        {"type": "c5.xlarge", "env": "production", "owner": "payments-team", "pattern": "normal", "cost": 12.00},
        {"type": "m5.2xlarge", "env": "production", "owner": "search-cluster", "pattern": "normal", "cost": 28.50},
        {"type": "t3.medium", "env": "staging", "owner": "staging-internal", "pattern": "normal", "cost": 3.40},
    ]

    for idx, spec in enumerate(instance_specs, start=1):
        inst_id = f"i-{idx:04d}a1b2c3d4"
        name = f"cloudcare-{spec['env']}-{spec['owner']}-{idx:02d}"
        
        resource_dict = {
            "schema_version": "1.0",
            "provider": "aws",
            "resource_type": "ec2_instance",
            "region": region,
            "availability_zone": f"{region}a",
            "resource_id": inst_id,
            "instance_id": inst_id,
            "name": name,
            "environment": spec["env"],
            "instance_type": spec["type"],
            "state": "running",
            "launched_at": (now - timedelta(days=45)).isoformat(),
            "collected_at": now.isoformat(),
            "monthly_cost_usd": round(spec["cost"] * 30, 2),
            "tags": {
                "Name": name,
                "Environment": spec["env"],
                "Owner": spec["owner"],
                "CostCenter": "Engineering",
                "Pattern": spec["pattern"]
            },
            "warnings": []
        }
        resources.append(resource_dict)

        # Generate CPU time series based on pattern
        if spec["pattern"] == "idle":
            cpu_series = [round(random.uniform(0.5, 3.2), 2) for _ in range(14)]
        elif spec["pattern"] == "oversized":
            cpu_series = [round(random.uniform(7.0, 16.5), 2) for _ in range(14)]
        elif spec["pattern"] == "nonprod_schedule":
            cpu_series = [round(random.uniform(0.2, 1.4), 2) for _ in range(14)]
        else:
            cpu_series = [round(random.uniform(35.0, 68.0), 2) for _ in range(14)]

        net_base = 2_000_000.0 if spec["pattern"] in ("idle", "nonprod_schedule") else 50_000_000.0
        network_series = [round(max(0.0, net_base + random.gauss(0, net_base * 0.1)), 0) for _ in range(14)]

        cpu_p95 = sorted(cpu_series)[int(len(cpu_series) * 0.95)]
        avg_cpu = sum(cpu_series) / len(cpu_series)
        resource_dict["cpu_samples"] = cpu_series
        resource_dict["network_samples"] = network_series

        cpu_metrics.append(
            EC2CpuMetric(
                instance_id=inst_id,
                region=region,
                metric_name="CPUUtilization",
                unit="Percent",
                window_start=now - timedelta(days=14),
                window_end=now,
                datapoint_count=len(cpu_series),
                average_cpu_percent=round(avg_cpu, 2),
                maximum_cpu_percent=round(cpu_p95, 2),
                latest_datapoint_at=now
            )
        )

    # ---------------------------------------------------------------------------
    # 2. Generate 4 Unattached EBS Volumes
    # ---------------------------------------------------------------------------
    ebs_specs = [
        {"vol_id": "vol-0111222333", "size_gb": 500, "type": "gp3", "cost": 40.00, "name": "unused-backup-vol-01"},
        {"vol_id": "vol-0444555666", "size_gb": 1000, "type": "io2", "cost": 125.00, "name": "analytics-temp-disk"},
        {"vol_id": "vol-0777888999", "size_gb": 250, "type": "gp2", "cost": 25.00, "name": "dev-db-dump-old"},
        {"vol_id": "vol-0000111222", "size_gb": 100, "type": "gp3", "cost": 8.00, "name": "sandbox-stale-vol"},
    ]

    for vol in ebs_specs:
        resources.append({
            "schema_version": "1.0",
            "provider": "aws",
            "resource_type": "ebs_volume",
            "region": region,
            "availability_zone": f"{region}b",
            "resource_id": vol["vol_id"],
            "name": vol["name"],
            "environment": "staging",
            "instance_type": f"{vol['size_gb']}GB-{vol['type']}",
            "state": "available",
            "launched_at": (now - timedelta(days=60)).isoformat(),
            "collected_at": now.isoformat(),
            "monthly_cost_usd": vol["cost"],
            "tags": {
                "Name": vol["name"],
                "State": "available",
                "Environment": "staging"
            },
            "warnings": ["UNATTACHED_EBS_VOLUME"]
        })

    # ---------------------------------------------------------------------------
    # 3. Generate 30-Day Cost History (with 1 spend anomaly)
    # ---------------------------------------------------------------------------
    daily_costs: list[DailyCost] = []
    base_daily_cost = 320.00

    for i in range(30):
        day = today - timedelta(days=(29 - i))
        noise = random.uniform(-12.0, 15.0)
        amount = base_daily_cost + noise
        
        # Inject spend anomaly on today (day 29)
        if i == 29:
            amount += 650.00  # Large spike > 3x mean

        daily_costs.append(
            DailyCost(
                usage_date=day,
                amount=round(amount, 2),
                currency="USD",
                estimated=False,
                metric="UnblendedCost"
            )
        )

    return CloudSnapshot(
        account_id=account_id,
        region=region,
        collected_at=now,
        status="success",
        resource_count=len(resources),
        metric_count=len(cpu_metrics),
        cost_day_count=len(daily_costs),
        resources=resources,
        cpu_metrics=cpu_metrics,
        daily_costs=daily_costs,
        issues=[]
    )
