"""Zero-model refresh and saved-data read path for Rardar Hotspot News."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import unescape
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentStatus
from app.models.source import Source, SourceStatus, SourceType
from app.repositories.rardar_hotspot_news_repo import RardarHotspotNewsRepository
from app.repositories.source_repo import SourceRepository
from app.schemas.rardar_hotspot_news import (
    HotspotNewsDiscoveryChannel,
    HotspotNewsItem,
    HotspotNewsQuickRead,
    HotspotNewsRefreshResult,
    HotspotNewsRefreshSourceResult,
    HotspotNewsResponse,
    HotspotNewsSource,
    HotspotNewsTopic,
)
from app.services._error_redaction import redact_source_sync_error
from app.services.content_summary import clean_content_summary
from app.services.rardar_news_operation_lock import news_writer
from app.services.scraper_http import build_scraper_client_kwargs
from app.services.scrapers.rss import RSSScraper
from app.services.trending_scrapers._hackernews import HackerNewsTrending
from app.utils.url_safety import ensure_public_hostname, hostname_is_blocked

logger = logging.getLogger(__name__)

HOTSPOT_NEWS_PLATFORM = "rardar_hotspot_news"
HOTSPOT_NEWS_CATEGORY = "技术资讯/资讯"
HOTSPOT_NEWS_MARKER_VERSION = 2
HOTSPOT_NEWS_STALE_AFTER = timedelta(hours=24)
HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE = 40
HOTSPOT_NEWS_DEFAULT_PAGE_SIZE = 18
HOTSPOT_NEWS_BALANCE_WINDOW_HOURS = 24
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}

SourceKind = Literal["official", "media", "community", "aggregate"]
FetchKind = Literal["rss", "hackernews"]
ContentType = Literal["official_update", "report", "research", "community_discussion", "uncategorized"]


@dataclass(frozen=True)
class HotspotNewsSourceDefinition:
    key: str
    name: str
    feed_url: str
    homepage_url: str
    fetch_kind: FetchKind = "rss"
    source_kind: SourceKind = "official"
    language: Literal["zh", "en", "unknown"] = "en"
    default_topic: str | None = None
    default_content_type: ContentType = "official_update"


# Direct publishers run before Hacker News so a duplicate article keeps its
# publisher facts while also recording HN as an additional discovery channel.
# The source count is an MVP scope choice, not a permanent product quota.
HOTSPOT_NEWS_SOURCES: tuple[HotspotNewsSourceDefinition, ...] = (
    HotspotNewsSourceDefinition(
        key="solidot",
        name="Solidot",
        feed_url="https://www.solidot.org/index.rss",
        homepage_url="https://www.solidot.org/",
        source_kind="media",
        language="zh",
        default_content_type="report",
    ),
    HotspotNewsSourceDefinition(
        key="ars-technica",
        name="Ars Technica",
        feed_url="https://feeds.arstechnica.com/arstechnica/index",
        homepage_url="https://arstechnica.com/",
        source_kind="media",
        default_content_type="report",
    ),
    HotspotNewsSourceDefinition(
        key="github-changelog",
        name="GitHub Changelog",
        feed_url="https://github.blog/changelog/feed/",
        homepage_url="https://github.blog/changelog/",
        default_topic="software-open-source",
    ),
    HotspotNewsSourceDefinition(
        key="cloudflare-blog",
        name="Cloudflare Blog",
        feed_url="https://blog.cloudflare.com/rss/",
        homepage_url="https://blog.cloudflare.com/",
    ),
    HotspotNewsSourceDefinition(
        key="openai-news",
        name="OpenAI News",
        feed_url="https://openai.com/news/rss.xml",
        homepage_url="https://openai.com/news/",
    ),
    HotspotNewsSourceDefinition(
        key="hugging-face-blog",
        name="Hugging Face Blog",
        feed_url="https://huggingface.co/blog/feed.xml",
        homepage_url="https://huggingface.co/blog",
    ),
    HotspotNewsSourceDefinition(
        key="hacker-news",
        name="Hacker News",
        feed_url="https://hacker-news.firebaseio.com/v0/topstories.json",
        homepage_url="https://news.ycombinator.com/",
        fetch_kind="hackernews",
        source_kind="community",
        default_content_type="community_discussion",
    ),
)

HOTSPOT_NEWS_TOPICS: tuple[tuple[str, str], ...] = (
    ("software-open-source", "软件与开源"),
    ("cloud-data", "云与数据"),
    ("security", "安全"),
    ("hardware-chips", "硬件与芯片"),
    ("science-research", "科研与太空"),
    ("ai", "人工智能"),
    ("industry-products", "产业与产品"),
    ("uncategorized", "未分类"),
)
_TOPIC_LABELS = dict(HOTSPOT_NEWS_TOPICS)
_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "security",
        re.compile(
            r"\b(?:security|vulnerabilit(?:y|ies)|malware|ransomware|exploit|breach|cve|cyberattack)\b|安全|漏洞|攻击|恶意软件|勒索",
            re.IGNORECASE,
        ),
    ),
    (
        "hardware-chips",
        re.compile(
            r"\b(?:chip|semiconductor|cpu|gpu|hardware|robot|robotics|processor|device|silicon)\b|芯片|半导体|硬件|处理器|机器人",
            re.IGNORECASE,
        ),
    ),
    (
        "science-research",
        re.compile(
            r"\b(?:science|research|space|rocket|nasa|physics|biology|climate|astronomy|orbit)\b|科学|研究|太空|火箭|物理|生物|气候|轨道",
            re.IGNORECASE,
        ),
    ),
    (
        "ai",
        re.compile(
            r"\b(?:ai|artificial intelligence|machine learning|llm|gpt|neural|foundation model)\b|人工智能|大模型|机器学习|神经网络",
            re.IGNORECASE,
        ),
    ),
    (
        "cloud-data",
        re.compile(
            r"\b(?:cloud|database|data center|storage|cache|kubernetes|serverless|cdn|network)\b|云计算|数据库|数据中心|存储|缓存|网络",
            re.IGNORECASE,
        ),
    ),
    (
        "software-open-source",
        re.compile(
            r"\b(?:open source|github|linux|compiler|programming language|software|developer|api|package|release)\b|开源|软件|开发者|编译器|编程语言|发布",
            re.IGNORECASE,
        ),
    ),
    (
        "industry-products",
        re.compile(
            r"\b(?:company|acquisition|funding|startup|product|launch|regulation|antitrust|apple|tesla)\b|产业|公司|收购|融资|创业|产品|监管",
            re.IGNORECASE,
        ),
    ),
)
_RESEARCH_PATTERN = re.compile(
    r"\b(?:research|paper|study|scientist|science|physics|biology|astronomy)\b|研究|论文|科学家|物理|生物|天文",
    re.IGNORECASE,
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
    if ":" in host:
        host = f"[{host}]"
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


def classify_news_topic(
    title: str,
    feed_tags: list[str],
    *,
    default_topic: str | None = None,
) -> str:
    """Assign one conservative display topic from title and publisher tags."""
    evidence = " ".join([title, *feed_tags])
    for topic, pattern in _TOPIC_PATTERNS:
        if pattern.search(evidence):
            return topic
    return default_topic if default_topic in _TOPIC_LABELS else "uncategorized"


def classify_news_content_type(
    title: str,
    feed_tags: list[str],
    definition: HotspotNewsSourceDefinition,
) -> ContentType:
    if definition.source_kind == "community":
        return "community_discussion"
    if _RESEARCH_PATTERN.search(" ".join([title, *feed_tags])):
        return "research"
    return definition.default_content_type


def _aware_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_marker_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware_utc(parsed)


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


def _safe_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


def _safe_rank(value: object) -> int | None:
    parsed = _safe_nonnegative_int(value)
    return parsed if parsed and parsed >= 1 else None


def _publisher_name_for_url(url: str) -> str:
    host = (urlsplit(url).hostname or "原始来源").lower().removeprefix("www.")
    known = {
        "github.com": "GitHub",
        "github.blog": "GitHub",
        "openai.com": "OpenAI",
        "arstechnica.com": "Ars Technica",
        "blog.cloudflare.com": "Cloudflare",
        "solidot.org": "Solidot",
        "news.ycombinator.com": "Hacker News",
    }
    return known.get(host, host)[:255]


def _channel_payload(
    definition: HotspotNewsSourceDefinition,
    fetched_at: datetime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    discussion_url = payload.get("discussion_url")
    if discussion_url:
        try:
            discussion_url = normalize_news_url(discussion_url)
        except ValueError:
            discussion_url = None
    discussion_at = _aware_utc(payload.get("discussion_at"))
    return {
        "key": definition.key,
        "name": definition.name,
        "kind": definition.source_kind,
        "observedAt": fetched_at.isoformat(),
        "discussionUrl": discussion_url,
        "discussionAt": discussion_at.isoformat() if discussion_at else None,
        "rank": _safe_rank(payload.get("rank")),
        "points": _safe_nonnegative_int(payload.get("points")),
        "comments": _safe_nonnegative_int(payload.get("comments")),
    }


def _item_marker(item: ContentItem) -> dict[str, Any]:
    tags = item.tags if isinstance(item.tags, dict) else {}
    marker = tags.get("rardarHotspotNews") if isinstance(tags, dict) else None
    return dict(marker) if isinstance(marker, dict) else {}


def _text_digest(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _quick_read_for_item(item: ContentItem) -> HotspotNewsQuickRead | None:
    """Expose a derived reading aid only while it matches the raw source facts."""
    tags = item.tags if isinstance(item.tags, dict) else {}
    marker = tags.get("rardarHotspotNewsQuickRead")
    if not isinstance(marker, dict):
        return None
    failure = tags.get("rardarHotspotNewsQuickReadFailure")
    if (
        isinstance(failure, dict)
        and isinstance(failure.get("inputIdentity"), str)
        and failure.get("inputIdentity") != marker.get("inputIdentity")
    ):
        return None
    if (
        marker.get("version") != 1
        or marker.get("sourceTitleSha256") != _text_digest(item.title)
        or marker.get("sourceSummarySha256") != _text_digest(item.summary)
    ):
        return None
    try:
        return HotspotNewsQuickRead.model_validate(
            {
                "state": marker.get("state"),
                "titleZh": marker.get("titleZh"),
                "summaryZh": marker.get("summaryZh"),
                "materialKind": marker.get("materialKind"),
                "generatedBy": "ai",
                "generatedAt": marker.get("generatedAt"),
            },
        )
    except Exception:
        return None


def _merge_channels(marker: dict[str, Any], channel: dict[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    existing = marker.get("discoveryChannels")
    if isinstance(existing, list):
        for candidate in existing:
            if isinstance(candidate, dict) and isinstance(candidate.get("key"), str):
                merged[candidate["key"]] = dict(candidate)
    elif isinstance(marker.get("sourceKey"), str):
        legacy_key = marker["sourceKey"]
        definition = next((row for row in HOTSPOT_NEWS_SOURCES if row.key == legacy_key), None)
        if definition is not None:
            merged[legacy_key] = {
                "key": legacy_key,
                "name": definition.name,
                "kind": definition.source_kind,
                "observedAt": channel["observedAt"],
                "discussionUrl": None,
                "discussionAt": None,
                "rank": None,
                "points": None,
                "comments": None,
            }
    merged[channel["key"]] = channel
    order = {definition.key: index for index, definition in enumerate(HOTSPOT_NEWS_SOURCES)}
    return sorted(merged.values(), key=lambda value: (order.get(str(value.get("key")), 999), str(value.get("key"))))


def _marker(
    *,
    item: ContentItem | None,
    definition: HotspotNewsSourceDefinition,
    fetched_at: datetime,
    payload: dict[str, Any],
) -> dict[str, Any]:
    existing = _item_marker(item) if item is not None else {}
    channel = _channel_payload(definition, fetched_at, payload)
    existing_topic = existing.get("topicKey")
    topic_key = payload["topic_key"]
    if existing_topic in _TOPIC_LABELS and existing_topic != "uncategorized":
        topic_key = existing_topic
    existing_content_type = existing.get("contentType")
    content_type = payload["content_type"]
    if existing_content_type in {
        "official_update",
        "report",
        "research",
        "community_discussion",
        "uncategorized",
    } and not (existing_content_type == "community_discussion" and definition.source_kind != "community"):
        content_type = existing_content_type
    existing_publisher = existing.get("publisherName")
    publisher_name = payload["publisher_name"]
    if isinstance(existing_publisher, str) and existing_publisher:
        publisher_name = existing_publisher
    source_key = existing.get("sourceKey") if isinstance(existing.get("sourceKey"), str) else definition.key
    updated_at = _aware_utc(payload.get("updated_at"))
    existing_updated = _parse_marker_time(existing.get("updatedAt"))
    times = [value for value in (updated_at, existing_updated) if value is not None]
    effective_updated = max(times) if times else None
    existing_feed_tags = existing.get("feedTags") if isinstance(existing.get("feedTags"), list) else []
    feed_tags = list(dict.fromkeys([*existing_feed_tags, *payload["feed_tags"]]))[:8]
    tags = dict(item.tags) if item is not None and isinstance(item.tags, dict) else {}
    tags["rardarHotspotNews"] = {
        "version": HOTSPOT_NEWS_MARKER_VERSION,
        "sourceKey": source_key,
        "updatedAt": effective_updated.isoformat() if effective_updated else None,
        "feedTags": feed_tags,
        "topicKey": topic_key,
        "contentType": content_type,
        "publisherName": publisher_name,
        "language": existing.get("language") or definition.language,
        "discoveryChannels": _merge_channels(existing, channel),
    }
    return tags


async def _fetch_rss_feed(source: Source) -> _FeedFetchResult:
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


async def _fetch_hacker_news(source: Source) -> _FeedFetchResult:
    await ensure_public_hostname(source.url)
    scraper = HackerNewsTrending()
    scraper.conditional_etag = source.etag
    scraper.conditional_last_modified = source.last_modified
    kwargs = build_scraper_client_kwargs(source.url, timeout=25)
    kwargs["headers"]["Accept"] = "application/json"
    async with httpx.AsyncClient(**kwargs) as client:
        stories = await scraper.fetch(client)
    if getattr(scraper, "fetch_degraded", False):
        raise _SourceFetchError("community_fetch_failed")
    if getattr(scraper, "not_modified", False):
        return _FeedFetchResult(
            entries=[],
            etag=getattr(scraper, "_latest_etag", None),
            last_modified=getattr(scraper, "_latest_last_modified", None),
            not_modified=True,
        )
    entries: list[dict[str, Any]] = []
    for story in stories:
        extra = story.get("extra") if isinstance(story.get("extra"), dict) else {}
        unix_time = _safe_nonnegative_int(extra.get("time"))
        discussion_at = datetime.fromtimestamp(unix_time, tz=UTC) if unix_time else None
        entries.append(
            {
                "title": story.get("title", ""),
                "url": story.get("url", ""),
                "author": extra.get("by", ""),
                "summary": None,
                "published_at": None,
                "updated_at": None,
                "discussion_at": discussion_at,
                "discussion_url": extra.get("hn_link"),
                "rank": story.get("rank"),
                "points": story.get("hot_value"),
                "comments": extra.get("descendants"),
                "tags": [],
            }
        )
    if not entries:
        raise _SourceFetchError("community_feed_empty")
    return _FeedFetchResult(
        entries=entries,
        etag=getattr(scraper, "_latest_etag", None),
        last_modified=getattr(scraper, "_latest_last_modified", None),
        not_modified=False,
    )


async def _fetch_source(source: Source, definition: HotspotNewsSourceDefinition) -> _FeedFetchResult:
    return await _fetch_hacker_news(source) if definition.fetch_kind == "hackernews" else await _fetch_rss_feed(source)


async def _ensure_managed_source(
    db: AsyncSession,
    repository: RardarHotspotNewsRepository,
    definition: HotspotNewsSourceDefinition,
    sort_order: int,
) -> Source:
    source = await repository.get_source(platform=HOTSPOT_NEWS_PLATFORM, feed_url=definition.feed_url)
    expected_type = SourceType.API if definition.fetch_kind == "hackernews" else SourceType.RSS
    if source is None:
        source = Source(
            owner_user_id=None,
            scope="system",
            name=definition.name,
            source_type=expected_type,
            url=definition.feed_url,
            keyword=json.dumps(
                {
                    "managedBy": HOTSPOT_NEWS_PLATFORM,
                    "sourceKey": definition.key,
                    "sourceKind": definition.source_kind,
                },
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
        source.name = definition.name
        source.source_type = expected_type
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
        or _aware_utc(entry.get("discussion_at"))
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
        if url in prepared:
            in_batch_duplicates += 1
            continue
        feed_tags = [str(tag).strip()[:80] for tag in entry.get("tags", []) if str(tag).strip()][:8]
        prepared[url] = {
            "title": title,
            "summary": _bounded_text(entry.get("summary"), limit=1200),
            "author": _bounded_text(entry.get("author"), limit=255),
            "published_at": _aware_utc(entry.get("published_at")),
            "updated_at": _aware_utc(entry.get("updated_at")),
            "discussion_at": _aware_utc(entry.get("discussion_at")),
            "discussion_url": entry.get("discussion_url"),
            "rank": entry.get("rank"),
            "points": entry.get("points"),
            "comments": entry.get("comments"),
            "feed_tags": feed_tags,
            "topic_key": classify_news_topic(title, feed_tags, default_topic=definition.default_topic),
            "content_type": classify_news_content_type(title, feed_tags, definition),
            "publisher_name": (
                _publisher_name_for_url(url) if definition.source_kind == "community" else definition.name
            ),
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
            if current.source_id == source.id:
                current.title = payload["title"]
                current.summary = payload["summary"] or current.summary
                current.author = payload["author"] or current.author
            else:
                current.summary = current.summary or payload["summary"]
                current.author = current.author or payload["author"]
            current.published_at = current.published_at or payload["published_at"]
            current.tags = _marker(
                item=current,
                definition=definition,
                fetched_at=fetched_at,
                payload=payload,
            )
            continue
        db.add(
            ContentItem(
                title=payload["title"],
                url=url,
                source_id=source.id,
                source_name=definition.name,
                source_type=source.source_type.value
                if isinstance(source.source_type, SourceType)
                else str(source.source_type),
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
                tags=_marker(
                    item=None,
                    definition=definition,
                    fetched_at=fetched_at,
                    payload=payload,
                ),
                language=definition.language,
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
    with news_writer():
        return await _refresh_hotspot_news(db, definitions=definitions)


async def _refresh_hotspot_news(
    db: AsyncSession,
    *,
    definitions: tuple[HotspotNewsSourceDefinition, ...],
) -> HotspotNewsRefreshResult:
    """Refresh selected public sources sequentially without any model calls."""
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
            fetched = await _fetch_source(claimed, definition)
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


def _channel_from_marker(
    value: object,
    *,
    fallback_observed_at: datetime,
) -> HotspotNewsDiscoveryChannel | None:
    if not isinstance(value, dict):
        return None
    key = value.get("key")
    name = value.get("name")
    kind = value.get("kind")
    observed_at = _parse_marker_time(value.get("observedAt")) or fallback_observed_at
    if (
        not isinstance(key, str)
        or not isinstance(name, str)
        or kind
        not in {
            "official",
            "media",
            "community",
            "aggregate",
        }
    ):
        return None
    discussion_url = value.get("discussionUrl")
    if discussion_url:
        try:
            discussion_url = normalize_news_url(str(discussion_url))
        except ValueError:
            discussion_url = None
    return HotspotNewsDiscoveryChannel(
        key=key,
        name=name,
        kind=kind,
        observedAt=observed_at,
        discussionUrl=discussion_url,
        discussionAt=_parse_marker_time(value.get("discussionAt")),
        rank=_safe_rank(value.get("rank")),
        points=_safe_nonnegative_int(value.get("points")),
        comments=_safe_nonnegative_int(value.get("comments")),
    )


def _item_channels(
    item: ContentItem,
    definition: HotspotNewsSourceDefinition,
    fetched_at: datetime,
) -> list[HotspotNewsDiscoveryChannel]:
    marker = _item_marker(item)
    candidates = marker.get("discoveryChannels")
    parsed = (
        [channel for value in candidates if (channel := _channel_from_marker(value, fallback_observed_at=fetched_at))]
        if isinstance(candidates, list)
        else []
    )
    if not parsed:
        parsed = [
            HotspotNewsDiscoveryChannel(
                key=definition.key,
                name=definition.name,
                kind=definition.source_kind,
                observedAt=fetched_at,
            )
        ]
    unique: dict[str, HotspotNewsDiscoveryChannel] = {channel.key: channel for channel in parsed}
    order = {definition.key: index for index, definition in enumerate(HOTSPOT_NEWS_SOURCES)}
    return sorted(unique.values(), key=lambda channel: (order.get(channel.key, 999), channel.key))


def _item_sort_time(item: HotspotNewsItem) -> datetime:
    discussion_times = [channel.discussionAt for channel in item.discoveryChannels if channel.discussionAt is not None]
    return item.publishedAt or item.updatedAt or max(discussion_times, default=None) or item.fetchedAt


def _balance_channel(item: HotspotNewsItem) -> str:
    return item.discoveryChannels[0].key


def _balanced_items(items: list[HotspotNewsItem]) -> list[HotspotNewsItem]:
    """Spread exposure across sources whose next item is within one day."""
    queues: dict[str, deque[HotspotNewsItem]] = defaultdict(deque)
    for item in sorted(items, key=lambda row: (_item_sort_time(row), row.id), reverse=True):
        queues[_balance_channel(item)].append(item)
    result: list[HotspotNewsItem] = []
    selected_counts: dict[str, int] = defaultdict(int)
    tolerance = timedelta(hours=HOTSPOT_NEWS_BALANCE_WINDOW_HOURS)
    while queues:
        freshest = max(queues, key=lambda key: (_item_sort_time(queues[key][0]), key))
        freshest_time = _item_sort_time(queues[freshest][0])
        eligible = [key for key in queues if freshest_time - _item_sort_time(queues[key][0]) <= tolerance]
        least_selected = min(selected_counts[key] for key in eligible)
        candidates = [key for key in eligible if selected_counts[key] == least_selected]
        channel = max(candidates, key=lambda key: (_item_sort_time(queues[key][0]), key))
        result.append(queues[channel].popleft())
        selected_counts[channel] += 1
        if not queues[channel]:
            del queues[channel]
    return result


async def load_hotspot_news(
    db: AsyncSession,
    *,
    selected_source: str | None = None,
    selected_topic: str | None = None,
    sort: Literal["balanced", "latest"] = "balanced",
    page: int = 1,
    page_size: int = HOTSPOT_NEWS_DEFAULT_PAGE_SIZE,
) -> tuple[HotspotNewsResponse, str]:
    """Load, filter and paginate saved news; never fetch or invoke a model."""
    definitions = _definition_by_url()
    key_to_definition = {item.key: item for item in HOTSPOT_NEWS_SOURCES}
    if selected_source is not None and selected_source not in key_to_definition:
        raise ValueError("hotspot_news_source_unknown")
    if selected_topic is not None and selected_topic not in _TOPIC_LABELS:
        raise ValueError("hotspot_news_topic_unknown")
    if sort not in {"balanced", "latest"}:
        raise ValueError("hotspot_news_sort_unknown")
    if page < 1 or page_size < 1 or page_size > 40:
        raise ValueError("hotspot_news_pagination_invalid")

    repository = RardarHotspotNewsRepository(db)
    sources = await repository.list_sources(
        platform=HOTSPOT_NEWS_PLATFORM,
        feed_urls=list(definitions),
    )
    source_ids = [source.id for source in sources]
    all_rows = await repository.list_items(source_ids=source_ids)
    source_by_id = {source.id: source for source in sources}
    now = datetime.now(UTC)

    all_items: list[HotspotNewsItem] = []
    for item in all_rows:
        source = source_by_id.get(item.source_id)
        if source is None:
            continue
        definition = definitions[source.url]
        published_at = _aware_utc(item.published_at)
        fetched_at = _aware_utc(item.crawled_at)
        if fetched_at is None:
            continue
        marker = _item_marker(item)
        updated_at = _parse_marker_time(marker.get("updatedAt"))
        topic_key = marker.get("topicKey")
        if topic_key not in _TOPIC_LABELS:
            feed_tags = marker.get("feedTags") if isinstance(marker.get("feedTags"), list) else []
            topic_key = classify_news_topic(item.title, feed_tags, default_topic=definition.default_topic)
        content_type = marker.get("contentType")
        if content_type not in {
            "official_update",
            "report",
            "research",
            "community_discussion",
            "uncategorized",
        }:
            content_type = definition.default_content_type
        publisher_name = marker.get("publisherName")
        if not isinstance(publisher_name, str) or not publisher_name.strip():
            publisher_name = (
                _publisher_name_for_url(item.url) if definition.source_kind == "community" else definition.name
            )
        language = marker.get("language")
        if language not in {"zh", "en", "unknown"}:
            language = definition.language
        channels = _item_channels(item, definition, fetched_at)
        primary_key = marker.get("sourceKey")
        if primary_key not in key_to_definition:
            primary_key = definition.key
        primary_definition = key_to_definition[primary_key]
        all_items.append(
            HotspotNewsItem(
                id=item.id,
                title=item.title,
                summary=item.summary,
                sourceKey=primary_key,
                sourceName=primary_definition.name,
                publisherName=publisher_name,
                url=item.url,
                topicKey=topic_key,
                topicLabel=_TOPIC_LABELS[topic_key],
                contentType=content_type,
                language=language,
                publishedAt=published_at,
                updatedAt=updated_at,
                fetchedAt=fetched_at,
                discoveryChannels=channels,
                quickRead=_quick_read_for_item(item),
            )
        )

    def matches_source(item: HotspotNewsItem, key: str | None) -> bool:
        return key is None or any(channel.key == key for channel in item.discoveryChannels)

    def matches_topic(item: HotspotNewsItem, key: str | None) -> bool:
        return key is None or item.topicKey == key

    source_counts = {
        definition.key: sum(
            matches_topic(item, selected_topic)
            and any(channel.key == definition.key for channel in item.discoveryChannels)
            for item in all_items
        )
        for definition in HOTSPOT_NEWS_SOURCES
    }
    topic_counts = {
        topic_key: sum(matches_source(item, selected_source) and item.topicKey == topic_key for item in all_items)
        for topic_key, _ in HOTSPOT_NEWS_TOPICS
    }
    matched = [
        item for item in all_items if matches_source(item, selected_source) and matches_topic(item, selected_topic)
    ]
    ordered = (
        sorted(matched, key=lambda item: (_item_sort_time(item), item.id), reverse=True)
        if sort == "latest"
        else _balanced_items(matched)
    )
    total_items = len(ordered)
    source_scope_item_count = sum(matches_topic(item, selected_topic) for item in all_items)
    topic_scope_item_count = sum(matches_source(item, selected_source) for item in all_items)
    total_pages = max(1, math.ceil(total_items / page_size))
    effective_page = min(page, total_pages)
    offset = (effective_page - 1) * page_size
    items = ordered[offset : offset + page_size]

    source_dtos: list[HotspotNewsSource] = []
    for definition in HOTSPOT_NEWS_SOURCES:
        source = next((row for row in sources if row.url == definition.feed_url), None)
        if source is None:
            state = "not_synced"
            last_sync_at = None
            error_code = None
        else:
            last_sync_at = _aware_utc(source.last_sync_at)
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
                kind=definition.source_kind,
                homepageUrl=definition.homepage_url,
                status=state,
                lastSyncAt=last_sync_at,
                itemCount=source_counts[definition.key],
                errorCode=error_code,
            )
        )

    topic_dtos = [
        HotspotNewsTopic(key=key, label=label, itemCount=topic_counts[key])
        for key, label in HOTSPOT_NEWS_TOPICS
        if topic_counts[key] > 0 or selected_topic == key
    ]
    synced_values = [source.lastSyncAt for source in source_dtos if source.lastSyncAt is not None]
    synced_at = max(synced_values, default=None)
    source_states = {source.status for source in source_dtos}
    if not sources:
        status = "not_synced"
    elif "failed" in source_states:
        status = "degraded"
    elif all_items and source_states <= {"stale", "not_synced"}:
        status = "stale"
    elif all_items or "healthy" in source_states:
        status = "ready"
    else:
        status = "not_synced"
    response = HotspotNewsResponse(
        status=status,
        syncedAt=synced_at,
        itemCount=len(items),
        totalItems=total_items,
        sourceScopeItemCount=source_scope_item_count,
        topicScopeItemCount=topic_scope_item_count,
        page=effective_page,
        pageSize=page_size,
        totalPages=total_pages,
        sort=sort,
        selectedSource=selected_source,
        selectedTopic=selected_topic,
        sources=source_dtos,
        topics=topic_dtos,
        items=items,
    )
    etag_payload = response.model_dump(mode="json")
    etag = hashlib.sha256(json.dumps(etag_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return response, f'"{etag}"'
