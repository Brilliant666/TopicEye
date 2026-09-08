from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.rardar import router as rardar_router
from app.core.config import settings
from app.core.database import get_db
from app.models.content import ContentItem
from app.models.source import Source, SourceStatus
from app.services import rardar_hotspot_news as news_service
from app.services.rardar_hotspot_news import (
    HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE,
    HOTSPOT_NEWS_PLATFORM,
    HOTSPOT_NEWS_SOURCES,
    _FeedFetchResult,
    classify_news_topic,
    load_hotspot_news,
    normalize_news_url,
    refresh_hotspot_news,
)
from app.services.rardar_llm_control import RardarLLMError, RardarLLMMetadata, RardarStructuredResult
from app.services.rardar_news_quickread import (
    QUICK_READ_MARKER,
    _Material,
    _QuickReadOutput,
    enhance_hotspot_news,
)
from app.services.trending_scrapers._hackernews import HackerNewsTrending


def _entry(
    *,
    url: str = "https://github.blog/changelog/2026-09-08-example/?utm_source=feed#section",
    title: str = "A concrete platform change",
    summary: str = "<p>The API now exposes a bounded, documented capability.</p>",
) -> dict:
    return {
        "url": url,
        "title": title,
        "summary": summary,
        "author": "GitHub",
        "published_at": datetime(2026, 9, 8, 1, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 8, 2, 0, tzinfo=UTC),
        "tags": ["API"],
    }


def _metadata() -> RardarLLMMetadata:
    return RardarLLMMetadata(
        scene="rardar_news_quickread",
        routing_group="rardar",
        model_display_name="mock-model",
        model_id=1,
        provider="mock",
        reasoning_effort="medium",
        prompt_version="rardar-news-quickread-v1",
        schema_version="rardar-news-quickread-output-v1",
        latency_ms=1,
        usage=None,
        cache_hit=False,
        result_state="completed",
    )


async def _route() -> str:
    return "route-v1"


def test_normalize_news_url_removes_tracking_but_not_meaningful_query():
    assert (
        normalize_news_url("HTTPS://Example.COM:443/post?utm_source=rss&version=2&fbclid=ignored#fragment")
        == "https://example.com/post?version=2"
    )
    with pytest.raises(ValueError, match="news_item_url_invalid"):
        normalize_news_url("http://127.0.0.1/private")
    with pytest.raises(ValueError, match="news_item_url_invalid"):
        normalize_news_url("javascript:alert(1)")


def test_topic_uses_item_evidence_instead_of_source_identity():
    assert classify_news_topic("OpenAI appoints a new finance officer", []) == "uncategorized"
    assert classify_news_topic("OpenAI releases a new foundation model", []) == "ai"
    assert classify_news_topic("Critical Linux security vulnerability fixed", []) == "security"


