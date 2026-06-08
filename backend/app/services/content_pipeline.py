"""
Content ingestion pipeline.

Orchestrates fetching, deduplication, classification, and storage for a
single source. Uses the scraper registry to dispatch by SourceType.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, SourceType, SourceStatus
from app.models.content import ContentItem, ContentStatus
from app.core.config import settings
from app.services.dedup import build_hash
from app.services.classifier import classify, extract_tags, classify_async
from app.services.content_read_cache import invalidate_content_read_caches
from app.services.scrapers import get_scraper_cls

logger = logging.getLogger(__name__)

_SENSITIVE_ENV_SUFFIXES = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
_SENSITIVE_PAIR_RE = re.compile(
    r"(?i)([\"']?\b(?:access[_-]?token|api[_-]?key|apikey|auth[_-]?token|"
    r"client[_-]?secret|secret|password|passwd|pwd|token|key)\b[\"']?\s*[:=]\s*[\"']?)"
    r"([^&\s,;\"'<>}]+)([\"']?)"
)
_AUTH_HEADER_RE = re.compile(
    r"(?i)([\"']?\bauthorization\b[\"']?\s*[:=]\s*[\"']?)(?!Bearer\s+\*\*\*)"
    r"([^,\s;\"'<>}]+)([\"']?)"
)
_BEARER_RE = re.compile(r"\bBearer\s+[^\s,;\"'<>]+", re.IGNORECASE)


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
    try:
        return await asyncio.wait_for(
            _ingest_from_source_inner(source, db),
            timeout=settings.SOURCE_SYNC_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        message = f"Source sync timed out after {settings.SOURCE_SYNC_TIMEOUT_SECONDS}s"
        logger.warning("Source %s (%d): %s", source.name, source.id, message)
        _update_source_error(source, message)
        await db.flush()
        return {"fetched": 0, "new": 0, "duplicates": 0}


async def _ingest_from_source_inner(source: Source, db: AsyncSession) -> dict[str, int]:
    fetched_count = 0
    new_count = 0
    duplicate_count = 0
    started_at = time.perf_counter()

    try:
        # ── Step 1: Resolve scraper ──────────────────────────────────
        source_type = source.source_type
        source_type_str = source_type.value if source_type else "RSS"

        # Skip ZHIHU: its hot topics are now served exclusively via trending radar
        # and should not be duplicated into the content feed.
        if source_type == SourceType.ZHIHU or source_type_str.upper() == "ZHIHU":
            logger.info("Source '%s' (ZHIHU): skipped — topics served via trending radar", source.name)
            _update_source_status(source, SourceStatus.ACTIVE)
            await db.flush()
            return {"fetched": 0, "new": 0, "duplicates": 0}

        scraper_cls = get_scraper_cls(source_type_str)

        if scraper_cls is None:
            logger.warning(
                "No scraper registered for source_type '%s' (source %d)",
                source_type_str, source.id,
            )
            _update_source_error(source, f"No scraper registered for source_type '{source_type_str}'")
            await db.flush()
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
        client_kwargs = _build_http_client_kwargs(source.url)
        fetch_started_at = time.perf_counter()
        async with httpx.AsyncClient(**client_kwargs) as client:
            entries = await scraper.fetch(client)
        fetched_count = len(entries)
        fetch_elapsed_ms = int((time.perf_counter() - fetch_started_at) * 1000)

        if not entries:
            logger.info(
                "Source %s (%d): no entries fetched in %dms",
                source.name, source.id, fetch_elapsed_ms,
            )
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
        category_names = await _get_active_category_names(db)
        new_items: list[ContentItem] = []
        category_counts: dict[str, int] = {}
        classify_elapsed_ms = 0
        for entry in entries:
            ch = entry["_content_hash"]
            if ch in existing_hashes:
                duplicate_count += 1
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")

            # LLM-driven classification with keyword fallback
            classify_started_at = time.perf_counter()
            class_result = await classify_async(title, summary, db, category_names=category_names)
            classify_elapsed_ms += int((time.perf_counter() - classify_started_at) * 1000)
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
        db_elapsed_ms = 0
        if new_items:
            for item in new_items:
                db.add(item)
            db_started_at = time.perf_counter()
            await db.flush()
            await _increment_category_counts(db, category_counts)
            invalidate_content_read_caches()
            db_elapsed_ms = int((time.perf_counter() - db_started_at) * 1000)

        # ── Step 6: Update source ────────────────────────────────────
        _update_source_status(source, SourceStatus.ACTIVE)
        await db.flush()

        logger.info(
            "Source %s (%d): fetched=%d, new=%d, dupes=%d, fetch=%dms, classify=%dms, db=%dms, total=%dms",
            source.name, source.id, fetched_count, new_count, duplicate_count,
            fetch_elapsed_ms, classify_elapsed_ms, db_elapsed_ms,
            int((time.perf_counter() - started_at) * 1000),
        )

    except Exception as exc:
        error_message = str(exc) or exc.__class__.__name__
        safe_message = redact_source_sync_error(error_message)
        logger.error(
            "Error ingesting source %s (%d): %s",
            source.name,
            source.id,
            safe_message,
        )
        _update_source_error(source, safe_message)
        await db.flush()

    return {"fetched": fetched_count, "new": new_count, "duplicates": duplicate_count}


def _update_source_status(source: Source, status: SourceStatus) -> None:
    """Set source sync metadata."""
    source.last_sync_at = datetime.utcnow()
    source.status = status
    source.sync_error = None
    source.updated_at = datetime.utcnow()


def _update_source_error(source: Source, message: str) -> None:
    """Record a failed sync attempt without causing immediate retry loops."""
    source.last_sync_at = datetime.utcnow()
    source.status = SourceStatus.ERROR
    source.sync_error = redact_source_sync_error(message)[:500]
    source.updated_at = datetime.utcnow()


def redact_source_sync_error(message: str) -> str:
    """Remove source credentials before persisting sync errors."""
    redacted = str(message or "")

    for secret in _source_error_secrets():
        redacted = redacted.replace(secret, "***")

    redacted = _BEARER_RE.sub("Bearer ***", redacted)
    redacted = _AUTH_HEADER_RE.sub(r"\1***\3", redacted)
    redacted = _SENSITIVE_PAIR_RE.sub(r"\1***\3", redacted)
    return redacted.strip() or "信源同步失败"


def _source_error_secrets() -> list[str]:
    secrets: set[str] = set()
    for name, value in os.environ.items():
        if not value or len(value.strip()) < 8:
            continue
        upper_name = name.upper()
        if upper_name.endswith(_SENSITIVE_ENV_SUFFIXES) or upper_name in {"HTTPS_PROXY", "HTTP_PROXY"}:
            stripped = value.strip()
            secrets.add(stripped)
            secrets.add(quote(stripped, safe=""))
    return sorted(secrets, key=len, reverse=True)


def _build_http_client_kwargs(source_url: str) -> dict[str, Any]:
    client_kwargs: dict[str, Any] = {"timeout": 30, "follow_redirects": True, "trust_env": False}
    proxy_url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy_url and not _is_loopback_url(source_url):
        client_kwargs["proxy"] = proxy_url
    return client_kwargs


def _is_loopback_url(source_url: str) -> bool:
    host = (urlparse(source_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.startswith("127.")


async def _get_active_category_names(db: AsyncSession) -> list[str]:
    from app.repositories.category_repo import CategoryRepository

    names = await CategoryRepository(db).get_active_names()
    return names or classify_default_categories()


def classify_default_categories() -> list[str]:
    from app.services.classifier import CATEGORIES

    return CATEGORIES.copy()


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
