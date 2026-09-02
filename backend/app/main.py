from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque

import ollama
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.repositories import router as repository_router
from app.api.workspaces import router as workspace_router
from app.config import settings
from app.database import Base, engine
from app.models import CodeChunk, IndexJob
from app.services.schema import ensure_schema


# ------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------

logging.basicConfig(
    level=getattr(
        logging,
        settings.log_level.upper(),
        logging.INFO,
    ),
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    ),
)

logger = logging.getLogger("repopilot")


# ------------------------------------------------------------------
# APPLICATION
# ------------------------------------------------------------------

app = FastAPI(
    title="RepoPilot API",
    version="1.1.0",
    description=(
        "Production-oriented local-first AI codebase "
        "intelligence platform."
    ),
)


# ------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "X-Request-ID",
    ],
)


# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------

# Register each router exactly once.
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(conversations_router)
app.include_router(repository_router)
app.include_router(chat_router)


# ------------------------------------------------------------------
# REQUEST RATE LIMITING
# ------------------------------------------------------------------

RATE_LIMIT_WINDOW_SECONDS = (
    settings.rate_limit_window_seconds
)

RATE_LIMIT_MAX_REQUESTS = (
    settings.rate_limit_max_requests
)

_rate_limit_buckets: dict[
    str,
    deque[float],
] = defaultdict(deque)


def _client_key(request: Request) -> str:
    """
    Identify the caller for the in-process rate limiter.

    When running behind a trusted reverse proxy, use the direct
    client address rather than blindly trusting arbitrary
    X-Forwarded-For headers.
    """
    client = request.client

    if client is None:
        return "unknown"

    return client.host


@app.middleware("http")
async def rate_limit_middleware(
    request: Request,
    call_next,
):
    """
    Basic in-process request rate limiter.

    This is intentionally simple and dependency-free.
    For multiple replicas/workers, use Redis-backed limiting.
    """
    # Do not rate-limit CORS preflight requests.
    if request.method == "OPTIONS":
        return await call_next(request)

    # Keep health probes available even under application load.
    if request.url.path.startswith("/health"):
        return await call_next(request)

    if not settings.rate_limit_enabled:
        return await call_next(request)

    client_key = _client_key(request)
    now = time.monotonic()

    bucket = _rate_limit_buckets[client_key]

    while (
        bucket
        and (
            now - bucket[0]
            > RATE_LIMIT_WINDOW_SECONDS
        )
    ):
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        retry_after = max(
            1,
            int(
                RATE_LIMIT_WINDOW_SECONDS
                - (now - bucket[0])
            ),
        )

        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    "Too many requests. "
                    "Please try again later."
                )
            },
            headers={
                "Retry-After": str(retry_after),
            },
        )

    bucket.append(now)

    return await call_next(request)


# ------------------------------------------------------------------
# REQUEST CONTEXT / STRUCTURED LOGGING
# ------------------------------------------------------------------

@app.middleware("http")
async def request_context_middleware(
    request: Request,
    call_next,
):
    request_id = (
        request.headers.get("X-Request-ID")
        or str(uuid.uuid4())
    )

    started = time.perf_counter()

    try:
        response = await call_next(request)

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )

        # Do not expose internal exception details.
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error."
            },
            headers={
                "X-Request-ID": request_id,
            },
        )

    finally:
        latency_ms = round(
            (
                time.perf_counter()
                - started
            )
            * 1000,
            2,
        )

        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "latency_ms": latency_ms,
            },
        )

    response.headers[
        "X-Request-ID"
    ] = request_id

    return response


# ------------------------------------------------------------------
# HEALTH
# ------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "repopilot",
        "environment": settings.environment,
    }


@app.get("/health/database")
def database_health_check():
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as exc:
        logger.exception(
            "database_health_check_failed"
        )

        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc


@app.get("/health/ollama")
def ollama_health_check():
    try:
        client = ollama.Client(
            host=settings.ollama_url,
            timeout=settings.healthcheck_timeout_seconds,
        )

        client.list()

        return {
            "status": "ok",
            "ollama": "connected",
        }

    except Exception as exc:
        logger.exception(
            "ollama_health_check_failed"
        )

        raise HTTPException(
            status_code=503,
            detail="Ollama unavailable",
        ) from exc


@app.get("/ready")
def readiness_check():
    """
    Kubernetes/load-balancer style readiness endpoint.

    A healthy process is not necessarily ready if the database
    cannot be reached.
    """
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        return {
            "status": "ready",
        }

    except Exception as exc:
        logger.exception(
            "readiness_check_failed"
        )

        raise HTTPException(
            status_code=503,
            detail="Service not ready",
        ) from exc


# ------------------------------------------------------------------
# METRICS
# ------------------------------------------------------------------

@app.get("/metrics")
def metrics():
    try:
        with engine.connect() as connection:
            repos = (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        "FROM repositories"
                    )
                ).scalar()
                or 0
            )

            chunks = (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        "FROM code_chunks"
                    )
                ).scalar()
                or 0
            )

            queued_jobs = (
                connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM index_jobs
                        WHERE status = 'queued'
                        """
                    )
                ).scalar()
                or 0
            )

            running_jobs = (
                connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM index_jobs
                        WHERE status = 'running'
                        """
                    )
                ).scalar()
                or 0
            )

        return {
            "repositories": repos,
            "chunks": chunks,
            "queued_jobs": queued_jobs,
            "running_jobs": running_jobs,
        }

    except Exception:
        logger.exception(
            "metrics_query_failed"
        )

        raise HTTPException(
            status_code=503,
            detail="Metrics unavailable",
        )


# ------------------------------------------------------------------
# STARTUP
# ------------------------------------------------------------------

def initialize_database() -> None:
    """
    Development/local compatibility initializer.

    Production deployments should run Alembic migrations before
    starting the application instead of relying on create_all().
    """
    if settings.auto_create_tables:
        Base.metadata.create_all(
            bind=engine
        )

    if settings.ensure_schema_on_startup:
        ensure_schema()


@app.on_event("startup")
def startup_event():
    initialize_database()

    logger.info(
        "repopilot_api_started",
        extra={
            "environment": settings.environment,
            "worker_enabled": settings.worker_enabled,
        },
    )

    # In production, prefer a dedicated worker container/process.
    # This remains available for local development.
    if settings.worker_enabled:
        from app.services.worker import run_worker

        import threading

        worker_thread = threading.Thread(
            target=run_worker,
            name="repopilot-index-worker",
            daemon=True,
        )

        worker_thread.start()

        logger.info(
            "embedded_worker_started"
        )