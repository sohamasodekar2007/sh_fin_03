"""
End-to-end smoke test for the full 6-node LangGraph pipeline — Monitor
through Verifier — against the built-in demo fleet (no CloudAccounts or
API keys required; every adapter degrades to its synthetic dataset).

Run with:  python -m scripts.test_graph
"""

import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from services.orchestrator.graph import build_graph, make_initial_state

initial_state = make_initial_state(run_id="test-run-001", tenant_id="demo-tenant", account_id="multi-cloud")

graph = build_graph()
result = graph.invoke(initial_state)

print()
print("=== RESULTS ===")

observation = result.get("observation", {})
findings = result.get("findings", [])
proposals = result.get("proposals", [])
approvals = result.get("approvals", [])
execution_log = result.get("execution_log", [])
feedback = result.get("feedback", [])
trace = result.get("trace", [])

print("Status          :", result.get("status", "?"))
print("Providers       :", observation.get("providers", {}))
print("Resources       :", observation.get("resources_scanned", "?"))
print("Findings        :", len(findings))
print("Proposals       :", len(proposals))
print("Policy decisions:", len(approvals))
print("Executions      :", len(execution_log))
print("Verified        :", len(feedback))
print()
for f in findings:
    print(f"  [{f['rule_id']}]  resource={f['resource_id']}  severity={f['severity']}  confidence={f['confidence']:.2f}")
print()
for a in approvals:
    print(f"  policy: {a['outcome']:14} risk_score={a['risk_score']:.2f}  {a['reason']}")
print()
print("Trace entries:", len(trace))
for t in trace:
    print(f"  {t['agent']:10} -> {t['summary']}")

assert observation.get("resources_scanned", 0) > 0, "monitor must scan at least one resource"
assert len(trace) == 6 or len(trace) == 5, "expected one trace entry per executed node (5 if the run short-circuits with nothing to execute)"
print()
print("All assertions passed.")
