# CloudCare fintech add-ons (self-contained, lives inside `sh_fin_03`)

Three "category-defining" features scoped down from the
`Cloud-Cost-Optimization-Platform.md` brainstorm doc, built to actually
plug into the real `sh_fin_03` architecture (policy engine, executor,
notifications, governance tags) rather than requiring new infrastructure
(no OpenTelemetry, no Kafka, no traffic-replay sandbox — see each
package's docstring for what was deliberately scoped down and why).

This folder is a sibling to `services/`, `apps/`, `packages/` etc. inside
`sh_fin_03`, but nothing in the main app imports from it — **delete this
folder and nothing else in the repo changes.** See `MERGE_GUIDE.md` for
folding individual pieces into `services/`/`apps/` when you're ready.

## What's here

| Package | Concept it implements | What it does |
|---|---|---|
| `spend_velocity/` | SpendShield-lite | A spend-velocity circuit breaker — detects a cost spike from usage-metric samples (CUSUM-confirmed, not just a threshold), classifies severity, and decides a containment action through the same "production never auto-executes" policy discipline as the main repo. |
| `cost_attribution/` | DollarTrace-lite | Decomposes a cost delta across a dimension (merchant, region, tag) to rank which values explain the change — a cost flame-graph's ranking without needing distributed-trace instrumentation. |
| `unit_economics/` | MarginOS-lite | Cost-per-unit and gross-margin calculations per scope (merchant/customer/plan), flags negative-margin scopes. Backs a claim already made in `sh_fin_03/CDW_HACKATHON_PITCH.md` (#4, "Unit Economics & Margin Analytics") that no service in the main repo currently implements. |
| `api/` | — | A standalone FastAPI app (own port, default 8100) exposing all three, so the frontend snippets — or a live demo — can hit real endpoints without touching `sh_fin_03/apps/api`. |
| `demo/` | — | `run_demo.py` runs the full three-scene narrative (spike detected → attributed → margin impact) against synthetic data, printed to the console. No server needed. |
| `frontend_snippets/` | — | Three `.tsx` components matching `sh_fin_03/apps/web`'s existing Tailwind tokens and dependencies, ready to copy in. See `frontend_snippets/README.md`. |
| `tests/` | — | 27 pytest tests covering the actual math (velocity ratios, CUSUM calibration, cost decomposition, margin edge cases) — run before you trust any of this. |

## Design discipline carried over from the main repo

Every rationale string states its own limitations explicitly (no fake
precision), every "recommend" schema is honest about what it can't prove,
and production resources can never get an auto-executed containment
action — same rules `sh_fin_03/services/governance/tags.py` and
`services/policy/engine.py` already enforce. `spend_velocity/_tags_shim.py`
duplicates two of those tag-convention functions so this runs standalone;
see that file's docstring for the exact merge step.

## Running it

Uses the same Python dependencies as `sh_fin_03` (pydantic v2, FastAPI) —
reuse the repo's existing `.venv` one level up rather than creating a new one.

```bash
# From this folder (sh_fin_03/cloudcare-fintech-addons/):
../.venv/Scripts/python.exe -m pytest -q          # run the 27 tests
../.venv/Scripts/python.exe -m demo.run_demo       # console narrative demo
../.venv/Scripts/python.exe -m uvicorn api.main:app --reload --port 8100  # live API
```

Or set up your own venv from `requirements.txt` if you'd rather keep this
fully isolated from `sh_fin_03`'s environment.

Frontend snippets are copy-in only (see `frontend_snippets/README.md`) —
this folder has no `node_modules`/Next.js project of its own.

## If you want to delete this

Delete the folder. Nothing in `sh_fin_03` references it — it was never
imported from there, and the one deliberate duplication
(`_tags_shim.py`) exists so that's true.

## If you want to merge this

See `MERGE_GUIDE.md` for the exact file-by-file destination mapping and
the handful of things to change on the way in (mainly: swap
`_tags_shim.py` for the real `services.governance.tags` import, and
point the frontend snippets' fetch calls at the real backend once routers
are folded in there instead of the standalone `api/` app).
