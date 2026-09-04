"""Quick smoke test for the wired monitor + analyze nodes."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from services.orchestrator.graph import build_graph, make_initial_state

initial_state = make_initial_state(
    run_id="test-run-001",
    tenant_id="demo-tenant",
    account_id="ap-south-1",
)

graph = build_graph()
result = graph.invoke(initial_state)

print()
print("=== RESULTS ===")

# LangGraph with a plain dict schema returns merged state across all nodes.
# Access keys defensively since partial-state merging depends on langgraph version.
obs = result.get("observation", {})
findings = result.get("findings", [])
trace = result.get("trace", [])

print("Status       :", result.get("status", "?"))
print("Source       :", obs.get("source", "?"))
print("Resources    :", obs.get("resources_scanned", "?"))
print("Findings     :", len(findings))
print()
for f in findings:
    print(
        f"  [{f['rule_id']}]  resource={f['resource_id']}"
        f"  severity={f['severity']}  confidence={f['confidence']}"
    )
print()
print("Trace entries:", len(trace))
for t in trace:
    print(f"  {t['agent']:12} -> {t['summary']}")

assert obs.get("source") in ("aws", "mock"), "source must be set"
assert len(findings) > 0, "expected at least one finding from mock data"
assert len(trace) >= 2, "expected trace entries from monitor + analyze at minimum"
print()
print("All assertions passed.")
