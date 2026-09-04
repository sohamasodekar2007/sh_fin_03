from __future__ import annotations

from services.governance.tags import (
    RISK_ORDER,
    exceeds_max_risk,
    get_max_risk_ceiling,
    has_missing_ownership,
    is_excluded,
)


def test_is_excluded_true():
    assert is_excluded({"cloudcare:exclude": "true"}) is True
    assert is_excluded({"cloudcare:exclude": "True"}) is True


def test_is_excluded_false_when_absent_or_other_value():
    assert is_excluded({}) is False
    assert is_excluded({"cloudcare:exclude": "false"}) is False
    assert is_excluded({"cloudcare:exclude": "yes"}) is False


def test_get_max_risk_ceiling_valid_values():
    assert get_max_risk_ceiling({"cloudcare:max-risk": "low"}) == "low"
    assert get_max_risk_ceiling({"cloudcare:max-risk": "MEDIUM"}) == "medium"
    assert get_max_risk_ceiling({"cloudcare:max-risk": "high"}) == "high"


def test_get_max_risk_ceiling_none_when_absent_or_invalid():
    assert get_max_risk_ceiling({}) is None
    assert get_max_risk_ceiling({"cloudcare:max-risk": "critical"}) is None
    assert get_max_risk_ceiling({"cloudcare:max-risk": "not-a-risk"}) is None


def test_exceeds_max_risk_true_when_real_risk_above_ceiling():
    assert exceeds_max_risk("high", {"cloudcare:max-risk": "low"}) is True
    assert exceeds_max_risk("critical", {"cloudcare:max-risk": "medium"}) is True


def test_exceeds_max_risk_false_when_at_or_below_ceiling():
    assert exceeds_max_risk("low", {"cloudcare:max-risk": "low"}) is False
    assert exceeds_max_risk("medium", {"cloudcare:max-risk": "high"}) is False


def test_exceeds_max_risk_false_when_no_ceiling_set():
    assert exceeds_max_risk("critical", {}) is False


def test_exceeds_max_risk_never_mutates_risk_level_itself():
    # Approval-floor semantics (per the resolved spec ambiguity): the
    # function only ever returns a bool, never a modified risk_level.
    tags = {"cloudcare:max-risk": "low"}
    result = exceeds_max_risk("critical", tags)
    assert result is True
    assert tags == {"cloudcare:max-risk": "low"}  # untouched


def test_has_missing_ownership_true_when_neither_tag_present():
    assert has_missing_ownership({}) is True
    assert has_missing_ownership({"Name": "web-1"}) is True


def test_has_missing_ownership_false_when_owner_present():
    assert has_missing_ownership({"Owner": "alice"}) is False
    assert has_missing_ownership({"owner": "alice"}) is False


def test_has_missing_ownership_false_when_environment_present():
    assert has_missing_ownership({"Environment": "prod"}) is False


def test_risk_order_is_monotonic():
    assert RISK_ORDER["low"] < RISK_ORDER["medium"] < RISK_ORDER["high"] < RISK_ORDER["critical"]
