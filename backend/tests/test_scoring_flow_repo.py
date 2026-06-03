from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.analysis import AiAnalysis
from app.models.content import ContentItem, ContentStatus
from app.models.source import Source, SourceStatus, SourceType
from app.repositories.content_repo import ContentRepo
from app.services.scoring_flow import build_scoring_flow_payload, invalidate_scoring_flow_cache


@pytest.mark.asyncio
async def test_scoring_flow_candidates_use_analysis_presence_not_status():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.utcnow()
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
                weight=5,
            )
        )
        db.add_all(
            [
                ContentItem(
                    id=1,
                    title="已有分析但状态未同步",
                    url="https://example.com/analyzed-pending",
                    source_id=1,
                    source_name="测试信源",
                    source_type="RSS",
                    category="AI",
                    status=ContentStatus.PENDING,
                    crawled_at=now,
                ),
                ContentItem(
                    id=2,
                    title="尚未分析",
                    url="https://example.com/no-analysis",
                    source_id=1,
                    source_name="测试信源",
                    source_type="RSS",
                    category="AI",
                    status=ContentStatus.PENDING,
                    crawled_at=now,
                ),
            ]
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
            )
        )
        await db.commit()

        repo = ContentRepo(db)
        cutoff = now - timedelta(hours=24)
        total = await repo.count_for_scoring(time_cutoff=cutoff)
        rows = await repo.list_scoring_rows(time_cutoff=cutoff, limit=10)

        assert total == 1
        assert [row.id for row in rows] == [1]
        assert rows[0].title == "已有分析但状态未同步"
        assert rows[0].source_weight_db == 5

    await engine.dispose()


@pytest.mark.asyncio
async def test_scoring_flow_diagnostics_include_requested_custom_window():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.utcnow()
    invalidate_scoring_flow_cache()
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
                weight=5,
            )
        )
        db.add(
            ContentItem(
                id=1,
                title="自定义窗口样本",
                url="https://example.com/custom-window",
                source_id=1,
                source_name="测试信源",
                source_type="RSS",
                category="AI",
                status=ContentStatus.PENDING,
                crawled_at=now,
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
            )
        )
        await db.commit()

        payload = await build_scoring_flow_payload(db, hours=96, limit=20)

        window_options = payload["diagnostics"]["window_options"]
        collected_window_options = payload["diagnostics"]["collected_window_options"]
        assert {"hours": 96, "count": 1} in window_options
        assert {"hours": 96, "count": 1} in collected_window_options
        assert [item["hours"] for item in window_options] == [24, 48, 96, 168, 720]

    invalidate_scoring_flow_cache()
    await engine.dispose()
