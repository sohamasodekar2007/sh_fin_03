# Merge guide

Exact file-by-file mapping into `sh_fin_03`, plus the handful of changes
each move needs. Nothing here is required to run the standalone version —
only do this when you've decided to fold a feature into the real app.

## 1. `spend_velocity/` → `sh_fin_03/services/spend_velocity/`

1. Copy the whole folder to `sh_fin_03/services/spend_velocity/`.
2. **Delete `_tags_shim.py`.** In `policy.py`, change:
   ```python
   from ._tags_shim import exceeds_max_risk, is_excluded
   ```
   to:
   ```python
   from services.governance.tags import exceeds_max_risk, is_excluded
   ```
3. In `notify.py`, replace `LoggingNotificationSink` usage with a sink
   that calls into `services/notifications` (e.g. wrap
   `services/notifications/email.py`'s send function in a class
   implementing the `NotificationSink` protocol — the protocol only
   needs one method, `send(alert) -> None`).
4. Decide where `SpendVelocityGuard.evaluate()` gets called from. Two
   reasonable options:
   - A new lightweight polling loop (cron/scheduled task) that pulls
     recent CloudWatch usage metrics into `SpendSample`s and calls the
     guard every few minutes.
   - A node in `services/orchestrator/graph.py`'s LangGraph pipeline,
     alongside the existing Analyzer step, if you want it running inside
     the same pipeline tick rather than a separate poller.
5. When `VelocityAlert.recommended_action` is `escalate_supervisor` or
   `block_auto_execute`, route it through the same approval surface
   `services/executor` already uses for ActionProposals — but note
   `VelocityAlert` is deliberately a different shape (same discipline as
   `services/phase14/schemas.py`'s docstring: don't let this quietly
   enter the real executable-proposal pipeline as if it were an
   ActionProposal; give it its own review lane, or explicitly convert it
   at the boundary).
6. Add `tests/test_spend_velocity.py` to `sh_fin_03/tests/unit/` (or
   wherever unit tests matching this structure live), updating the
   import from `spend_velocity...` — it already matches, no change
   needed if `services/` is on `sh_fin_03`'s `pythonpath` (it is, per
   `pyproject.toml`).

## 2. `cost_attribution/` → `sh_fin_03/services/cost_attribution/`

1. Copy the whole folder over — it has no shimmed dependencies, no
   changes needed to the package itself.
2. Wire a real `CostSample` feed: Cost Explorer's `GetCostAndUsage` with
   `GroupBy` on the dimension you want (tag, service, region) maps
   directly onto `CostSample.dimension_key` / `dimension_value`.
3. Expose it wherever the chat service's tool-calling lives
   (`services/chat/tools.py`) — "why did X cost more this week" is a
   natural fit for a new tool that calls `decompose()` and returns the
   `CostBreakdown.rationale` plus top contributors.
4. Copy `tests/test_cost_attribution.py` alongside it.

## 3. `unit_economics/` → `sh_fin_03/services/unit_economics/` (or fold into `services/focus/`)

1. Copy the folder over. **Delete `seed_data.py` before this goes near
   anything real** — it's demo-only synthetic data, and its own
   docstring says so. Replace calls to it with a real query for
   revenue/transaction-volume per scope; `services/focus/` (the
   FOCUS-standard cost aggregation service) is the natural place to add
   that query since it already aggregates cost per scope.
2. Copy `tests/test_unit_economics.py`, but drop or rewrite
   `test_seed_data_produces_at_least_one_negative_margin_scope` once
   `seed_data.py` is gone.
3. This is the piece that backs `CDW_HACKATHON_PITCH.md`'s feature #4
   claim — once merged, that pitch doc stops overstating what the repo
   does.

## 4. `api/` (standalone FastAPI app)

This one **shouldn't be copied wholesale** — its job was to let the
frontend snippets and the demo work without touching the real backend.
Once the three service packages above are merged:

1. Create routers in `sh_fin_03/apps/api/routers/` (or `backend/app/routers/`,
   whichever is the live one — check which of `apps/api` vs `backend`
   is still active before choosing) mirroring `api/routers/*.py` here,
   but importing from `services.spend_velocity` / `services.cost_attribution`
   / `services.unit_economics` instead of the top-level package names.
2. Register those routers in the real app's `main.py` the same way
   `api/main.py` here does with `app.include_router(...)`.
3. Delete this addon's `api/` folder (or leave it as a local dev/demo
   server — it's harmless either way since it imports nothing from
   `sh_fin_03`).

## 5. `frontend_snippets/`

See `frontend_snippets/README.md` — copy the three `.tsx` files into
`sh_fin_03/apps/web/components/dashboard/`, add them to
`apps/web/app/dashboard/page.tsx`, and once step 4 above is done, point
`NEXT_PUBLIC_ADDON_API_URL` at the real backend's base URL (or just
change each snippet's fetch path to a relative `/api/...` route if it's
served from the same origin).

## 6. `demo/`

Demo-only — no merge target. Keep it here for regression-checking the
three packages together, or delete it once real integration tests exist
in `sh_fin_03/tests/integration/`.

## Order of operations, if doing this incrementally

`spend_velocity` first (highest pitch impact, plugs into
policy/executor/notifications you already have) → `cost_attribution`
(no dependencies, safe to merge any time) → `unit_economics` (needs a
real revenue data source decision before `seed_data.py` can be deleted,
so this one has an external blocker the other two don't).
