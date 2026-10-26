"""FastAPI application factory: lifespan, middleware, error handlers and routers."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.errors import register_handlers
from app.db import dispose_engine, init_db
from app.routers import admin, auth, common, profile, public, recruiter, recruiter_jobs, seeker
from app.services.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
UPLOAD_SUBDIRS = ("logos", "banners", "photos", "resumes")


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger().setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting up")
    init_db()
    upload_root = Path(settings.upload_dir)
    for sub in UPLOAD_SUBDIRS:
        (upload_root / sub).mkdir(parents=True, exist_ok=True)
    start_scheduler()
    try:
        yield
    finally:
        logger.info("Shutting down")
        stop_scheduler()
        dispose_engine()
        logger.info("Shutdown complete")


app = FastAPI(
    title="Job Portal API",
    version="1.0.0",
    description="Job portal: search, applications, recruiter tools, admin, notifications and messaging.",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

register_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Propagate/generate X-Request-ID and log one line per request."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if request.url.path not in ("/health", f"{API_PREFIX}/health"):
        logger.info(
            "%s %s -> %s (%.1f ms) rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            request_id,
        )
    return response


# Added after the logging middleware so CORS is outermost and also decorates error responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)

# Order matters: static routes in earlier routers must win over param routes in later ones.
for _module in (common, auth, seeker, profile, recruiter, recruiter_jobs, admin, public):
    app.include_router(_module.router, prefix=API_PREFIX)

# Root-level GET /health (only the health route, not every common route).
app.include_router(common.health_router)
