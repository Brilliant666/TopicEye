"""
APScheduler-based periodic task scheduler.

Jobs:
    - sync_and_analyze: every 30 minutes, sync all enabled sources,
      then auto-analyze new pending content.
    - cleanup_old_content: daily at 03:00, remove stale pending content.

All DB access goes through Repository layer — no raw SQL here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.database import async_session
from app.models.content import ContentStatus
from app.repositories.source_repo import SourceRepository
from app.repositories.content_repo import ContentRepo
from app.services.content_pipeline import ingest_from_source
from app.services.analysis import analyze_batch

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


# ── Scheduled jobs ────────────────────────────────────────────────────

async def sync_and_analyze() -> None:
    """Sync all enabled sources, then auto-analyze new pending content."""
    logger.info("Scheduler: sync_and_analyze started")

    # ── Phase 1: Sync sources via SourceRepository ──
    async with async_session() as db:
        source_repo = SourceRepository(db)
        sources = await source_repo.get_enabled_sources()

        for source in sources:
            try:
                stats = await ingest_from_source(source, db)
                logger.info(
                    "Scheduler: synced source '%s' — %s",
                    source.name, stats,
                )
            except Exception:
                logger.exception(
                    "Scheduler: failed to sync source '%s' (id=%d)",
                    source.name, source.id,
                )
            await db.commit()

    logger.info("Scheduler: sync finished (%d sources)", len(sources))

    # ── Phase 2: Auto-analyze pending content via ContentRepo ──
    BATCH_SIZE = 20
    async with async_session() as db:
        content_repo = ContentRepo(db)
        pending = await content_repo.get_by_status(ContentStatus.PENDING, limit=BATCH_SIZE)
        pending_ids = [item.id for item in pending]

    if not pending_ids:
        logger.info("Scheduler: no pending content to analyze")
        return

    logger.info("Scheduler: auto-analyzing %d pending items", len(pending_ids))
    try:
        async with async_session() as db:
            await analyze_batch(pending_ids, db)
        logger.info("Scheduler: auto-analysis complete for %d items", len(pending_ids))
    except Exception:
        logger.exception("Scheduler: auto-analysis failed")

    # ── Phase 3: Cluster + dedup ──
    try:
        async with async_session() as db:
            from app.services.topic_clustering import cluster_and_dedup
            stats = await cluster_and_dedup(db)
        logger.info("Scheduler: clustering done — %s", stats)
    except Exception:
        logger.exception("Scheduler: clustering failed")

    # ── Phase 4: Trend snapshot ──
    try:
        async with async_session() as db:
            from app.services.trends import snapshot_daily_trends
            stats = await snapshot_daily_trends(db)
            await db.commit()
        logger.info("Scheduler: trend snapshot done — %s", stats)
    except Exception:
        logger.exception("Scheduler: trend snapshot failed")

    # Note: DuckDB analytical layer reads SQLite directly (READ_ONLY ATTACH).
    # No sync step needed — DuckDB queries always see fresh data.


async def cleanup_old_content() -> None:
    """Remove pending content older than 90 days."""
    logger.info("Scheduler: cleanup_old_content started")
    cutoff = datetime.utcnow() - timedelta(days=90)

    async with async_session() as db:
        content_repo = ContentRepo(db)
        removed = await content_repo.delete_old_pending(cutoff_days=90)
        await db.commit()
        logger.info(
            "Scheduler: cleanup_old_content removed %d old pending items",
            removed,
        )


# ── Lifecycle helpers ─────────────────────────────────────────────────

def start_scheduler() -> None:
    """Register jobs and start the scheduler."""
    scheduler.add_job(
        sync_and_analyze,
        trigger=IntervalTrigger(minutes=30),
        id="sync_and_analyze",
        name="Sync sources and auto-analyze pending content",
        replace_existing=True,
    )

    scheduler.add_job(
        cleanup_old_content,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_old_content",
        name="Cleanup old pending content",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: sync+analyze every 30min, cleanup at 03:00")


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
