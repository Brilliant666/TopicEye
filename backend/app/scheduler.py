"""
APScheduler-based periodic task scheduler.

Per-source scheduling:
    - Each enabled source gets its own IntervalTrigger job.
    - Interval is read from source.fetch_interval_minutes (default 60 min).
    - A rescan job runs every 10 minutes to pick up new / updated sources.
    - cleanup_old_content: daily at 03:00.

All DB access goes through Repository layer — no raw SQL here.
"""

from __future__ import annotations

import asyncio
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

# Semaphore to limit concurrent DB write tasks — SQLite single-writer constraint.
# Allows a small number of parallel sync jobs (each opens its own session)
# while preventing lock storms when 160+ sources trigger simultaneously.
_MAX_CONCURRENT_SYNCS = 3
_sync_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _sync_semaphore
    if _sync_semaphore is None:
        _sync_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SYNCS)
    return _sync_semaphore

scheduler = AsyncIOScheduler(
    timezone="Asia/Shanghai",
    job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 120},
)


# ── Scheduled jobs ────────────────────────────────────────────────────

async def sync_and_analyze() -> None:
    """Legacy: sync all enabled sources, then auto-analyze new pending content.

    Kept for backward compatibility — prefer per-source jobs registered in
    start_scheduler() which respect each source's fetch_interval_minutes.
    """
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

async def _sync_all_trending() -> None:
    """Sync all trending sources (lightweight, no LLM)."""
    from app.services.trending_pipeline import sync_all_trending
    try:
        async with async_session() as db:
            results = await sync_all_trending(db)
            await db.commit()
        total = sum(r.get("fetched", 0) for r in results.values())
        logger.info("Scheduler: trending sync done — %d items from %d sources", total, len(results))
    except Exception:
        logger.exception("Scheduler: trending sync failed")


async def _sync_single_source(source_id: int) -> None:
    """Job handler: sync one source by ID, then run shared post-sync pipeline."""
    sem = _get_semaphore()
    async with sem:
        async with async_session() as db:
            from app.repositories.source_repo import SourceRepository
            source_repo = SourceRepository(db)
            source = await source_repo.get_by_id(source_id)
            if not source or not source.enabled:
                logger.debug("Source id=%d skipped (not found or disabled)", source_id)
                return
            try:
                stats = await ingest_from_source(source, db)
                await db.commit()
                logger.info("Scheduler: source '%s' synced — %s", source.name, stats)
            except Exception:
                logger.exception("Scheduler: failed to sync source id=%d", source_id)
                await db.rollback()

        # Shared post-sync: analyze pending + cluster + trends
        await _run_post_sync_pipeline()


async def _run_post_sync_pipeline() -> None:
    """Analyze pending, cluster, and snapshot trends. Called after each sync."""
    BATCH_SIZE = 20
    async with async_session() as db:
        content_repo = ContentRepo(db)
        pending = await content_repo.get_by_status(ContentStatus.PENDING, limit=BATCH_SIZE)
        pending_ids = [item.id for item in pending]
    if pending_ids:
        try:
            async with async_session() as db:
                await analyze_batch(pending_ids, db)
            logger.info("Scheduler: auto-analysis complete for %d items", len(pending_ids))
        except Exception:
            logger.exception("Scheduler: auto-analysis failed")
    try:
        async with async_session() as db:
            from app.services.topic_clustering import cluster_and_dedup
            stats = await cluster_and_dedup(db)
        logger.info("Scheduler: clustering done — %s", stats)
    except Exception:
        logger.exception("Scheduler: clustering failed")
    try:
        async with async_session() as db:
            from app.services.trends import snapshot_daily_trends
            stats = await snapshot_daily_trends(db)
            await db.commit()
        logger.info("Scheduler: trend snapshot done — %s", stats)
    except Exception:
        logger.exception("Scheduler: trend snapshot failed")


