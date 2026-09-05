""""AWS Trusted Services" — genuinely undefined in the main repo before
this: grepping the whole codebase for "trusted"/"Trusted Advisor" turns up
exactly one hit, packages/schemas/cloud_resource.py's
DependencyContext.trusted_advisor_note, a dead placeholder field that's
never read or set anywhere (AWS Trusted Advisor access returned
AccessDeniedException when tested live, per that field's own comment).
There is no pillar-scoring system or approved-services concept anywhere
else in the repo.

This package is therefore a deliberate interpretation, not an extension
of something that already existed, built as two pieces:

1. `allowlist.py` — an approved-AWS-services checker. Every company has a
   different list of services it actually sanctions; this flags usage
   outside that list as a governance deviation ("shadow IT"), not a
   security verdict by itself.
2. `scorecard.py` — a simple, auditable pillar scorecard (Cost
   Optimization / Security / Fault Tolerance / Service Limits) built from
   plain finding counts — e.g. security_policy_addons' output feeds the
   "security" pillar. Deliberately not a black-box ML risk score: the
   math is `100 - findings*8 - critical*12`, visible in scorecard.py.
"""

from .allowlist import check_approved_services
from .schemas import PillarScore, ServiceUsageSample, TrustedServicesReport, TrustScorecard, UnapprovedServiceFinding
from .scorecard import build_scorecard

__all__ = [
    "check_approved_services",
    "build_scorecard",
    "ServiceUsageSample",
    "UnapprovedServiceFinding",
    "TrustedServicesReport",
    "PillarScore",
    "TrustScorecard",
]
