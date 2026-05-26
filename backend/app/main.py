from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.database import engine, Base
from app.api.v1.router import router as v1_router
from app.scheduler import start_scheduler, shutdown_scheduler
from app.core.exceptions import AppException
# Ensure all models are imported for table creation
import app.models.daily_report  # noqa: F401
import app.models.category  # noqa: F401
import app.models.feedback  # noqa: F401
import app.models.weekly_digest  # noqa: F401
import app.models.trending  # noqa: F401
import app.models.mother_topic  # noqa: F401
import app.models.fanqie  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.qimao  # noqa: F401
import app.models.zhihu  # noqa: F401
import app.models.scheduled_job  # noqa: F401
import app.models.llm_model  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all SQLite tables
    if settings.AUTO_CREATE_TABLES_ON_STARTUP:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        logger.info("Startup table creation skipped by config")

    # Seed categories from hardcoded defaults (no-op if already seeded)
    if settings.STARTUP_SEED_ENABLED:
        try:
            from app.database import async_session
            from app.services.classifier import seed_categories
            async with async_session() as seed_db:
                await seed_categories(seed_db)
                await seed_db.commit()
        except Exception as e:
            logger.warning("Category seed skipped: %s", e)
    else:
        logger.info("Category seed skipped by config")

    # Seed mother topics (4 content pillars for 大痴小乙)
    if settings.STARTUP_SEED_ENABLED:
        try:
            from app.database import async_session
            from app.services.mother_topic_seed import seed_mother_topics
            async with async_session() as seed_db:
                added = await seed_mother_topics()
                await seed_db.commit()
                logger.info("Mother topics seeded (%d new)", added)
        except Exception as e:
            logger.warning("Mother topic seed skipped: %s", e)
    else:
        logger.info("Mother topic seed skipped by config")

    # Initialize DuckDB analytical layer (in-memory + ATTACH SQLite)
    try:
        from app.services.duckdb_service import get_analytics
        analytics = get_analytics()
        if analytics.available:
            logger.info("DuckDB analytical layer initialized (ATTACH SQLite READ_ONLY)")
        else:
            logger.warning("DuckDB analytical layer not available — falling back to SQLite queries")
    except Exception as e:
        logger.warning("DuckDB init skipped: %s — falling back to SQLite queries", e)

    # Start the periodic scheduler
    if settings.SCHEDULER_ENABLED:
        start_scheduler()
        logger.info("Application startup complete — scheduler running")
    else:
        logger.info("Application startup complete — scheduler disabled by config")

    yield

    # Shutdown: stop scheduler, close connections, dispose engine
    shutdown_scheduler()

    # Close DuckDB analytics connection
    try:
        from app.services.duckdb_service import close_analytics
        close_analytics()
    except Exception:
        pass

    await engine.dispose()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="TopicEye API",
    description="AI-powered content discovery and topic analysis platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount v1 API routes
app.include_router(v1_router)


# ── Global exception handlers ─────────────────────────────────────────

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "detail": exc.detail},
        headers={} if not exc.detail else None,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": {}},
    )


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "topiceye-backend"}
