"""CloudCare FastAPI entrypoint — a trusting resource server (spec section 2)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import get_settings
from apps.api.db import ping
from apps.api.routers import accounts_runs, agent_activity, chat, forecasts_savings, observation, recommendations, resources
from apps.api.ws import agent_feed

settings = get_settings()

app = FastAPI(title="CloudCare API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (resources.router, agent_activity.router, forecasts_savings.router, observation.router, accounts_runs.router, recommendations.router, chat.router):
    app.include_router(router)

app.include_router(agent_feed.router)


@app.get("/health")
async def health():
    return {"status": "ok", "mongodb_connected": await ping(), "app_env": settings.app_env}


@app.get("/")
async def root():
    return {"name": "CloudCare API", "docs": "/docs"}
