"""
Phase 14 — Multi-Service Awareness. Entirely additive: deleting this
package, apps/api/routers/phase14.py, the one include_router line in
apps/api/main.py, and the one guarded hook in apps/api/routers/decision.py
fully reverts the app to its pre-Phase-14 behavior. Nothing outside this
package imports from it except those two exact spots, both wrapped so a
missing import degrades to prior behavior rather than crashing.
"""
