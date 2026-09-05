from __future__ import annotations

from .schemas import ServiceUsageSample, TrustedServicesReport, UnapprovedServiceFinding


def check_approved_services(
    usage: list[ServiceUsageSample], approved_services: list[str]
) -> TrustedServicesReport:
    """Case-insensitive match against a caller-supplied allowlist — there
    is no universal "trusted AWS services" list; every org configures its
    own. A service not on the list is a policy deviation worth reviewing,
    not an automatic verdict that it's insecure."""
    approved_lower = {s.lower() for s in approved_services}
    unapproved: list[UnapprovedServiceFinding] = []
    unapproved_cost = 0.0
    total_cost = 0.0

    for sample in usage:
        total_cost += sample.monthly_cost
        if sample.service.lower() in approved_lower:
            continue
        unapproved_cost += sample.monthly_cost
        unapproved.append(
            UnapprovedServiceFinding(
                service=sample.service,
                resource_count=sample.resource_count,
                monthly_cost=round(sample.monthly_cost, 2),
                rationale=(
                    f"'{sample.service}' is not on this org's {len(approved_services)}-service allowlist — "
                    f"{sample.resource_count} resource(s), ₹{sample.monthly_cost:,.2f}/mo. Flags a policy "
                    "deviation to review, not a security vulnerability by itself."
                ),
            )
        )

    unapproved.sort(key=lambda f: f.monthly_cost, reverse=True)
    unapproved_pct = round((unapproved_cost / total_cost * 100) if total_cost > 1e-9 else 0.0, 2)
    rationale = (
        f"{len(unapproved)} of {len(usage)} service(s) in use are not on this org's {len(approved_services)}-"
        f"service allowlist, representing {unapproved_pct:.1f}% of tracked spend. Allowlists are configurable "
        "per company — there is no universal 'trusted' list this check enforces."
    )

    return TrustedServicesReport(
        approved_services=list(approved_services),
        unapproved=unapproved,
        unapproved_cost=round(unapproved_cost, 2),
        unapproved_pct=unapproved_pct,
        total_cost=round(total_cost, 2),
        rationale=rationale,
    )