@pytest.mark.asyncio
async def test_refresh_is_zero_model_deduplicated_and_truthful(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    calls = 0

    async def fake_fetch(source, definition):
        nonlocal calls
        calls += 1
        return _FeedFetchResult(
            entries=[_entry(), _entry(url="https://github.blog/changelog/2026-09-08-example/?utm_medium=rss")],
            etag='"v1"',
            last_modified="Tue, 08 Sep 2026 02:00:00 GMT",
            not_modified=False,
        )

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    first = await refresh_hotspot_news(db, definitions=(definition,))
    second = await refresh_hotspot_news(db, definitions=(definition,))

    rows = (await db.execute(select(ContentItem))).scalars().all()
    source = (await db.execute(select(Source))).scalar_one()
    assert first.status == "completed"
    assert first.providerCalls == 0
    assert first.sources[0].created == 1
    assert second.sources[0].created == 0
    assert second.sources[0].duplicates == 2
    assert calls == 2
    assert len(rows) == 1
    assert rows[0].url == "https://github.blog/changelog/2026-09-08-example/"
    assert rows[0].summary == "The API now exposes a bounded, documented capability."
    assert rows[0].published_at == datetime(2026, 9, 8, 1, 0)
    assert rows[0].skip_analysis is True
    assert rows[0].skip_reason == "rardar_hotspot_news_zero_model_ingestion"
    assert source.platform == HOTSPOT_NEWS_PLATFORM
    assert source.hidden is True
    assert source.etag == '"v1"'

    loaded, _ = await load_hotspot_news(db)
    assert loaded.status == "ready"
    assert loaded.itemCount == 1
    assert loaded.items[0].publishedAt == datetime(2026, 9, 8, 1, 0, tzinfo=UTC)
    assert loaded.items[0].updatedAt == datetime(2026, 9, 8, 2, 0, tzinfo=UTC)
    assert loaded.items[0].publisherName == definition.name
    assert loaded.items[0].discoveryChannels[0].key == definition.key
    assert loaded.items[0].quickRead is None


@pytest.mark.asyncio
async def test_quick_read_preserves_raw_facts_survives_refresh_and_reuses_content_cache(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[1]
    calls = 0

    async def fake_fetch(source, source_definition):
        return _FeedFetchResult(entries=[_entry()], etag=None, last_modified=None, not_modified=False)

    async def fake_call(**kwargs):
        nonlocal calls
        calls += 1
        return RardarStructuredResult(
            value=_QuickReadOutput(
                titleZh="平台推出一项具体变更",
                summaryZh="GitHub 表示，该 API 现在提供一项有边界且有文档说明的能力。",
            ),
            metadata=_metadata(),
        )

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    before = (await db.execute(select(ContentItem))).scalar_one()
    raw = (before.title, before.summary, before.url, before.published_at, before.crawled_at)

    first = await enhance_hotspot_news(db, item_limit=1, caller=fake_call, route_resolver=_route)
    await refresh_hotspot_news(db, definitions=(definition,))
    second = await enhance_hotspot_news(db, item_limit=1, caller=fake_call, route_resolver=_route)
    after = (await db.execute(select(ContentItem))).scalar_one()
    loaded, _ = await load_hotspot_news(db)

    assert first.enhanced == 1
    assert second.cacheHits == 1
    assert calls == 1
    assert (after.title, after.summary, after.url, after.published_at, after.crawled_at) == raw
    assert loaded.items[0].title == raw[0]
    assert loaded.items[0].summary == raw[1]
    assert loaded.items[0].quickRead is not None
    assert loaded.items[0].quickRead.titleZh == "平台推出一项具体变更"
    assert loaded.items[0].quickRead.materialKind == "feed_summary"


@pytest.mark.asyncio
async def test_title_only_hn_never_uses_discussion_facts_or_accepts_an_invented_summary(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[-1]
    captured = ""

    async def fake_fetch(source, source_definition):
        entry = _entry(
            url="https://news.ycombinator.com/item?id=42",
            title="Ask HN: A title-only systems question",
            summary="",
        )
        entry.update(
            published_at=None,
            updated_at=None,
            discussion_at=datetime(2026, 9, 8, 3, 0, tzinfo=UTC),
            discussion_url="https://news.ycombinator.com/item?id=42",
            rank=3,
            points=188,
            comments=42,
        )
        return _FeedFetchResult(entries=[entry], etag=None, last_modified=None, not_modified=False)

    async def bad_call(**kwargs):
        nonlocal captured
        captured = json.dumps(kwargs["messages"], ensure_ascii=False)
        return RardarStructuredResult(
            value=_QuickReadOutput(titleZh="Ask HN：一个仅有标题的系统问题", summaryZh="这是编造的说明。"),
            metadata=_metadata(),
        )

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    result = await enhance_hotspot_news(db, item_limit=1, caller=bad_call, route_resolver=_route)
    row = (await db.execute(select(ContentItem))).scalar_one()
    loaded, _ = await load_hotspot_news(db)

    assert result.failed == 1
    assert loaded.items[0].quickRead is None
    assert QUICK_READ_MARKER not in row.tags
    material_payload = json.loads(json.loads(captured)[1]["content"])
    assert set(material_payload) == {"originalTitle", "materialKind", "material"}
    assert material_payload["materialKind"] == "title_only"
    assert material_payload["material"] is None

    async def title_translation(**kwargs):
        return RardarStructuredResult(
            value=_QuickReadOutput(titleZh="Ask HN：一个仅有标题的系统问题", summaryZh=None),
            metadata=_metadata(),
        )

    retried = await enhance_hotspot_news(db, item_limit=1, caller=title_translation, route_resolver=_route)
    loaded, _ = await load_hotspot_news(db)
    assert retried.enhanced == 1
    assert loaded.items[0].quickRead is not None
    assert loaded.items[0].quickRead.state == "title_only"
    assert loaded.items[0].quickRead.summaryZh is None


@pytest.mark.asyncio
async def test_failed_re_enhancement_keeps_last_good_derived_record_but_never_serves_it_as_current(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[1]

    async def fake_fetch(source, source_definition):
        return _FeedFetchResult(entries=[_entry()], etag=None, last_modified=None, not_modified=False)

    async def success(**kwargs):
        return RardarStructuredResult(
            value=_QuickReadOutput(titleZh="一项平台变更", summaryZh="来源摘要称 API 提供了一项新能力。"),
            metadata=_metadata(),
        )

    async def failure(**kwargs):
        raise RardarLLMError("rardar_llm_unavailable", classification="timeout")

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    await enhance_hotspot_news(db, item_limit=1, caller=success, route_resolver=_route)
    row = (await db.execute(select(ContentItem))).scalar_one()
    good = dict(row.tags[QUICK_READ_MARKER])
    row.title = "A materially changed title"
    await db.commit()

    result = await enhance_hotspot_news(db, item_limit=1, caller=failure, route_resolver=_route)
    await db.refresh(row)
    loaded, _ = await load_hotspot_news(db)

    assert result.failed == 1
    assert row.tags[QUICK_READ_MARKER] == good
    assert loaded.items[0].quickRead is None


@pytest.mark.asyncio
async def test_article_body_identity_ignores_interaction_metadata_but_changes_with_body(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[-1]
    body_digest = "body-v1"
    calls = 0

    async def fake_fetch(source, source_definition):
        entry = _entry(url="https://example.com/story", title="A title-only report", summary="")
        entry.update(published_at=None, updated_at=None, points=1, comments=2, rank=1)
        return _FeedFetchResult(entries=[entry], etag=None, last_modified=None, not_modified=False)

    async def material(db, item, source_key):
        return _Material("article_body", "The author reports a bounded change with direct evidence.", body_digest)

    async def fake_call(**kwargs):
        nonlocal calls
        calls += 1
        return RardarStructuredResult(
            value=_QuickReadOutput(titleZh="一则有正文依据的报道", summaryZh="作者依据直接材料报告了一项有限变更。"),
            metadata=_metadata(),
        )

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    await enhance_hotspot_news(db, item_limit=1, caller=fake_call, route_resolver=_route, material_loader=material)
    row = (await db.execute(select(ContentItem))).scalar_one()
    marker = row.tags["rardarHotspotNews"]
    marker["discoveryChannels"][0]["points"] = 999
    marker["discoveryChannels"][0]["comments"] = 999
    row.tags = {**row.tags, "rardarHotspotNews": marker}
    await db.commit()
    cached = await enhance_hotspot_news(
        db, item_limit=1, caller=fake_call, route_resolver=_route, material_loader=material
    )
    body_digest = "body-v2"
    changed = await enhance_hotspot_news(
        db, item_limit=1, caller=fake_call, route_resolver=_route, material_loader=material
    )

    assert cached.cacheHits == 1
    assert changed.enhanced == 1
    assert calls == 2


@pytest.mark.asyncio
async def test_quick_read_stops_after_two_consecutive_matching_provider_errors(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[1]
    calls = 0

    async def fake_fetch(source, source_definition):
        return _FeedFetchResult(
            entries=[_entry(url=f"https://example.com/story-{index}", title=f"Report {index}") for index in range(3)],
            etag=None,
            last_modified=None,
            not_modified=False,
        )

    async def failing_call(**kwargs):
        nonlocal calls
        calls += 1
        raise RardarLLMError("rardar_llm_invalid_output", classification="invalid_output")

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    result = await enhance_hotspot_news(db, item_limit=3, caller=failing_call, route_resolver=_route)

    assert result.status == "degraded"
    assert result.considered == 2
    assert result.failed == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_304_preserves_saved_rows(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    results = [
        _FeedFetchResult(entries=[_entry()], etag='"v1"', last_modified=None, not_modified=False),
        _FeedFetchResult(entries=[], etag='"v1"', last_modified=None, not_modified=True),
    ]

    async def fake_fetch(source, definition):
        return results.pop(0)

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    before = (await db.execute(select(ContentItem))).scalar_one()
    before_fetched = before.crawled_at
    before_summary = before.summary

    repeated = await refresh_hotspot_news(db, definitions=(definition,))
    after = (await db.execute(select(ContentItem))).scalar_one()

    assert repeated.sources[0].status == "not_modified"
    assert after.id == before.id
    assert after.crawled_at == before_fetched
    assert after.summary == before_summary


@pytest.mark.asyncio
async def test_refresh_bounds_large_feeds_to_the_newest_entries(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    entries = [
        {
            **_entry(url=f"https://example.com/news/{index}"),
            "published_at": datetime(2026, 9, 8, index % 24, tzinfo=UTC),
        }
        for index in range(HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE + 5)
    ]

    async def fake_fetch(source, definition):
        return _FeedFetchResult(entries=entries, etag=None, last_modified=None, not_modified=False)

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    result = await refresh_hotspot_news(db, definitions=(definition,))

    rows = (await db.execute(select(ContentItem))).scalars().all()
    assert result.sources[0].fetched == HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE + 5
    assert result.sources[0].created == HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE
    assert len(rows) == HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE


@pytest.mark.asyncio
async def test_source_failure_preserves_old_content_and_degrades_independently(db, monkeypatch):
    first, second = HOTSPOT_NEWS_SOURCES[:2]

    async def initial_fetch(source, definition):
        suffix = "github" if source.url == first.feed_url else "hugging-face"
        return _FeedFetchResult(
            entries=[_entry(url=f"https://example.com/{suffix}", title=f"{suffix} change")],
            etag=None,
            last_modified=None,
            not_modified=False,
        )

    monkeypatch.setattr(news_service, "_fetch_source", initial_fetch)
    await refresh_hotspot_news(db, definitions=(first, second))

    async def partial_failure(source, definition):
        if source.url == first.feed_url:
            raise RuntimeError("token=should-not-be-exposed")
        return _FeedFetchResult(entries=[], etag=None, last_modified=None, not_modified=True)

    monkeypatch.setattr(news_service, "_fetch_source", partial_failure)
    result = await refresh_hotspot_news(db, definitions=(first, second))
    loaded, _ = await load_hotspot_news(db)

    assert result.status == "degraded"
    assert result.providerCalls == 0
    assert len(loaded.items) == 2
    assert loaded.status == "degraded"
    states = {source.key: source.status for source in loaded.sources}
    assert states[first.key] == "failed"
    assert states[second.key] == "healthy"
    failed_source = (await db.execute(select(Source).where(Source.url == first.feed_url))).scalar_one()
    assert failed_source.status == SourceStatus.ERROR
    assert "should-not-be-exposed" not in (failed_source.sync_error or "")


@pytest.mark.asyncio
async def test_saved_news_api_never_fetches_sources_or_models(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]

    async def initial_fetch(source, source_definition):
        return _FeedFetchResult(entries=[_entry()], etag=None, last_modified=None, not_modified=False)

    monkeypatch.setattr(news_service, "_fetch_source", initial_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))

    async def forbidden_fetch(source, source_definition):
        raise AssertionError("GET must not fetch a source")

    monkeypatch.setattr(news_service, "_fetch_source", forbidden_fetch)
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", True)

    app = FastAPI()
    app.include_router(rardar_router, prefix="/api/v1")

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/rardar/hotspot-news")
        filtered = await client.get(f"/api/v1/rardar/hotspot-news?source={definition.key}")
        paged = await client.get(
            f"/api/v1/rardar/hotspot-news?source={definition.key}&topic=software-open-source&sort=latest&pageSize=1"
        )
        unknown = await client.get("/api/v1/rardar/hotspot-news?source=unknown")
        unknown_topic = await client.get("/api/v1/rardar/hotspot-news?topic=unknown")

    assert response.status_code == 200
    assert response.json()["itemCount"] == 1
    assert filtered.status_code == 200
    assert filtered.json()["selectedSource"] == definition.key
    assert paged.status_code == 200
    assert paged.json()["selectedTopic"] == "software-open-source"
    assert paged.json()["sort"] == "latest"
    assert unknown.status_code == 422
    assert unknown_topic.status_code == 422


@pytest.mark.asyncio
async def test_cross_source_duplicate_preserves_publisher_and_all_discovery_channels(db, monkeypatch):
    publisher = HOTSPOT_NEWS_SOURCES[1]
    community = HOTSPOT_NEWS_SOURCES[-1]
    shared_url = "https://example.com/chips/new-architecture"

    async def fake_fetch(source, definition):
        if definition.key == community.key:
            return _FeedFetchResult(
                entries=[
                    {
                        **_entry(url=shared_url, title="New chip architecture reaches production"),
                        "summary": None,
                        "published_at": None,
                        "updated_at": None,
                        "discussion_at": datetime(2026, 9, 8, 3, 0, tzinfo=UTC),
                        "discussion_url": "https://news.ycombinator.com/item?id=42",
                        "rank": 2,
                        "points": 321,
                        "comments": 45,
                    }
                ],
                etag=None,
                last_modified=None,
                not_modified=False,
            )
        return _FeedFetchResult(
            entries=[_entry(url=shared_url, title="New chip architecture reaches production")],
            etag=None,
            last_modified=None,
            not_modified=False,
        )

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(publisher, community))
    loaded, _ = await load_hotspot_news(db)

    assert loaded.totalItems == 1
    item = loaded.items[0]
    assert item.publisherName == publisher.name
    assert item.publishedAt == datetime(2026, 9, 8, 1, 0, tzinfo=UTC)
    assert [channel.key for channel in item.discoveryChannels] == [publisher.key, community.key]
    hn = item.discoveryChannels[1]
    assert hn.discussionAt == datetime(2026, 9, 8, 3, 0, tzinfo=UTC)
    assert str(hn.discussionUrl) == "https://news.ycombinator.com/item?id=42"
    assert (hn.rank, hn.points, hn.comments) == (2, 321, 45)


@pytest.mark.asyncio
async def test_filters_pagination_and_facets_cover_the_full_saved_range(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    entries = []
    for index in range(25):
        title = f"Security vulnerability report {index}" if index % 2 == 0 else f"New processor hardware {index}"
        entries.append(
            {
                **_entry(url=f"https://example.com/news/{index}", title=title),
                "published_at": datetime(2026, 9, 8, index % 24, tzinfo=UTC),
            }
        )

    async def fake_fetch(source, source_definition):
        return _FeedFetchResult(entries=entries, etag=None, last_modified=None, not_modified=False)

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))

    first, _ = await load_hotspot_news(db, selected_topic="security", page=1, page_size=5)
    third, _ = await load_hotspot_news(db, selected_topic="security", page=3, page_size=5)
    filtered, _ = await load_hotspot_news(db, selected_source=definition.key, page_size=40)

    assert first.totalItems == 13
    assert first.sourceScopeItemCount == 13
    assert first.topicScopeItemCount == 25
    assert first.itemCount == 5
    assert first.totalPages == 3
    assert third.page == 3
    assert third.itemCount == 3
    assert all(item.topicKey == "security" for item in [*first.items, *third.items])
    assert filtered.totalItems == 25
    assert {topic.key: topic.itemCount for topic in filtered.topics} == {
        "security": 13,
        "hardware-chips": 12,
    }


@pytest.mark.asyncio
async def test_balanced_sort_diversifies_sources_inside_same_time_window(db, monkeypatch):
    first, second = HOTSPOT_NEWS_SOURCES[:2]

    async def fake_fetch(source, definition):
        base = 10 if definition.key == first.key else 9
        entries = [
            {
                **_entry(
                    url=f"https://{definition.key}.example.com/{index}",
                    title=f"{definition.name} software update {index}",
                ),
                "published_at": datetime(2026, 9, 8, base - index, tzinfo=UTC),
            }
            for index in range(3)
        ]
        return _FeedFetchResult(entries=entries, etag=None, last_modified=None, not_modified=False)

    monkeypatch.setattr(news_service, "_fetch_source", fake_fetch)
    await refresh_hotspot_news(db, definitions=(first, second))

    balanced, _ = await load_hotspot_news(db, sort="balanced", page_size=10)
    latest, _ = await load_hotspot_news(db, sort="latest", page_size=10)
    scoped, _ = await load_hotspot_news(
        db,
        selected_source=first.key,
        selected_topic="software-open-source",
        page_size=10,
    )
    balanced_sources = [item.discoveryChannels[0].key for item in balanced.items]
    latest_sources = [item.discoveryChannels[0].key for item in latest.items]

    assert balanced_sources[:4] == [first.key, second.key, first.key, second.key]
    assert latest_sources[:3] == [first.key, second.key, first.key]
    assert scoped.totalItems == 3
    assert scoped.sourceScopeItemCount == 6
    assert scoped.topicScopeItemCount == 3


@pytest.mark.asyncio
async def test_hacker_news_adapter_preserves_discussion_time_and_conditionals():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("topstories.json"):
            return httpx.Response(200, json=[123], headers={"ETag": '"hn-v2"'})
        return httpx.Response(
            200,
            json={
                "id": 123,
                "title": "A compiler release",
                "url": "https://example.com/compiler",
                "score": 88,
                "descendants": 12,
                "by": "author",
                "time": 1788836400,
            },
        )

    scraper = HackerNewsTrending()
    scraper.conditional_etag = '"hn-v1"'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await scraper.fetch(client)

    assert result[0]["extra"]["time"] == 1788836400
    assert result[0]["extra"]["hn_link"] == "https://news.ycombinator.com/item?id=123"
    assert requests[0].headers["If-None-Match"] == '"hn-v1"'
    assert "If-None-Match" not in requests[1].headers
    assert scraper._latest_etag == '"hn-v2"'


@pytest.mark.asyncio
async def test_hacker_news_adapter_304_skips_item_requests():
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(304, headers={"ETag": '"hn-v1"'})

    scraper = HackerNewsTrending()
    scraper.conditional_etag = '"hn-v1"'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await scraper.fetch(client)

    assert result == []
    assert scraper.not_modified is True
    assert scraper.fetch_degraded is False
    assert requests == 1
