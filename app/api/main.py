"""The CircadianIQ application/API layer entry point.

    CLIENT -> API -> APPLICATION SERVICES -> DOMAIN/INTELLIGENCE MODULES -> REPOSITORIES -> DATABASE

Routes never contain biological/ML/recommendation/safety logic -- they
only translate HTTP <-> application services, which in turn call the
existing Phase 4-14 modules. Run locally with:

    uvicorn app.api.main:app --reload

OpenAPI docs at ``/docs`` (development only by convention -- see
``docs/api_architecture.md`` "Prototype security limitations").
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.config import load_api_config
from app.api.errors import ApplicationError
from app.api.middleware import CorrelationIdMiddleware
from app.api.routers import behavior, contributors, health, history, inference, interventions, onboarding, participants, recommendation, safety
from app.api.schemas.common import ErrorResponse
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.logging_config import setup_logging

API_PREFIX = "/api/v1"

# Default local dev origins for the Vite frontend (both hostname forms,
# since browsers treat 127.0.0.1 and localhost as distinct origins, and
# a couple of ports past Vite's default in case 5173 was already taken).
# Override with a comma-separated CIRCADIANIQ_CORS_ORIGINS env var.
_DEFAULT_DEV_CORS_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("127.0.0.1", "localhost")
    for port in (5173, 5174, 5175)
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_config = load_api_config()
    setup_logging(api_config.app_config.log_level)

    engine = create_app_engine(api_config.app_config)
    if api_config.is_development:
        # Convenience for local/dev/test runs only -- a real deployment
        # manages schema exclusively through Alembic migrations.
        create_all_tables(engine)

    app.state.api_config = api_config
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    yield

    engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="CircadianIQ API",
        description=(
            "CircadianIQ estimates circadian phase from behavioral and environmental patterns. "
            "It is not a medical device, does not perform laboratory measurements, and does not "
            "diagnose any condition. See the response boundary_note on every prediction-capable endpoint."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)

    # A browser fetch from the Vite dev server (a different origin --
    # different port than the API) is blocked without this, regardless
    # of whether the API itself is reachable and healthy -- see
    # docs/api_architecture.md "Prototype security limitations": this
    # is local-dev-only permissive CORS, not a production configuration.
    cors_env = os.getenv("CIRCADIANIQ_CORS_ORIGINS")
    allowed_origins = [o.strip() for o in cors_env.split(",")] if cors_env else _DEFAULT_DEV_CORS_ORIGINS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    for router_module in (health, onboarding, participants, inference, history, behavior, contributors, recommendation, interventions, safety):
        app.include_router(router_module.router, prefix=API_PREFIX)

    @app.exception_handler(ApplicationError)
    async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        error_code = type(exc).__name__.replace("Error", "").lower() or "error"
        correlation_id = getattr(request.state, "correlation_id", None)
        body = ErrorResponse(error=error_code, message=exc.message, detail=exc.detail, correlation_id=correlation_id)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", None)
        logging.getLogger("app.api").exception("Unhandled exception (correlation_id=%s)", correlation_id)
        body = ErrorResponse(error="internal_error", message="An unexpected error occurred.", correlation_id=correlation_id)
        return JSONResponse(status_code=500, content=body.model_dump())

    return app


app = create_app()
