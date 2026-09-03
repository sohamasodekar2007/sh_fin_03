"""
Decision Agent — LLM reasoning layer (spec section 4.3).

Takes the Analyzer's purely mathematical findings and asks an OpenAI model
to *reason* about them, constrained via Structured Outputs / tool calling
to a rigid ActionProposal JSON array — never free text. This is the only
place in the pipeline that calls an LLM to decide anything.

Safety boundary (unchanged from the original blueprint, and still enforced
one layer up in services/policy/engine.py): the LLM's output is advisory,
not authoritative. services/decision/service.py::decide() cross-checks the
LLM's estimated_monthly_savings against the deterministic template-based
estimate and clips outliers, and the Supervisor Agent's policy engine is
the only thing that can set requires_human_approval — an LLM can never
downgrade risk to skip that check.

Falls back to `None` (caller then uses the deterministic proposals as-is)
whenever OPENAI_API_KEY isn't set or the call fails, so the pipeline never
crashes waiting on a live LLM.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.api.config import get_settings

logger = logging.getLogger(__name__)

_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "propose_actions",
        "description": "Propose cost-optimization actions for the flagged cloud resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_resource_id": {"type": "string"},
                            "action_type": {
                                "type": "string",
                                "enum": ["stop_instance", "schedule_instance", "resize_instance"],
                            },
                            "estimated_monthly_savings": {"type": "number"},
                            "rationale": {
                                "type": "string",
                                "description": "One or two sentences a FinOps reviewer can act on — cite the evidence.",
                            },
                        },
                        "required": ["target_resource_id", "action_type", "estimated_monthly_savings", "rationale"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["proposals"],
            "additionalProperties": False,
        },
    },
}


def generate_action_proposals(findings: list[dict[str, Any]], resource_context: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    settings = get_settings()
    if not settings.openai_api_key:
        logger.info("decision.llm: OPENAI_API_KEY not set — skipping LLM reasoning, deterministic proposals only.")
        return None
    if not findings:
        return []

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Decision Agent in a cloud FinOps pipeline. You will be given "
                        "deterministic findings (from statistical rules and an IsolationForest model) "
                        "about idle, over-provisioned, or anomalous cloud resources, plus each "
                        "resource's cost/environment context. Call propose_actions with one proposal "
                        "per finding you think is worth acting on. Never invent a resource id that "
                        "isn't in the input."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"findings": findings, "resources": resource_context}, default=str),
                },
            ],
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "function", "function": {"name": "propose_actions"}},
            temperature=0.2,
        )
        tool_call = response.choices[0].message.tool_calls[0]
        parsed = json.loads(tool_call.function.arguments)
        proposals = parsed.get("proposals", [])
        logger.info("decision.llm: model returned %d proposal(s) for %d finding(s)", len(proposals), len(findings))
        return proposals

    except Exception as exc:  # noqa: BLE001
        logger.warning("decision.llm: OpenAI call failed (%s) — falling back to deterministic proposals.", exc)
        return None
