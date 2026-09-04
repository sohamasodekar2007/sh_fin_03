from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from services.decision.service import build_proposals, enrich_proposals_with_llm
from services.llm.client import LLMUnavailable


def _proposal(pid: str = "p1", action_type: str = "stop_instance") -> dict:
    return {
        "proposal_id": pid,
        "resource_arn": "arn:aws:ec2:ap-south-1:000000000000:instance/i-1",
        "action_type": action_type,
        "template_id": "ec2.stop.v1",
        "parameters": {"instance_id": "i-1", "region": "ap-south-1"},
        "expected_monthly_savings": "120.00",
        "risk_level": "low",
        "confidence": 0.9,
        "evidence": [],
        "rollback_plan": None,
        "requires_human_approval": False,
        "status": "proposed",
        "rationale": "template-generated rationale",
    }


# ---------------------------------------------------------------------------
# (a) LLMUnavailable degrades cleanly — proposals still come back, unchanged
# ---------------------------------------------------------------------------


def test_llm_unavailable_degrades_cleanly_and_still_returns_proposals():
    proposal = _proposal()
    mock_client = AsyncMock()
    mock_client.complete.side_effect = LLMUnavailable("OPENAI_API_KEY not set")

    proposals, llm_used = asyncio.run(
        enrich_proposals_with_llm([proposal], findings=[], focus_context=None, client=mock_client)
    )

    assert llm_used is False
    assert proposals == [proposal]
    assert proposals[0]["rationale"] == "template-generated rationale"


# ---------------------------------------------------------------------------
# (b) A hallucinated proposal_id (not in the input set) is dropped, not
# appended as a phantom proposal.
# ---------------------------------------------------------------------------


def test_hallucinated_proposal_id_is_dropped():
    proposal = _proposal(pid="p1")
    mock_client = AsyncMock()
    mock_client.complete.return_value = {
        "proposals": [
            {
                "proposal_id": "p1",
                "rationale_plain_english": "Stopping this idle server saves money with low risk.",
                "business_impact": "Reduces monthly cloud spend.",
                "risk_notes": "Low risk, development environment.",
                "priority_rank": 1,
            },
            {
                "proposal_id": "p-hallucinated-999",
                "rationale_plain_english": "This proposal was never given to the model.",
                "business_impact": "N/A",
                "risk_notes": "N/A",
                "priority_rank": 2,
            },
        ]
    }

    proposals, llm_used = asyncio.run(
        enrich_proposals_with_llm([proposal], findings=[], focus_context=None, client=mock_client)
    )

    assert llm_used is True
    assert len(proposals) == 1
    assert proposals[0]["proposal_id"] == "p1"
    assert proposals[0]["rationale_plain_english"] == "Stopping this idle server saves money with low risk."


# ---------------------------------------------------------------------------
# (c) action_type is never taken from the LLM response, even if the model
# tries to smuggle one in.
# ---------------------------------------------------------------------------


def test_action_type_is_never_taken_from_llm_response():
    proposal = _proposal(pid="p1", action_type="stop_instance")
    mock_client = AsyncMock()
    mock_client.complete.return_value = {
        "proposals": [
            {
                "proposal_id": "p1",
                "rationale_plain_english": "Stopping this idle server saves money with low risk.",
                "business_impact": "Reduces monthly cloud spend.",
                "risk_notes": "Low risk, development environment.",
                "priority_rank": 1,
                # Not a field on LLMProposalEnrichment — Pydantic drops it,
                # so it can never overwrite the deterministic action_type.
                "action_type": "delete_instance",
            }
        ]
    }

    proposals, llm_used = asyncio.run(
        enrich_proposals_with_llm([proposal], findings=[], focus_context=None, client=mock_client)
    )

    assert llm_used is True
    assert proposals[0]["action_type"] == "stop_instance"


def test_unattached_ebs_finding_builds_delete_volume_proposal():
    observation = {
        "account_id": "123456789012",
        "resources": [
            {
                "resource_id": "vol-123",
                "resource_type": "ebs_volume",
                "region": "ap-south-1",
                "environment": "dev",
                "monthly_cost_usd": 8.0,
                "tags": {"Owner": "finops"},
            }
        ],
    }
    findings = [
        {
            "rule_id": "ebs.unattached.v1",
            "resource_id": "vol-123",
            "confidence": 0.95,
            "evidence": {"unattached_hours": 48},
        }
    ]

    proposals = build_proposals(observation, findings)

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["action_type"] == "delete_volume"
    assert proposal["template_id"] == "ebs.delete.v1"
    assert proposal["resource_arn"] == "arn:aws:ec2:ap-south-1:123456789012:volume/vol-123"
    assert proposal["parameters"] == {"volume_id": "vol-123", "region": "ap-south-1"}
    assert proposal["rollback_plan"]["manual_action_required"] is True
