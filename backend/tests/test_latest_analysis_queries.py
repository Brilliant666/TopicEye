from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.analysis import AiAnalysis
from app.models.content import ContentItem, ContentStatus
from app.models.topic import TopicGroup
from app.models.trend import TopicTrend
from app.repositories.analysis_repo import AnalysisRepository
from app.services import creation, topic_clustering
from app.services.trends import snapshot_daily_trends


async def _session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_analysis_repository_reads_and_filters_latest_rows_only():
    engine, session_factory = await _session_factory()
    now = datetime.utcnow()
    async with session_factory() as db:
        db.add(ContentItem(id=1, title="测试内容", url="https://example.com/1"))
        db.add_all([
            AiAnalysis(
                id=2,
                content_id=1,
                summary="旧分析",
                curation_score=95,
                creator_score=95,
                enrichment_status="pending",
                created_at=now,
            ),
            AiAnalysis(
                id=1,
                content_id=1,
                summary="新分析",
                curation_score=10,
                creator_score=10,
                enrichment_status="completed",
                created_at=now + timedelta(minutes=1),
            ),
        ])
        await db.commit()

        repo = AnalysisRepository(db)
        latest = await repo.get_by_content_id(1)
        pending_ids = await repo.get_pending_enrichment_ids(min_score=70, limit=10)
        high_score_items, total = await repo.list_with_score_filter(min_creator_score=70)

        assert latest is not None
        assert latest.summary == "新分析"
        assert pending_ids == []
        assert high_score_items == []
        assert total == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_creation_plan_uses_latest_analysis_prompt_material(monkeypatch):
    captured_messages = []

    async def fake_call_llm_json(messages, scene):
        captured_messages.extend(messages)
        return {"titles": ["新分析选题"]}

    monkeypatch.setattr(creation, "call_llm_json", fake_call_llm_json)
    engine, session_factory = await _session_factory()
    now = datetime.utcnow()
    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="Runway 更新",
                url="https://example.com/runway",
                source_name="测试信源",
                status=ContentStatus.ANALYZED,
            )
        )
        db.add_all([
            AiAnalysis(
                id=2,
                content_id=1,
                summary="旧分析摘要",
                tags=["旧标签"],
                created_at=now,
            ),
            AiAnalysis(
                id=1,
                content_id=1,
                summary="新分析摘要",
                tags=["新标签"],
                created_at=now + timedelta(minutes=1),
            ),
        ])
        await db.commit()

        plan = await creation.generate_creation_plan(db, 1, "xiaohongshu")

        prompt_text = "\n".join(str(message["content"]) for message in captured_messages)
        assert plan["titles"] == ["新分析选题"]
        assert "新分析摘要" in prompt_text
        assert "新标签" in prompt_text
        assert "旧分析摘要" not in prompt_text

    await engine.dispose()


@pytest.mark.asyncio
async def test_clustering_uses_one_latest_analysis_per_content(monkeypatch):
    async def fake_name_clusters(clusters):
        return [
            {
                "name": "新标签话题",
                "summary": "只看新分析",
                "keywords": ["新标签"],
                "item_ids": [item["id"] for item in clusters[0]],
                "best_score": max(item["curation_score"] for item in clusters[0]),
                "content_count": len(clusters[0]),
            }
        ]

    async def fake_dedup_candidate_clusters(clusters):
        return {}

    monkeypatch.setattr(topic_clustering, "_name_clusters", fake_name_clusters)
    monkeypatch.setattr(topic_clustering, "_dedup_candidate_clusters", fake_dedup_candidate_clusters)
    engine, session_factory = await _session_factory()
    now = datetime.utcnow()
    async with session_factory() as db:
        for content_id in (1, 2):
            db.add(
                ContentItem(
                    id=content_id,
                    title=f"内容 {content_id}",
                    url=f"https://example.com/{content_id}",
                    status=ContentStatus.ANALYZED,
                )
            )
            db.add_all([
                AiAnalysis(
                    id=content_id + 10,
                    content_id=content_id,
                    tags=["旧标签"],
                    curation_score=90,
                    created_at=now,
                ),
                AiAnalysis(
                    id=content_id,
                    content_id=content_id,
                    tags=["新标签"],
                    curation_score=40 + content_id,
                    created_at=now + timedelta(minutes=1),
                ),
            ])
        await db.commit()

        stats = await topic_clustering.cluster_and_dedup(db)
        topics = (await db.execute(select(TopicGroup))).scalars().all()

        assert stats["total"] == 2
        assert stats["clusters"] == 1
        assert len(topics) == 1
        assert topics[0].content_count == 2
        assert topics[0].best_score == 42

    await engine.dispose()


@pytest.mark.asyncio
async def test_trend_snapshot_counts_latest_analysis_once():
    engine, session_factory = await _session_factory()
    target = date(2026, 6, 8)
    created_at = datetime(2026, 6, 8, 12, 0, 0)
    async with session_factory() as db:
        db.add(TopicGroup(id=1, name="AI话题"))
        db.add(
            ContentItem(
                id=1,
                title="趋势内容",
                url="https://example.com/trend",
                topic_id=1,
                status=ContentStatus.ANALYZED,
                created_at=created_at,
            )
        )
        db.add_all([
            AiAnalysis(
                id=2,
                content_id=1,
                curation_score=95,
                tags=["旧关键词"],
                created_at=created_at,
            ),
            AiAnalysis(
                id=1,
                content_id=1,
                curation_score=35,
                tags=["新关键词"],
                created_at=created_at + timedelta(minutes=1),
            ),
        ])
        await db.commit()

        result = await snapshot_daily_trends(db, target)
        trends = (await db.execute(select(TopicTrend))).scalars().all()
        topic_trend = next(item for item in trends if item.topic_id == 1)
        keywords = {item.keyword for item in trends if item.keyword}

        assert result == {"topics": 1, "keywords": 1, "date": "2026-06-08"}
        assert topic_trend.content_count == 1
        assert topic_trend.avg_score == 35.0
        assert topic_trend.max_score == 35.0
        assert topic_trend.pick_count == 0
        assert keywords == {"新关键词"}

    await engine.dispose()
