from contextlib import asynccontextmanager
import logging
from sqlalchemy import text
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
import app.models.monthly_digest  # noqa: F401
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


async def ensure_source_sort_order_column(conn) -> None:
    """SQLite create_all does not add columns to existing tables."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    result = await conn.execute(text("PRAGMA table_info(sources)"))
    columns = {row[1] for row in result.fetchall()}
    if "sort_order" not in columns:
        await conn.execute(text("ALTER TABLE sources ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
    await conn.execute(text("UPDATE sources SET sort_order = id * 10 WHERE sort_order = 0 OR sort_order IS NULL"))


async def ensure_daily_report_version_schema(conn) -> None:
    """SQLite create_all does not remove old unique constraints; rebuild daily_reports if needed."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    table_exists = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_reports'"
    ))
    if table_exists.scalar_one_or_none() is None:
        return

    result = await conn.execute(text("PRAGMA table_info(daily_reports)"))
    columns = {row[1] for row in result.fetchall()}
    required = {"edition", "generated_at", "window_start", "window_end", "cutoff_at", "source_scope", "source_item_ids"}

    index_rows = await conn.execute(text("PRAGMA index_list(daily_reports)"))
    has_report_date_unique = False
    for row in index_rows.fetchall():
        index_name = row[1]
        is_unique = bool(row[2])
        if not is_unique:
            continue
        info_rows = await conn.execute(text(f"PRAGMA index_info('{index_name}')"))
        index_cols = [info[2] for info in info_rows.fetchall()]
        if index_cols == ["report_date"]:
            has_report_date_unique = True
            break

    if required.issubset(columns) and not has_report_date_unique:
        return

    logger.info("Rebuilding daily_reports table for versioned report schema")
    missing_column_sql = {
        "edition": "ALTER TABLE daily_reports ADD COLUMN edition VARCHAR(20) DEFAULT 'legacy'",
        "generated_at": "ALTER TABLE daily_reports ADD COLUMN generated_at DATETIME",
        "window_start": "ALTER TABLE daily_reports ADD COLUMN window_start DATETIME",
        "window_end": "ALTER TABLE daily_reports ADD COLUMN window_end DATETIME",
        "cutoff_at": "ALTER TABLE daily_reports ADD COLUMN cutoff_at DATETIME",
        "source_scope": "ALTER TABLE daily_reports ADD COLUMN source_scope VARCHAR(20) DEFAULT 'curated'",
        "source_item_ids": "ALTER TABLE daily_reports ADD COLUMN source_item_ids TEXT",
    }
    for column, sql in missing_column_sql.items():
        if column not in columns:
            await conn.execute(text(sql))

    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS daily_reports_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date VARCHAR(10) NOT NULL,
            weekday VARCHAR(10) NOT NULL,
            edition VARCHAR(20) NOT NULL DEFAULT 'snapshot',
            generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            window_start DATETIME,
            window_end DATETIME,
            cutoff_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_scope VARCHAR(20) NOT NULL DEFAULT 'curated',
            source_item_ids TEXT,
            overview TEXT,
            takeaway TEXT,
            keywords TEXT,
            trends TEXT,
            top_picks TEXT,
            platform_tips TEXT,
            topic_count INTEGER NOT NULL DEFAULT 0,
            content_count INTEGER NOT NULL DEFAULT 0,
            analyzed_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at DATETIME,
            updated_at DATETIME,
            CONSTRAINT uq_daily_report_version UNIQUE (report_date, edition, cutoff_at)
        )
    """))
    await conn.execute(text("""
        INSERT OR IGNORE INTO daily_reports_new (
            id, report_date, weekday, edition, generated_at, window_start, window_end, cutoff_at,
            source_scope, source_item_ids, overview, takeaway, keywords, trends, top_picks,
            platform_tips, topic_count, content_count, analyzed_count, status, created_at, updated_at
        )
        SELECT
            id,
            report_date,
            weekday,
            COALESCE(NULLIF(edition, ''), 'legacy'),
            COALESCE(generated_at, updated_at, created_at, CURRENT_TIMESTAMP),
            COALESCE(window_start, report_date || ' 00:00:00'),
            COALESCE(window_end, report_date || ' 23:59:59'),
            COALESCE(cutoff_at, updated_at, created_at, CURRENT_TIMESTAMP),
            COALESCE(source_scope, 'curated'),
            source_item_ids,
            overview,
            takeaway,
            keywords,
            trends,
            top_picks,
            platform_tips,
            COALESCE(topic_count, 0),
            COALESCE(content_count, 0),
            COALESCE(analyzed_count, 0),
            COALESCE(status, 'PENDING'),
            created_at,
            updated_at
        FROM daily_reports
    """))
    await conn.execute(text("DROP TABLE daily_reports"))
    await conn.execute(text("ALTER TABLE daily_reports_new RENAME TO daily_reports"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_reports_report_date ON daily_reports(report_date)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_reports_edition ON daily_reports(edition)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_reports_cutoff_at ON daily_reports(cutoff_at)"))


async def ensure_llm_call_logs_schema(conn) -> None:
    """SQLite create_all does not update existing installs with new telemetry columns."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS llm_call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id VARCHAR(64) NOT NULL UNIQUE,
            model_id INTEGER,
            model_name VARCHAR(100),
            provider VARCHAR(50),
            request_model VARCHAR(200),
            actual_model VARCHAR(200),
            scene VARCHAR(50) NOT NULL DEFAULT 'general',
            status VARCHAR(20) NOT NULL DEFAULT 'DONE',
            error_message TEXT,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
            billable_input_tokens INTEGER NOT NULL DEFAULT 0,
            input_cost FLOAT NOT NULL DEFAULT 0,
            output_cost FLOAT NOT NULL DEFAULT 0,
            cache_read_cost FLOAT NOT NULL DEFAULT 0,
            cache_creation_cost FLOAT NOT NULL DEFAULT 0,
            total_cost FLOAT NOT NULL DEFAULT 0,
            cost_per_1m_input FLOAT,
            cost_per_1m_output FLOAT,
            cost_per_1m_input_cache_hit FLOAT,
            cost_per_1m_input_cache_create FLOAT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_llm_call_logs_request_id ON llm_call_logs(request_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_model_id ON llm_call_logs(model_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_provider ON llm_call_logs(provider)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_scene ON llm_call_logs(scene)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_status ON llm_call_logs(status)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_created_at ON llm_call_logs(created_at)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_model_created ON llm_call_logs(model_id, created_at)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_llm_call_logs_scene_created ON llm_call_logs(scene, created_at)"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create all SQLite tables
    if settings.AUTO_CREATE_TABLES_ON_STARTUP:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_source_sort_order_column(conn)
            await ensure_daily_report_version_schema(conn)
            await ensure_llm_call_logs_schema(conn)
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
