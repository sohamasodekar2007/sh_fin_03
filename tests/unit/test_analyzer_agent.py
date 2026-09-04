"""
Unit test for merged Analyzer Agent (Detect) - rule engine and observation processing.
"""

from services.collector.mock_provider import generate_mock_observation_bundle
from services.analyzer.service import analyze_observation


def test_analyzer_agent_rule_execution():
    """Verify Analyzer Agent detects findings from Monitor Agent observation bundle."""
    snapshot = generate_mock_observation_bundle(account_id="123456789012", region="us-east-1")
    observation_dict = snapshot.model_dump(mode="json")

    findings = analyze_observation(observation_dict)

    assert isinstance(findings, list)
    assert len(findings) > 0

    rule_ids = [f["rule_id"] for f in findings]

    # Verify key rules triggered
    assert "ec2.idle.v1" in rule_ids
    assert "ec2.overprovisioned.v1" in rule_ids
    assert "ebs.unattached.v1" in rule_ids
    assert "cost.anomaly.v1" in rule_ids

    # Verify structure of finding
    first_finding = findings[0]
    assert "resource_id" in first_finding
    assert "rule_id" in first_finding
    assert "severity" in first_finding
    assert "confidence" in first_finding
    assert "evidence" in first_finding
