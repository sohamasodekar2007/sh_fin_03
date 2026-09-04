"""
LangGraph orchestration — lifted directly from blueprint section 9.1.

State merging: LangGraph 1.x requires a TypedDict (or dataclass) with
Annotated reducers for list fields that are appended across nodes.  We use
operator.add as the reducer for trace/findings/proposals/approvals/
execution_log/feedback so every node's returned list is *appended* to the
accumulated state rather than replacing it.

Node functions (nodes.py) only return the keys they change — LangGraph
merges the partial update into the full state automatically.

To run end-to-end:
    from services.orchestrator.graph import build_graph, make_initial_state
    result = build_graph().invoke(make_initial_state(run_id="x", tenant_id="y", account_id="z"))
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from langgraph.graph import END, StateGraph

from services.orchestrator.nodes import analyze, decide, execute, monitor, supervise, verify


# ---------------------------------------------------------------------------
# State schema — TypedDict with list reducers
# ---------------------------------------------------------------------------

from typing import TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    tenant_id: str
    account_id: str
    observation: dict
    # List fields use operator.add so partial updates are appended, not replaced.
    findings: Annotated[list, operator.add]
    proposals: Annotated[list, operator.add]
    approvals: Annotated[list, operator.add]
    execution_log: Annotated[list, operator.add]
    feedback: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]
    status: str
    reanalysis_count: int
    supervisor_decision: str


def make_initial_state(run_id: str, tenant_id: str, account_id: str) -> dict:
    """Convenience factory for a clean initial state dict."""
    return {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "account_id": account_id,
        "observation": {},
        "findings": [],
        "proposals": [],
        "approvals": [],
        "execution_log": [],
        "feedback": [],
        "trace": [],
        "status": "observing",
        "reanalysis_count": 0,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_supervisor(state: dict) -> str:
    decision = state.get("supervisor_decision")
    if decision == "execute":
        return "execute"
    if decision == "reanalyze" and state.get("reanalysis_count", 0) < 3:
        return "analyze"
    if decision == "human_review":
        return END
    return END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph():
    g = StateGraph(GraphState)

    for name, fn in [
        ("monitor", monitor),
        ("analyze", analyze),
        ("decide", decide),
        ("supervise", supervise),
        ("execute", execute),
        ("verify", verify),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("monitor")
    g.add_edge("monitor", "analyze")
    g.add_edge("analyze", "decide")
    g.add_edge("decide", "supervise")
    g.add_conditional_edges("supervise", route_after_supervisor)
    g.add_edge("execute", "verify")
    g.add_edge("verify", END)

    return g.compile()
