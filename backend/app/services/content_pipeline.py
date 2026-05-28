"""
Content ingestion pipeline.

Orchestrates fetching, deduplication, classification, and storage for a
single source. Uses the scraper registry to dispatch by SourceType.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, SourceType, SourceStatus
from app.models.content import ContentItem, ContentStatus
from app.services.dedup import build_hash
from app.services.classifier import classify, extract_tags, classify_async
from app.services.scrapers import get_scraper_cls

logger = logging.getLogger(__name__)


async def ingest_from_source(source: Source, db: AsyncSession) -> dict[str, int]:
    """
    Full ingestion pipeline for a single source.

    Steps:
        1. Look up the scraper class for this source_type.
        2. Fetch content entries.
        3. Compute content_hash for each entry and skip duplicates.
        4. Classify and tag each new entry.
        5. Persist ContentItem records.
        6. Update source.last_sync_at and status.

    Returns ``{"fetched": N, "new": N, "duplicates": N}``.
    """
    fetched_count = 0
    new_count = 0
    duplicate_count = 0

    try:
        # ── Step 1: Resolve scraper ──────────────────────────────────
        source_type_str = source.source_type.value if source.source_type else "RSS"

        # Skip ZHIHU: its hot topics are now served exclusively via trending radar
        # and should not be duplicated into the content feed.
        if source_type_str == "ZHIHU":
            logger.info("Source '%s' (ZHIHU): skipped — topics served via trending radar", source.name)
            return {"fetched": 0, "new": 0, "duplicates": 0}

        scraper_cls = get_scraper_cls(source_type_str)

        if scraper_cls is None:
            logger.warning(
                "No scraper registered for source_type '%s' (source %d)",
                source_type_str, source.id,
            )
            return {"fetched": 0, "new": 0, "duplicates": 0}

        # Build scraper config from source metadata (stored as JSON in DB)
        source_config = {}
        if source.keyword:
            import json
            try:
                source_config = json.loads(source.keyword)
            except (json.JSONDecodeError, TypeError):
                # keyword is a plain string, use as search_query for twitter
                if source_type_str == "X":
                    source_config = {"search_query": source.keyword}

        scraper = scraper_cls(source_url=source.url, source_config=source_config)

        # ── Step 2: Fetch ────────────────────────────────────────────
        import os
        proxy_url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        client_kwargs = {"timeout": 30, "follow_redirects": True}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        async with httpx.AsyncClient(**client_kwargs) as client:
            entries = await scraper.fetch(client)
        fetched_count = len(entries)

        if not entries:
            logger.info("Source %s (%d): no entries fetched", source.name, source.id)
            _update_source_status(source, SourceStatus.ACTIVE)
            await db.flush()
            return {"fetched": 0, "new": 0, "duplicates": 0}

        # ── Step 3: Dedup via content_hash ───────────────────────────
        for entry in entries:
            text_for_hash = entry.get("title", "") + entry.get("url", "")
            entry["_content_hash"] = build_hash(text_for_hash)

        incoming_hashes = {e["_content_hash"] for e in entries}

        result = await db.execute(
            select(ContentItem.content_hash).where(
                ContentItem.content_hash.in_(incoming_hashes)
            )
        )
        existing_hashes = {row[0] for row in result.all()}

        # ── Step 4+5: Classify, tag and persist ──────────────────────
        new_items: list[ContentItem] = []
        category_counts: dict[str, int] = {}
        for entry in entries:
            ch = entry["_content_hash"]
            if ch in existing_hashes:
                duplicate_count += 1
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")

            # LLM-driven classification with keyword fallback
            class_result = await classify_async(title, summary, db)
            category = class_result["category"]
            tags = class_result["tags"]

            item = ContentItem(
                title=title,
                url=entry.get("url", ""),
                source_id=source.id,
                source_name=source.name,
                source_type=source_type_str,
                platform=source.platform,
                author=entry.get("author"),
                published_at=entry.get("published_at"),
                content_hash=ch,
                summary=summary or None,
                raw_content=entry.get("raw_content") or None,
                cover_url=entry.get("cover_url"),
                category=category,
                tags=tags if tags else None,
                status=ContentStatus.PENDING,
            )
            new_items.append(item)
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            new_count += 1
            existing_hashes.add(ch)

            # ── Persist platform-specific metrics (Reddit, etc.) ──
            _maybe_save_metrics(entry, item, db)

        # Batch flush: single round-trip for all items this source
        if new_items:
            for item in new_items:
                db.add(item)
            await db.flush()
            await _increment_category_counts(db, category_counts)

        # ── Step 6: Update source ────────────────────────────────────
        _update_source_status(source, SourceStatus.ACTIVE)
        await db.flush()

        logger.info(
            "Source %s (%d): fetched=%d, new=%d, dupes=%d",
            source.name, source.id, fetched_count, new_count, duplicate_count,
        )

    except Exception as exc:
        logger.exception("Error ingesting source %s (%d)", source.name, source.id)
        source.status = SourceStatus.ERROR
        source.sync_error = str(exc)[:500]
        source.updated_at = datetime.utcnow()
        await db.flush()

    return {"fetched": fetched_count, "new": new_count, "duplicates": duplicate_count}


def _update_source_status(source: Source, status: SourceStatus) -> None:
    """Set source sync metadata."""
    source.last_sync_at = datetime.utcnow()
    source.status = status
    source.sync_error = None
    source.updated_at = datetime.utcnow()


async def _increment_category_counts(db: AsyncSession, counts: dict[str, int]) -> None:
    """
    Batch-increment category content_count in the current transaction.

    Do not spawn background tasks with the request/session object; SQLAlchemy
    sessions are not safe for concurrent use and SQLite has a single writer.
    One UPDATE per unique category = minimal DB round-trips.
    """
    if not counts:
        return

    for cat_name, count in counts.items():
        await db.execute(
            text("UPDATE categories SET content_count = content_count + :n WHERE name = :name"),
            {"n": count, "name": cat_name},
        )


def _maybe_save_metrics(entry: dict, item: ContentItem, db: AsyncSession) -> None:
    """Extract platform-specific metrics (e.g. _reddit_meta, _zhihu_meta) and persist as ContentMetrics."""
    from app.models.metrics import ContentMetrics

    # ── Reddit metrics ──
    reddit_meta = entry.get("_reddit_meta")
    if reddit_meta:
        score = reddit_meta.get("score", 0)
        num_comments = reddit_meta.get("num_comments", 0)
        subscribers = reddit_meta.get("subreddit_subscribers", 0)

        engagement_rate = 0.0
        if subscribers > 0:
            engagement_rate = round((score + num_comments) / subscribers * 100, 4)

        explosion_ratio = 0.0
        if subscribers > 0:
            explosion_ratio = round(score / subscribers * 1000, 4)

        metrics = ContentMetrics(
            content=item,
            likes=score,
            comments=num_comments,
            shares=0,
            favorites=0,
            followers_count=subscribers,
            engagement_rate=engagement_rate,
            explosion_ratio=explosion_ratio,
        )
        db.add(metrics)
        return

    # ── Zhihu metrics ──
    zhihu_meta = entry.get("_zhihu_meta")
    if zhihu_meta:
        hot_score_raw = zhihu_meta.get("hot_score", 0)
        rank_raw = zhihu_meta.get("rank", 0)
        try:
            hot_score = int(float(str(hot_score_raw).replace("_", "")))
        except (ValueError, TypeError):
            hot_score = 0
        try:
            rank = int(float(str(rank_raw).replace("_", "")))
        except (ValueError, TypeError):
            rank = 0

        # For Zhihu hot list, hot_score is the primary engagement metric
        # Use a simple explosion_ratio based on rank (lower rank = higher)
        explosion_ratio = 0.0
        if rank > 0:
            explosion_ratio = round(1000.0 / rank, 4)

        metrics = ContentMetrics(
            content=item,
            likes=hot_score,
            comments=0,
            shares=0,
            favorites=0,
            followers_count=0,
            engagement_rate=round(float(hot_score) / 10000, 4) if hot_score > 0 else 0.0,
            explosion_ratio=explosion_ratio,
        )
        db.add(metrics)
        return

    # ── Douyin Hot metrics ──
    douyin_meta = entry.get("_douyin_hot_meta")
    if douyin_meta:
        hot_score = douyin_meta.get("hot_score", 0)
        rank = douyin_meta.get("rank", 0)

        explosion_ratio = 0.0
        if rank > 0:
            explosion_ratio = round(1000.0 / rank, 4)

        metrics = ContentMetrics(
            content=item,
            likes=hot_score,
            comments=0,
            shares=0,
            favorites=0,
            followers_count=0,
            engagement_rate=round(float(hot_score) / 10000, 4) if hot_score > 0 else 0.0,
            explosion_ratio=explosion_ratio,
        )
        db.add(metrics)
        return

    # ── Twitter RSS metrics ──
    twitter_rss_meta = entry.get("_twitter_rss_meta")
    if twitter_rss_meta:
        # Basic metrics from xgo.ing RSS — limited data available
        metrics = ContentMetrics(
            content=item,
            likes=0,
            comments=0,
            shares=0,
            favorites=0,
            followers_count=0,
            engagement_rate=0.0,
            explosion_ratio=0.0,
        )
        db.add(metrics)
        return
