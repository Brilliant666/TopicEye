from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base
from app.models.analysis import AiAnalysis
from app.models.content import ContentItem, ContentStatus
from app.models.source import Source, SourceStatus, SourceType
from app.services import cache_warmup
from app.services.content_list_cache import home_content_list_cache_params
from app.services.json_cache import get_cached_json, invalidate_json_cache
from app.services.scoring_flow import SCORING_FLOW_WARMUP_TARGETS, get_cached_scoring_flow_json
from app.services.source_cache import default_source_list_cache_params
from app.services.today_picks_cache import default_today_picks_cache_params


@pytest.mark.asyncio
async def test_warmup_read_caches_populates_hot_read_cache_keys(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    invalidate_json_cache()
    monkeypatch.setattr(cache_warmup, "async_session", session_factory)

    async with session_factory() as db:
        db.add(
            Source(
                id=1,
                name="测试信源",
                source_type=SourceType.RSS,
                url="https://example.com/rss.xml",
                category="AI",
                status=SourceStatus.ACTIVE,
                enabled=True,
                sort_order=10,
            )
        )
        db.add(
            ContentItem(
                id=1,
                title="测试选题",
                url="https://example.com/topic",
                source_id=1,
                source_name="测试信源",
                source_type="RSS",
                category="AI",
                status=ContentStatus.ANALYZED,
                is_favorited=True,
                crawled_at=datetime.utcnow(),
            )
        )
        db.add(
            AiAnalysis(
                content_id=1,
                curation_score=82,
                info_density=75,
                actionability=70,
                source_weight=80,
                quality_score=78,
                hot_score=65,
                freshness_score=90,
                creator_score=72,
                viral_score=61,
                risk_score=15,
                recommendation="适合作为创作者选题观察样本",
            )
        )
        await db.commit()

    result = await cache_warmup.warmup_read_caches()

    expected_warmed = {
        "sources:list:1:20",
        "contents:list:1:50:48",
        "contents:today-picks:48",
        "contents:favorites:list:1:20",
        "stats:overview:7",
    }
    expected_warmed.update(f"scoring-flow:{hours}:{limit}" for hours, limit in SCORING_FLOW_WARMUP_TARGETS)
    assert set(result["warmed"]) == expected_warmed
    assert result["errors"] == []
    ttl = settings.READ_CACHE_TTL_SECONDS
    assert get_cached_json(default_source_list_cache_params().key, ttl_seconds=ttl) is not None
    assert get_cached_json(home_content_list_cache_params().key, ttl_seconds=ttl) is not None
    assert get_cached_json(default_today_picks_cache_params().key, ttl_seconds=ttl) is not None
    assert get_cached_json("contents:favorites:list:1:20", ttl_seconds=ttl) is not None
    assert get_cached_json("stats:overview:7", ttl_seconds=ttl) is not None
    for hours, limit in SCORING_FLOW_WARMUP_TARGETS:
        assert get_cached_scoring_flow_json(hours=hours, limit=limit) is not None

    invalidate_json_cache()
    await engine.dispose()
