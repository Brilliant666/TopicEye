"""Zero-model refresh and saved-data read path for Rardar Hotspot News."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import unescape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentStatus
from app.models.source import Source, SourceStatus, SourceType
from app.repositories.rardar_hotspot_news_repo import RardarHotspotNewsRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.rardar_hotspot_news import (
    HotspotNewsItem,
    HotspotNewsRefreshResult,
    HotspotNewsRefreshSourceResult,
    HotspotNewsResponse,
    HotspotNewsSource,
)
from app.services._error_redaction import redact_source_sync_error
from app.services.content_summary import clean_content_summary
from app.services.scraper_http import build_scraper_client_kwargs
from app.services.scrapers.rss import RSSScraper
from app.utils.url_safety import ensure_public_hostname, hostname_is_blocked

logger = logging.getLogger(__name__)

HOTSPOT_NEWS_PLATFORM = "rardar_hotspot_news"
HOTSPOT_NEWS_CATEGORY = "技术资讯/资讯"
HOTSPOT_NEWS_MARKER_VERSION = 1
HOTSPOT_NEWS_STALE_AFTER = timedelta(hours=24)
HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE = 40
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class HotspotNewsSourceDefinition:
    key: str
    name: str
    feed_url: str
    homepage_url: str


# Source count is intentionally an MVP configuration choice, not a permanent
# coverage claim or product ranking contract.
HOTSPOT_NEWS_SOURCES: tuple[HotspotNewsSourceDefinition, ...] = (
    HotspotNewsSourceDefinition(
        key="github-changelog",
        name="GitHub Changelog",
        feed_url="https://github.blog/changelog/feed/",
        homepage_url="https://github.blog/changelog/",
    ),
    HotspotNewsSourceDefinition(
        key="hugging-face-blog",
        name="Hugging Face Blog",
        feed_url="https://huggingface.co/blog/feed.xml",
        homepage_url="https://huggingface.co/blog",
    ),
    HotspotNewsSourceDefinition(
        key="openai-news",
        name="OpenAI News",
        feed_url="https://openai.com/news/rss.xml",
        homepage_url="https://openai.com/news/",
    ),
)


@dataclass(frozen=True)
class _FeedFetchResult:
    entries: list[dict[str, Any]]
    etag: str | None
    last_modified: str | None
    not_modified: bool


class _SourceFetchError(RuntimeError):
    pass


def normalize_news_url(value: str) -> str:
    """Return a safe, stable original URL with tracking noise removed."""
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if (
        scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or hostname_is_blocked(parts.hostname)
    ):
        raise ValueError("news_item_url_invalid")

    host = parts.hostname.rstrip(".").lower()
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("news_item_url_invalid") from exc
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = host if port is None or default_port else f"{host}:{port}"
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
        ],
        doseq=True,
    )
    normalized = urlunsplit((scheme, netloc, parts.path or "/", query, ""))
    if len(normalized) > 1024:
        raise ValueError("news_item_url_too_long")
    return normalized


def _aware_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _bounded_text(value: str | None, *, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    decoded = unescape(value).strip()
    cleaned = clean_content_summary(decoded) if "<" in decoded and ">" in decoded else " ".join(decoded.split())
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _marker(source_key: str, updated_at: datetime | None, feed_tags: list[str]) -> dict[str, Any]:
    return {
        "rardarHotspotNews": {
            "version": HOTSPOT_NEWS_MARKER_VERSION,
            "sourceKey": source_key,
            "updatedAt": _aware_utc(updated_at).isoformat() if updated_at else None,
            "feedTags": [str(tag).strip()[:80] for tag in feed_tags if str(tag).strip()][:8],
        }
    }


def _marker_updated_at(item: ContentItem) -> datetime | None:
    tags = item.tags if isinstance(item.tags, dict) else {}
    marker = tags.get("rardarHotspotNews") if isinstance(tags, dict) else None
    raw = marker.get("updatedAt") if isinstance(marker, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed)


async def _fetch_feed(source: Source) -> _FeedFetchResult:
    await ensure_public_hostname(source.url)
    scraper = RSSScraper(source.url, {"preserve_feed_timestamps": True})
    kwargs = build_scraper_client_kwargs(
        source.url,
        etag=source.etag,
        last_modified=source.last_modified,
    )
    async with httpx.AsyncClient(**kwargs) as client:
        entries = await scraper.fetch(client)
    if scraper.fetch_degraded:
        raise _SourceFetchError("feed_fetch_retries_exhausted")
    content_type = str(getattr(scraper, "_latest_content_type", "") or "").lower()
    if "text/html" in content_type:
        raise _SourceFetchError("feed_returned_html")
    return _FeedFetchResult(
        entries=entries,
        etag=getattr(scraper, "_latest_etag", None),
        last_modified=getattr(scraper, "_latest_last_modified", None),
        not_modified=bool(getattr(scraper, "not_modified", False)),
    )


async def _ensure_managed_source(
    db: AsyncSession,
    repository: RardarHotspotNewsRepository,
    definition: HotspotNewsSourceDefinition,
    sort_order: int,
) -> Source:
    source = await repository.get_source(platform=HOTSPOT_NEWS_PLATFORM, feed_url=definition.feed_url)
    if source is None:
        source = Source(
            owner_user_id=None,
            scope="system",
            name=definition.name,
            source_type=SourceType.RSS,
            url=definition.feed_url,
            keyword=json.dumps(
                {"managedBy": HOTSPOT_NEWS_PLATFORM, "sourceKey": definition.key},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            platform=HOTSPOT_NEWS_PLATFORM,
            category=HOTSPOT_NEWS_CATEGORY,
            sort_order=sort_order,
            fetch_interval_minutes=720,
            status=SourceStatus.ACTIVE,
            enabled=True,
            hidden=True,
        )
        db.add(source)
        await db.flush()
    else:
        # Only the dedicated hidden system row is adapted; user subscriptions
        # with the same URL remain untouched and never enter this page.
        source.name = definition.name
        source.category = HOTSPOT_NEWS_CATEGORY
        source.sort_order = sort_order
        source.enabled = True
        source.hidden = True
    return source


async def _persist_entries(
    db: AsyncSession,
    repository: RardarHotspotNewsRepository,
    source: Source,
    definition: HotspotNewsSourceDefinition,
    entries: list[dict[str, Any]],
    fetched_at: datetime,
) -> tuple[int, int]:
    prepared: dict[str, dict[str, Any]] = {}
    in_batch_duplicates = 0
    newest_entries = sorted(
        entries,
        key=lambda entry: _aware_utc(entry.get("published_at"))
        or _aware_utc(entry.get("updated_at"))
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )[:HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE]
    for entry in newest_entries:
        title = _bounded_text(entry.get("title"), limit=500)
        if not title:
            continue
        try:
            url = normalize_news_url(entry.get("url", ""))
        except ValueError:
            continue
        # URL identity is authoritative.  Similar titles are deliberately not
        # merged because they may describe distinct events.
        if url in prepared:
            in_batch_duplicates += 1
            continue
        prepared[url] = {
            "title": title,
            "summary": _bounded_text(entry.get("summary"), limit=1200),
            "author": _bounded_text(entry.get("author"), limit=255),
            "published_at": _aware_utc(entry.get("published_at")),
            "updated_at": _aware_utc(entry.get("updated_at")),
            "feed_tags": entry.get("tags") if isinstance(entry.get("tags"), list) else [],
        }

    managed = await repository.list_sources(
        platform=HOTSPOT_NEWS_PLATFORM,
        feed_urls=[item.feed_url for item in HOTSPOT_NEWS_SOURCES],
    )
    existing = await repository.list_items_by_urls(
        source_ids=[item.id for item in managed],
        urls=list(prepared),
    )
    existing_by_url = {item.url: item for item in existing}
    created = 0
    duplicates = in_batch_duplicates
    for url, payload in prepared.items():
        current = existing_by_url.get(url)
        if current is not None:
            duplicates += 1
            # A repeated item may carry an updated feed description.  Update
            # only the row already attributed to this source; cross-source
            # duplicates retain their original factual attribution.
            if current.source_id == source.id:
                current.title = payload["title"]
                current.summary = payload["summary"] or current.summary
                current.author = payload["author"] or current.author
                current.published_at = current.published_at or payload["published_at"]
                current.tags = _marker(definition.key, payload["updated_at"], payload["feed_tags"])
            continue
        db.add(
            ContentItem(
                title=payload["title"],
                url=url,
                source_id=source.id,
                source_name=definition.name,
                source_type=SourceType.RSS.value,
                platform=HOTSPOT_NEWS_PLATFORM,
                owner_user_id=None,
                author=payload["author"],
                published_at=payload["published_at"],
                crawled_at=fetched_at,
                content_hash=hashlib.sha256(url.encode("utf-8")).hexdigest(),
                summary=payload["summary"],
                raw_content=None,
                category="技术资讯",
                content_type="资讯",
                tags=_marker(definition.key, payload["updated_at"], payload["feed_tags"]),
                status=ContentStatus.PENDING,
                skip_analysis=True,
                skip_reason="rardar_hotspot_news_zero_model_ingestion",
            )
        )
        created += 1
    await db.flush()
    return created, duplicates


async def refresh_hotspot_news(
    db: AsyncSession,
    *,
    definitions: tuple[HotspotNewsSourceDefinition, ...] = HOTSPOT_NEWS_SOURCES,
) -> HotspotNewsRefreshResult:
    """Refresh selected public feeds sequentially without any model calls."""
    started_at = datetime.now(UTC)
    repository = RardarHotspotNewsRepository(db)
    for index, definition in enumerate(definitions):
        await _ensure_managed_source(db, repository, definition, index)
    await db.commit()

    results: list[HotspotNewsRefreshSourceResult] = []
    for definition in definitions:
        source = await repository.get_source(platform=HOTSPOT_NEWS_PLATFORM, feed_url=definition.feed_url)
        if source is None:
            raise RuntimeError("managed_hotspot_source_missing")
        claimed = await SourceRepository(db).claim_sync(source.id, lease_seconds=300)
        if claimed is None:
            retained = await repository.count_items(source_id=source.id)
            results.append(
                HotspotNewsRefreshSourceResult(
                    key=definition.key,
                    status="busy",
                    fetched=0,
                    created=0,
                    duplicates=0,
                    retained=retained,
                )
            )
            continue
        await db.commit()

        try:
            fetched_at = datetime.now(UTC)
            fetched = await _fetch_feed(claimed)
            if fetched.etag is not None:
                claimed.etag = fetched.etag
            if fetched.last_modified is not None:
                claimed.last_modified = fetched.last_modified
            if fetched.not_modified:
                created = duplicates = 0
                state = "not_modified"
            else:
                created, duplicates = await _persist_entries(
                    db,
                    repository,
                    claimed,
                    definition,
                    fetched.entries,
                    fetched_at,
                )
                state = "refreshed"
            claimed.status = SourceStatus.ACTIVE
            claimed.sync_error = None
            claimed.last_sync_at = datetime.now(UTC)
            claimed.updated_at = claimed.last_sync_at
            await db.commit()
            retained = await repository.count_items(source_id=claimed.id)
            results.append(
                HotspotNewsRefreshSourceResult(
                    key=definition.key,
                    status=state,
                    fetched=len(fetched.entries),
                    created=created,
                    duplicates=duplicates,
                    retained=retained,
                )
            )
        except Exception as exc:
            await db.rollback()
            safe_error = redact_source_sync_error(str(exc) or exc.__class__.__name__)[:500]
            logger.warning("Rardar Hotspot News source %s failed: %s", definition.key, safe_error)
            failed = await repository.get_source(platform=HOTSPOT_NEWS_PLATFORM, feed_url=definition.feed_url)
            if failed is not None:
                failed.status = SourceStatus.ERROR
                failed.sync_error = safe_error
                failed.last_sync_at = datetime.now(UTC)
                failed.updated_at = failed.last_sync_at
                await db.commit()
                retained = await repository.count_items(source_id=failed.id)
            else:
                retained = 0
            results.append(
                HotspotNewsRefreshSourceResult(
                    key=definition.key,
                    status="failed",
                    fetched=0,
                    created=0,
                    duplicates=0,
                    retained=retained,
                    errorCode="source_sync_failed",
                )
            )

    failed_count = sum(item.status == "failed" for item in results)
    busy_count = sum(item.status == "busy" for item in results)
    status = "degraded" if failed_count else "busy" if busy_count else "completed"
    return HotspotNewsRefreshResult(
        status=status,
        startedAt=started_at,
        completedAt=datetime.now(UTC),
        sources=results,
    )


def _definition_by_url() -> dict[str, HotspotNewsSourceDefinition]:
    return {item.feed_url: item for item in HOTSPOT_NEWS_SOURCES}


async def load_hotspot_news(
    db: AsyncSession,
    *,
    selected_source: str | None = None,
    limit: int = 60,
) -> tuple[HotspotNewsResponse, str]:
    """Load saved news only; this function never fetches or invokes a model."""
    definitions = _definition_by_url()
    key_to_definition = {item.key: item for item in HOTSPOT_NEWS_SOURCES}
    if selected_source is not None and selected_source not in key_to_definition:
        raise ValueError("hotspot_news_source_unknown")

    repository = RardarHotspotNewsRepository(db)
    sources = await repository.list_sources(
        platform=HOTSPOT_NEWS_PLATFORM,
        feed_urls=list(definitions),
    )
    source_ids = [source.id for source in sources]
    all_items = await repository.list_items(source_ids=source_ids)
    source_by_id = {source.id: source for source in sources}
    now = datetime.now(UTC)

    item_counts = {source.id: 0 for source in sources}
    parsed_items: list[tuple[datetime, HotspotNewsItem]] = []
    for item in all_items:
        source = source_by_id.get(item.source_id)
        if source is None:
            continue
        definition = definitions[source.url]
        item_counts[source.id] += 1
        if selected_source is not None and definition.key != selected_source:
            continue
        published_at = _aware_utc(item.published_at)
        updated_at = _marker_updated_at(item)
        fetched_at = _aware_utc(item.crawled_at)
        if fetched_at is None:
            continue
        dto = HotspotNewsItem(
            id=item.id,
            title=item.title,
            summary=item.summary,
            sourceKey=definition.key,
            sourceName=definition.name,
            url=item.url,
            publishedAt=published_at,
            updatedAt=updated_at,
            fetchedAt=fetched_at,
        )
        parsed_items.append((published_at or updated_at or fetched_at, dto))
    parsed_items.sort(key=lambda row: (row[0], row[1].id), reverse=True)
    items = [row[1] for row in parsed_items[:limit]]

    source_dtos: list[HotspotNewsSource] = []
    for definition in HOTSPOT_NEWS_SOURCES:
        source = next((row for row in sources if row.url == definition.feed_url), None)
        if source is None:
            state = "not_synced"
            last_sync_at = None
            item_count = 0
            error_code = None
        else:
            last_sync_at = _aware_utc(source.last_sync_at)
            item_count = item_counts[source.id]
            if source.status == SourceStatus.ERROR:
                state = "failed"
                error_code = "source_sync_failed"
            elif last_sync_at is None:
                state = "not_synced"
                error_code = None
            elif now - last_sync_at > HOTSPOT_NEWS_STALE_AFTER:
                state = "stale"
                error_code = None
            else:
                state = "healthy"
                error_code = None
        source_dtos.append(
            HotspotNewsSource(
                key=definition.key,
                name=definition.name,
                homepageUrl=definition.homepage_url,
                status=state,
                lastSyncAt=last_sync_at,
                itemCount=item_count,
                errorCode=error_code,
            )
        )

    synced_values = [source.lastSyncAt for source in source_dtos if source.lastSyncAt is not None]
    synced_at = max(synced_values, default=None)
    source_states = {source.status for source in source_dtos}
    if not sources:
        status = "not_synced"
    elif "failed" in source_states:
        status = "degraded"
    elif items and source_states <= {"stale", "not_synced"}:
        status = "stale"
    elif items or "healthy" in source_states:
        status = "ready"
    else:
        status = "not_synced"
    response = HotspotNewsResponse(
        status=status,
        syncedAt=synced_at,
        itemCount=len(items),
        selectedSource=selected_source,
        sources=source_dtos,
        items=items,
    )
    etag_payload = response.model_dump(mode="json")
    etag = hashlib.sha256(json.dumps(etag_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return response, f'"{etag}"'
