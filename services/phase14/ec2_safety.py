"""
EC2 stop-candidate safety checks. Originally (Phase 14) the ASG-membership/
load-balancer-target/termination-protection checks below were the one thing
that filtered stop_instance proposals AFTER the fact, live, on every
Decision Agent trigger. Phase 15 superseded that specific use: those same
facts are now collected once, at collection time, into each EC2 resource's
dependency_context (services/collector/ec2_collector.py), and consumed
deterministically inside services/decision/service.py::build_proposals() —
an ASG-managed or termination-protected instance never gets a stop_instance
proposal built in the first place, instead of being filtered out here after
the fact. is_asg_managed / is_load_balancer_target / has_termination_protection
/ evaluate_stop_candidate below are kept (still correct, still tested) as a
reusable live-check utility, but apps/api/routers/decision.py's real hook no
longer calls them — it only calls attached_ebs_monthly_cost and
attached_elastic_ip_note now, for evidence enrichment unrelated to the
ASG/LB/termination decision. Everything here is read-only (Describe* calls
only) and every function treats "can't confirm" as "not safe" — the
conservative direction, since a false "safe" could get something
autonomy-relevant stopped, while a false "unsafe" only costs a missed
recommendation.

Pure/isolated by design: nothing outside apps/api/routers/decision.py
imports this module, and that one call site is wrapped so a missing
import (this whole services/phase14/ package deleted) or the
ec2_safety_checks_enabled flag being off falls back to today's behavior
exactly, not a crash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StopSafetyResult:
    safe: bool
    exclusion_reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def is_asg_managed(autoscaling_client: Any, instance_id: str) -> bool:
    """True (or "can't tell, so assume yes") means: never a stop candidate.
    describe_auto_scaling_instances is an autoscaling: call, not ec2: —
    callers must pass a client built via factory.client("autoscaling", ...),
    never the ec2 client used by the other checks in this module."""
    try:
        response = autoscaling_client.describe_auto_scaling_instances(InstanceIds=[instance_id])
        return len(response.get("AutoScalingInstances", [])) > 0
    except ClientError as error:
        logger.info("phase14.ec2_safety: ASG check failed for %s, assuming managed: %s", instance_id, error)
        return True


def is_load_balancer_target(elbv2_client: Any, instance_id: str) -> bool:
    """Iterates every target group's health, looking for this instance —
    there is no "describe all targets across all groups" single call in
    the ELBv2 API, so this necessarily costs one call per target group."""
    try:
        groups = elbv2_client.describe_target_groups().get("TargetGroups", [])
    except ClientError as error:
        logger.info("phase14.ec2_safety: could not list target groups, assuming targeted: %s", error)
        return True

    for group in groups:
        try:
            health = elbv2_client.describe_target_health(TargetGroupArn=group["TargetGroupArn"])
            for desc in health.get("TargetHealthDescriptions", []):
                if desc.get("Target", {}).get("Id") == instance_id:
                    return True
        except ClientError as error:
            logger.info("phase14.ec2_safety: target-health check failed for group %s: %s", group.get("TargetGroupArn"), error)
            return True
    return False


def has_termination_protection(ec2_client: Any, instance_id: str) -> bool:
    try:
        response = ec2_client.describe_instance_attribute(InstanceId=instance_id, Attribute="disableApiTermination")
        return bool(response.get("DisableApiTermination", {}).get("Value", False))
    except ClientError as error:
        logger.info("phase14.ec2_safety: termination-protection check failed for %s, assuming protected: %s", instance_id, error)
        return True


def attached_ebs_monthly_cost(ec2_client: Any, instance_id: str, cost_by_resource: dict[str, float]) -> float | None:
    """Real FOCUS-joined cost when available (cost_by_resource is the same
    resource_id -> BilledCost map apps/api/routers/observation.py's
    _cost_by_resource_id() already builds — passed in, not re-fetched, so
    this stays a single source of truth for "real cost," never a second,
    possibly-divergent one). None (never 0.0) when no volume is attached
    or no cost data exists for it yet."""
    try:
        response = ec2_client.describe_volumes(
            Filters=[{"Name": "attachment.instance-id", "Values": [instance_id]}]
        )
    except ClientError as error:
        logger.info("phase14.ec2_safety: EBS lookup failed for %s: %s", instance_id, error)
        return None

    volume_ids = [v["VolumeId"] for v in response.get("Volumes", [])]
    if not volume_ids:
        return None

    total = sum(cost_by_resource.get(vid) or 0.0 for vid in volume_ids if vid in cost_by_resource)
    return total if any(vid in cost_by_resource for vid in volume_ids) else None


def attached_elastic_ip_note(ec2_client: Any, instance_id: str) -> str | None:
    """A stopped instance keeps its Elastic IP association only if the EIP
    stays allocated — AWS bills an idle allocated EIP hourly once it's no
    longer associated with a *running* instance. Returns a plain-English
    note to append to the proposal's rationale, or None if no EIP is
    attached."""
    try:
        response = ec2_client.describe_addresses(Filters=[{"Name": "instance-id", "Values": [instance_id]}])
    except ClientError as error:
        logger.info("phase14.ec2_safety: EIP lookup failed for %s: %s", instance_id, error)
        return None

    addresses = response.get("Addresses", [])
    if not addresses:
        return None
    ip = addresses[0].get("PublicIp", "the attached Elastic IP")
    return (
        f"This instance has an Elastic IP ({ip}) attached — once stopped, an idle "
        "allocated Elastic IP is billed hourly on its own, a separate charge that "
        "does not disappear when the instance stops."
    )


def evaluate_stop_candidate(
    ec2_client: Any,
    elbv2_client: Any,
    autoscaling_client: Any,
    instance_id: str,
    cost_by_resource: dict[str, float],
) -> StopSafetyResult:
    """The one orchestrating entry point apps/api/routers/decision.py calls.
    Excludes the instance entirely (safe=False) for ASG membership, load-
    balancer membership, or termination protection; otherwise returns
    safe=True with EBS-cost-split and EIP evidence to merge into the
    proposal's rationale — real signals, never fabricated when a describe
    call fails (see each function's own docstring for its fail-safe
    direction)."""
    if is_asg_managed(autoscaling_client, instance_id):
        return StopSafetyResult(
            safe=False,
            exclusion_reason="Managed by an Auto Scaling Group — stopping would trigger automatic replacement.",
        )
    if is_load_balancer_target(elbv2_client, instance_id):
        return StopSafetyResult(
            safe=False,
            exclusion_reason="Registered as a load balancer target — stopping would affect live traffic routing.",
        )
    if has_termination_protection(ec2_client, instance_id):
        return StopSafetyResult(
            safe=False,
            exclusion_reason="Termination protection is enabled — treated as a protected resource, recommend-only.",
        )

    ebs_cost = attached_ebs_monthly_cost(ec2_client, instance_id, cost_by_resource)
    eip_note = attached_elastic_ip_note(ec2_client, instance_id)

    evidence: dict[str, Any] = {}
    if ebs_cost is not None:
        evidence["attached_ebs_monthly_cost_usd"] = ebs_cost
    if eip_note:
        evidence["elastic_ip_note"] = eip_note

    return StopSafetyResult(safe=True, evidence=evidence)
