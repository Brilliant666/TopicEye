"""
APScheduler-based periodic task scheduler.

Per-source scheduling:
    - Each enabled source gets its own IntervalTrigger job.
    - Interval is read from source.fetch_interval_minutes (default 60 min).
    - A rescan job runs every 10 minutes to pick up new / updated sources.
    - cleanup_old_content: daily at 03:00.

All DB access goes through Repository layer — no raw SQL here.

Job tracking:
    - Every scheduled job is wrapped with @track_job decorator.
    - Execution records go to job_execution_logs table.
    - Task configs are auto-registered to scheduled_jobs table.
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
from app.services.job_tracker import track_job

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent DB write tasks — SQLite single-writer constraint.
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

@track_job("sync_and_analyze", name="全量信源同步+分析", timeout=600,
           description="同步所有启用的信源，自动分析新内容，聚类+趋势快照")
async def sync_and_analyze() -> None:
    """Legacy: sync all enabled sources, then auto-analyze new pending content."""
    logger.info("Scheduler: sync_and_analyze started")

    # ── Phase 1: Sync sources ──
    async with async_session() as db:
        source_repo = SourceRepository(db)
        sources = await source_repo.get_enabled_sources()

        for source in sources:
            try:
                stats = await ingest_from_source(source, db)
                logger.info("Scheduler: synced source '%s' — %s", source.name, stats)
            except Exception:
                logger.exception("Scheduler: failed to sync source '%s' (id=%d)", source.name, source.id)
            await db.commit()

    logger.info("Scheduler: sync finished (%d sources)", len(sources))

    # ── Phase 2: Auto-analyze pending content ──
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


@track_job("cleanup_old_content", name="清理90天前的待处理内容", timeout=120,
           description="删除 pending 状态超过90天的内容")
async def cleanup_old_content() -> None:
    """Remove pending content older than 90 days."""
    logger.info("Scheduler: cleanup_old_content started")
    cutoff = datetime.utcnow() - timedelta(days=90)

    async with async_session() as db:
        content_repo = ContentRepo(db)
        removed = await content_repo.delete_old_pending(cutoff_days=90)
        await db.commit()
        logger.info("Scheduler: cleanup_old_content removed %d old pending items", removed)
        return f"removed={removed}"


@track_job("sync_trending", name="趋势雷达数据同步", timeout=120,
           description="每30分钟同步所有趋势信源数据")
async def _sync_all_trending() -> None:
    """Sync all trending sources (lightweight, no LLM)."""
    from app.services.trending_pipeline import sync_all_trending
    try:
        async with async_session() as db:
            results = await sync_all_trending(db)
            await db.commit()
        total = sum(r.get("fetched", 0) for r in results.values())
        logger.info("Scheduler: trending sync done — %d items from %d sources", total, len(results))
        return f"fetched={total}, sources={len(results)}"
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
    """Every 10 minutes: sync scheduler job list with enabled sources from DB."""
    async with async_session() as db:
        source_repo = SourceRepository(db)
        sources = await source_repo.get_enabled_sources()

    current_job_ids = {job.id for job in scheduler.get_jobs()}
    source_job_prefix = "source_sync_"
    db_source_ids = {f"{source_job_prefix}{s.id}" for s in sources}

    for job_id in current_job_ids:
        if job_id.startswith(source_job_prefix) and job_id not in db_source_ids:
            scheduler.remove_job(job_id)
            logger.info("Scheduler: removed job %s (source disabled)", job_id)

    for source in sources:
        job_id = f"{source_job_prefix}{source.id}"
        interval_minutes = source.fetch_interval_minutes or 60

        existing = scheduler.get_job(job_id)
        if existing:
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
            logger.info("Scheduler: added job %s (%s) interval=%d min", job_id, source.name, interval_minutes)

    logger.info("Scheduler: source rescan complete — %d active jobs", len(sources))


@track_job("save_trending_snapshots", name="趋势快照保存", timeout=120,
           description="每日00:30保存趋势数据快照")
async def _save_trending_snapshots() -> None:
    """Save daily snapshot for all trending sources at 00:30."""
    logger.info("Scheduler: save_trending_snapshots started")
    try:
        async with async_session() as db:
            from app.services.trending_snapshot import save_all_snapshots
            results = await save_all_snapshots(db)
            await db.commit()
        logger.info("Scheduler: trending snapshots saved — %s", results)
        return str(results)
    except Exception:
        logger.exception("Scheduler: save_trending_snapshots failed")


@track_job("cleanup_trending_snapshots", name="清理过期趋势快照", timeout=60,
           description="每日01:00清理15天前的趋势快照")
async def _cleanup_old_trending_snapshots() -> None:
    """Delete trending snapshots older than 15 days at 01:00."""
    logger.info("Scheduler: cleanup_old_trending_snapshots started")
    try:
        async with async_session() as db:
            from app.services.trending_snapshot import cleanup_old_snapshots
            count = await cleanup_old_snapshots(db)
            await db.commit()
        logger.info("Scheduler: cleanup_old_trending_snapshots removed %d records", count)
        return f"removed={count}"
    except Exception:
        logger.exception("Scheduler: cleanup_old_trending_snapshots failed")


@track_job("sync_fanqie", name="番茄小说榜单抓取", timeout=300,
           description="每日凌晨1点抓取番茄小说34个分类榜单")
async def _sync_fanqie() -> None:
    """番茄小说榜单每日抓取（凌晨1点）。"""
    logger.info("Scheduler: fanqie sync started")
    try:
        from app.services.fanqie_service import full_sync
        result = await full_sync()
        logger.info("Scheduler: fanqie sync done — %s", result)
        return str(result)
    except Exception:
        logger.exception("Scheduler: fanqie sync failed")


# ── NEW: AI 日报 & 周刊定时任务 ──────────────────────────────────────

@track_job("daily_report", name="AI日报生成", timeout=300,
           description="每日早8点生成AI日报，基于当日已分析内容")
async def _generate_daily_report() -> None:
    """Generate AI daily report at 08:00."""
    logger.info("Scheduler: daily report generation started")
    try:
        from app.services.daily_report import generate_daily_report
        async with async_session() as db:
            report = await generate_daily_report(db)
        logger.info("Scheduler: daily report generated — %s (%s)", report.report_date, report.status)
        return f"date={report.report_date}, status={report.status}"
    except Exception:
        logger.exception("Scheduler: daily report generation failed")


@track_job("weekly_digest", name="AI周刊生成", timeout=300,
           description="每周一早9点生成AI周刊，基于本周已分析内容")
async def _generate_weekly_digest() -> None:
    """Generate AI weekly digest at 09:00 every Monday."""
    logger.info("Scheduler: weekly digest generation started")
    try:
        from app.services.weekly_digest import generate_weekly_digest
        async with async_session() as db:
            digest = await generate_weekly_digest(db)
        logger.info("Scheduler: weekly digest generated — %s (%s)", digest.week_key, digest.status)
        return f"week={digest.week_key}, status={digest.status}"
    except Exception:
        logger.exception("Scheduler: weekly digest generation failed")


# ── Lifecycle helpers ─────────────────────────────────────────────────

def start_scheduler() -> None:
    """Register all scheduled jobs and start the scheduler."""
    # Periodic rescan to catch new/updated/disabled sources
    scheduler.add_job(
        _rescan_sources,
        trigger=IntervalTrigger(minutes=10),
        id="rescan_sources",
        name="Rescan enabled sources and update scheduler",
        replace_existing=True,
    )

    # Daily cleanup at 03:00
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

    # Trending snapshot: save daily snapshot at 00:30
    scheduler.add_job(
        _save_trending_snapshots,
        trigger=CronTrigger(hour=0, minute=30),
        id="save_trending_snapshots",
        name="Save daily trending snapshots",
        replace_existing=True,
    )

    # Cleanup trending snapshots at 01:00
    scheduler.add_job(
        _cleanup_old_trending_snapshots,
        trigger=CronTrigger(hour=1, minute=0),
        id="cleanup_trending_snapshots",
        name="Cleanup trending snapshots older than 15 days",
        replace_existing=True,
    )

    # 番茄小说榜单：每日凌晨1点抓取
    scheduler.add_job(
        _sync_fanqie,
        trigger=CronTrigger(hour=1, minute=0),
        id="sync_fanqie",
        name="番茄小说榜单每日抓取",
        replace_existing=True,
    )

    # AI日报：每日早8点生成
    scheduler.add_job(
        _generate_daily_report,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_report",
        name="AI日报生成",
        replace_existing=True,
    )

    # AI周刊：每周一早9点生成
    scheduler.add_job(
        _generate_weekly_digest,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_digest",
        name="AI周刊生成",
        replace_existing=True,
    )

    scheduler.start()

    # Immediately register all enabled sources so they start syncing
    # right away instead of waiting for the first 10-minute rescan.
    import asyncio as _asyncio
    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_rescan_sources())
            logger.info("Scheduler: initial source rescan scheduled immediately")
    except RuntimeError:
        logger.warning("Scheduler: could not schedule initial rescan (no event loop)")

    logger.info(
        "Scheduler started: per-source sync + 10min rescan + cleanup + "
        "daily_report(08:00) + weekly_digest(Mon 09:00)"
    )


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
