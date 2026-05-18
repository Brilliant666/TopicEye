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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, SourceType, SourceStatus
from app.models.content import ContentItem, ContentStatus
from app.services.dedup import build_hash
from app.services.classifier import classify, extract_tags
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
        for entry in entries:
            ch = entry["_content_hash"]
            if ch in existing_hashes:
                duplicate_count += 1
                continue

            title = entry.get("title", "")
            summary = entry.get("summary", "")
            classify_text = f"{title} {summary}"

            category = classify(classify_text)
            tags = extract_tags(classify_text, max_tags=5)

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
            db.add(item)
            new_count += 1
            existing_hashes.add(ch)

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