async def _rescan_sources() -> None:
    """Every 10 minutes: sync scheduler job list with enabled sources from DB.

    - New enabled sources → add a per-source IntervalTrigger job.
    - Disabled sources → remove their jobs.
    - Interval changed → replace the job.
    """
    async with async_session() as db:
        source_repo = SourceRepository(db)
        sources = await source_repo.get_enabled_sources()

    current_job_ids = {job.id for job in scheduler.get_jobs()}
    source_job_prefix = "source_sync_"
    db_source_ids = {f"{source_job_prefix}{s.id}" for s in sources}

    # Remove jobs for disabled/deleted sources
    for job_id in current_job_ids:
        if job_id.startswith(source_job_prefix) and job_id not in db_source_ids:
            scheduler.remove_job(job_id)
            logger.info("Scheduler: removed job %s (source disabled)", job_id)

    # Add or update jobs for each enabled source
    for source in sources:
        job_id = f"{source_job_prefix}{source.id}"
        interval_minutes = source.fetch_interval_minutes or 60

        existing = scheduler.get_job(job_id)
        if existing:
            # Check if interval changed
            existing_interval = existing.trigger.interval.seconds // 60
            if existing_interval != interval_minutes:
                scheduler.reschedule_job(job_id, trigger=IntervalTrigger(minutes=interval_minutes))
                logger.info("Scheduler: updated job %s interval to %d min", job_id, interval_minutes)
        else:
            scheduler.add_job(
                _sync_single_source,
                trigger=IntervalTrigger(minutes=interval_minutes),
                id=job_id,
                name=f"Sync source: {source.name}",
                replace_existing=True,
                kwargs={"source_id": source.id},
            )
            logger.info("Scheduler: added job %s (%s) interval=%d min",
                         job_id, source.name, interval_minutes)

    logger.info("Scheduler: source rescan complete — %d active jobs", len(sources))


async def _save_trending_snapshots() -> None:
    """Save daily snapshot for all trending sources at 00:30."""
    logger.info("Scheduler: save_trending_snapshots started")
    try:
        async with async_session() as db:
            from app.services.trending_snapshot import save_all_snapshots
            results = await save_all_snapshots(db)
            await db.commit()
        logger.info("Scheduler: trending snapshots saved — %s", results)
    except Exception:
        logger.exception("Scheduler: save_trending_snapshots failed")


async def _cleanup_old_trending_snapshots() -> None:
    """Delete trending snapshots older than 15 days at 01:00."""
    logger.info("Scheduler: cleanup_old_trending_snapshots started")
    try:
        async with async_session() as db:
            from app.services.trending_snapshot import cleanup_old_snapshots
            count = await cleanup_old_snapshots(db)
            await db.commit()
        logger.info("Scheduler: cleanup_old_trending_snapshots removed %d records", count)
    except Exception:
        logger.exception("Scheduler: cleanup_old_trending_snapshots failed")


# ── Lifecycle helpers ─────────────────────────────────────────────────

def start_scheduler() -> None:
    """Register per-source jobs and start the scheduler."""
    # Periodic rescan to catch new/updated/disabled sources
    # (initial scan happens via the first _rescan_sources() job run)
    scheduler.add_job(
        _rescan_sources,
        trigger=IntervalTrigger(minutes=10),
        id="rescan_sources",
        name="Rescan enabled sources and update scheduler",
        replace_existing=True,
    )

    # Daily cleanup
    scheduler.add_job(
        cleanup_old_content,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_old_content",
        name="Cleanup old pending content",
        replace_existing=True,
    )

    # Trending radar: sync all trending sources every 30 minutes
    scheduler.add_job(
        _sync_all_trending,
        trigger=IntervalTrigger(minutes=30),
        id="sync_trending",
        name="Sync all trending sources",
        replace_existing=True,
    )

    # Trending snapshot: save daily snapshot at 00:30, cleanup old at 01:00
    scheduler.add_job(
        _save_trending_snapshots,
        trigger=CronTrigger(hour=0, minute=30),
        id="save_trending_snapshots",
        name="Save daily trending snapshots",
        replace_existing=True,
    )
    scheduler.add_job(
        _cleanup_old_trending_snapshots,
        trigger=CronTrigger(hour=1, minute=0),
        id="cleanup_trending_snapshots",
        name="Cleanup trending snapshots older than 15 days",
        replace_existing=True,
    )

    scheduler.start()

    # Immediately register all enabled sources so they start syncing
    # right away instead of waiting for the first 10-minute rescan.
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_rescan_sources())
            logger.info("Scheduler: initial source rescan scheduled immediately")
    except RuntimeError:
        logger.warning("Scheduler: could not schedule initial rescan (no event loop)")

    logger.info("Scheduler started: per-source sync jobs + 10min rescan + 03:00 cleanup")


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
