"""Standalone demo API for the three fintech add-on features. Deliberately
its own FastAPI app on its own port (default 8100) rather than mounted
into sh_fin_03/apps/api — run side-by-side with the real backend with zero
risk of colliding routes or import paths. See ../MERGE_GUIDE.md for how to
fold these routers into the real backend later.

Run with:
    uvicorn api.main:app --reload --port 8100
(from the cloudcare-fintech-addons folder)

CORS is wide open here — this is a local demo server, not a deployment.
Tighten allow_origins before this ever goes anywhere real.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import aws_trusted_services as aws_trusted_services_router
from api.routers import cost_attribution as cost_attribution_router
from api.routers import forecast_anomaly as forecast_anomaly_router
from api.routers import security_policy_addons as security_policy_addons_router
from api.routers import spend_velocity as spend_velocity_router
from api.routers import team_attribution as team_attribution_router
from api.routers import unit_economics as unit_economics_router

app = FastAPI(
    title="CloudCare Fintech Add-ons (standalone demo)",
    description=(
        "SpendShield-lite / DollarTrace-lite / MarginOS-lite / Forecast Anomaly Guard / "
        "Team Attribution / Security Policy Add-ons / AWS Trusted Services — not part of "
        "the main sh_fin_03 backend."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(spend_velocity_router.router)
app.include_router(cost_attribution_router.router)
app.include_router(unit_economics_router.router)
app.include_router(forecast_anomaly_router.router)
app.include_router(team_attribution_router.router)
app.include_router(security_policy_addons_router.router)
app.include_router(aws_trusted_services_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "cloudcare-fintech-addons"}
