import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.routers import (
    accounts_runs,
    agent_activity,
    agent_command,
    analysis,
    auth,
    chat,
    decision,
    execution,
    external_factors,
    focus_summary,
    forecasts_savings,
    governance,
    observation,
    parquet_analysis,
    phase14,
    pipeline,
    recommendations,
    resources,
    supervisor,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from services import agent_log, scheduler
    from services.focus import repository as focus_repository
    from services.chat.service import ensure_chat_indexes
    from services.executor.actions import ensure_execution_lock_index
    from services.executor.execution_audit import ensure_live_audit_indexes
    from services.supervisor.approval_tokens import ensure_approval_indexes
    from services.supervisor.service import ensure_supervisor_indexes

    db = get_db()
    try:
        await agent_log.ensure_indexes(db)
        await focus_repository.ensure_indexes(db)
        await scheduler.ensure_lock_index(db)
        await ensure_supervisor_indexes(db)
        await ensure_approval_indexes(db)
        await ensure_execution_lock_index(db)
        await ensure_live_audit_indexes(db)
        await ensure_chat_indexes(db)
        await auth.ensure_auth_indexes(db)
        await agent_command.ensure_agent_command_indexes(db)
    except Exception as exc:  # noqa: BLE001 - index setup must never block startup
        logger.warning("lifespan: index setup warning: %s", exc)

    scheduler.start_scheduler()
    try:
        yield
    finally:
        scheduler.shutdown_scheduler()

settings = get_settings()

app = FastAPI(
    title="CloudCare API",
    description="AI-Powered Cloud Cost Optimization & Resource Intelligence Platform backend API.",
    version="0.1.0",
    lifespan=lifespan,
)

class CorsSafeErrorMiddleware(BaseHTTPMiddleware):
    """
    Without this, an unhandled exception (e.g. a MongoDB connection that
    times out — the actual, very common case here when MONGODB_URI isn't
    configured) is caught by Starlette's ServerErrorMiddleware, which sits
    OUTSIDE CORSMiddleware in the default stack — even a handler registered
    via @app.exception_handler(Exception) is special-cased to run there,
    not in ExceptionMiddleware, because Starlette treats a bare Exception
    handler as the ServerErrorMiddleware's own handler. Either way, that
    500 response never passes back through CORSMiddleware, so it carries
    no Access-Control-Allow-Origin header — and the browser reports the
    whole thing to the frontend as an opaque "Failed to fetch" / network
    error, hiding the real 500 and its message entirely.

    This middleware is added OUTSIDE CORSMiddleware (added to the app
    after it — Starlette wraps user middleware in reverse add order, so
    the last one added ends up outermost) and adds the CORS headers onto
    the error response itself, so apps/frontend/src/lib/api.ts sees a real
    500 with a real body instead of a bare network failure.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
            headers: dict[str, str] = {}
            origin = request.headers.get("origin")
            if origin and origin in settings.cors_origin_list:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
                headers["Vary"] = "Origin"
            return JSONResponse(status_code=500, content={"detail": "Internal server error"}, headers=headers)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorsSafeErrorMiddleware)


app.include_router(auth.router)
app.include_router(observation.router)
app.include_router(parquet_analysis.router)
app.include_router(analysis.router)
app.include_router(decision.router)
app.include_router(resources.router)
app.include_router(agent_activity.router)
app.include_router(agent_command.router)
app.include_router(recommendations.router)
app.include_router(forecasts_savings.router)
app.include_router(accounts_runs.router)
app.include_router(pipeline.router)
app.include_router(supervisor.router)
app.include_router(execution.router)
app.include_router(external_factors.router)
app.include_router(chat.router)
app.include_router(focus_summary.router)
app.include_router(governance.router)
app.include_router(phase14.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "cloudcare-api",
        "status": "ok",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "cloudcare-api",
    }
