"""DUPLICATE — on merge, delete this file entirely and change
policy.py's import to `from services.governance.tags import (...)`.

These four functions are copied verbatim from
sh_fin_03/services/governance/tags.py so this addon package has no
import dependency on the main repo and can run/test standalone. They
must stay byte-for-byte behaviorally identical to the source; if you've
edited governance/tags.py since generating this addon, re-copy it rather
than trusting this file.
"""

from __future__ import annotations

from typing import Literal

RiskLevel = Literal["low", "medium", "high", "critical"]

RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_VALID_MAX_RISK_VALUES = {"low", "medium", "high"}


def is_excluded(tags: dict[str, str]) -> bool:
    return str((tags or {}).get("cloudcare:exclude", "")).lower() == "true"


def get_max_risk_ceiling(tags: dict[str, str]) -> RiskLevel | None:
    raw = str((tags or {}).get("cloudcare:max-risk", "")).strip().lower()
    if raw in _VALID_MAX_RISK_VALUES:
        return raw  # type: ignore[return-value]
    return None


def exceeds_max_risk(risk_level: str, tags: dict[str, str]) -> bool:
    ceiling = get_max_risk_ceiling(tags)
    if ceiling is None:
        return False
    return RISK_ORDER.get(str(risk_level).lower(), 0) > RISK_ORDER[ceiling]
