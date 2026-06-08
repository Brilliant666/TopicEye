from datetime import datetime, timedelta
from types import SimpleNamespace
import asyncio

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.exc import OperationalError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1 import analyses as analyses_api
from app.core.database import Base
from app import main as app_main
from app.models.analysis import AiAnalysis
from app.models.content import ContentItem, ContentStatus
from app.models.metrics import ContentMetrics  # noqa: F401
from app.models.source import Source  # noqa: F401
from app.models.topic import TopicGroup  # noqa: F401
from app.repositories.content_repo import ANALYSIS_STALE_MINUTES, ContentRepo
from app.services import analysis
from app.services import analysis_jobs
from app.services.analysis_jobs import (
    create_analysis_job,
    finish_analysis_job,
    get_analysis_job,
    mark_analysis_job_running,
    reset_analysis_jobs,
)
from app import scheduler as scheduler_module
from app.services.scoring_flow import (
    build_empty_payload,
    cache_payload,
    get_cached_scoring_flow_json,
    invalidate_scoring_flow_cache,
)


async def _session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_list_pending_for_analysis_filters_recent_pending_items():
    engine, session_factory = await _session_factory()
    now = datetime.utcnow()

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=1,
                title="旧待分析内容",
                url="https://example.com/old",
                status=ContentStatus.PENDING,
                crawled_at=now - timedelta(hours=30),
            ),
            ContentItem(
                id=2,
                title="最近待分析内容",
                url="https://example.com/recent",
                status=ContentStatus.PENDING,
                crawled_at=now - timedelta(hours=1),
            ),
            ContentItem(
                id=3,
                title="最近已分析内容",
                url="https://example.com/analyzed",
                status=ContentStatus.ANALYZED,
                crawled_at=now,
            ),
            ContentItem(
                id=4,
                title="超时分析中内容",
                url="https://example.com/stale-analyzing",
                status=ContentStatus.ANALYZING,
                crawled_at=now - timedelta(minutes=30),
                updated_at=now - timedelta(minutes=ANALYSIS_STALE_MINUTES + 5),
            ),
            ContentItem(
                id=5,
                title="刚进入分析中的内容",
                url="https://example.com/fresh-analyzing",
                status=ContentStatus.ANALYZING,
                crawled_at=now - timedelta(minutes=20),
                updated_at=now,
            ),
            ContentItem(
                id=6,
                title="可重试失败内容",
                url="https://example.com/retry-error",
                status=ContentStatus.ERROR,
                crawled_at=now - timedelta(minutes=10),
                updated_at=now - timedelta(minutes=ANALYSIS_STALE_MINUTES + 5),
            ),
            ContentItem(
                id=7,
                title="刚失败内容",
                url="https://example.com/fresh-error",
                status=ContentStatus.ERROR,
                crawled_at=now - timedelta(minutes=5),
                updated_at=now,
            ),
        ])
        await db.commit()

        pending = await ContentRepo(db).list_pending_for_analysis(limit=10, hours=24)

    assert [item.id for item in pending] == [6, 4, 2]
    await engine.dispose()


@pytest.mark.asyncio
async def test_claim_pending_analysis_ids_marks_items_analyzing_before_workers_run():
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="待认领内容",
                url="https://example.com/claim-pending",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow(),
            )
        )
        await db.commit()

        claimed_ids = await ContentRepo(db).claim_pending_analysis_ids(limit=10, hours=24)
        await db.commit()

    async with session_factory() as db:
        second_claim = await ContentRepo(db).claim_pending_analysis_ids(limit=10, hours=24)
        content = await db.get(ContentItem, 1)

    assert claimed_ids == [1]
    assert second_claim == []
    assert content.status == ContentStatus.ANALYZING
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_pending_defaults_to_background_queue(monkeypatch):
    await reset_analysis_jobs()

    async def fail_if_sync_analysis_runs(*args, **kwargs):
        raise AssertionError("pending endpoint should not analyze synchronously by default")

    monkeypatch.setattr(analyses_api, "analyze_batch_concurrent", fail_if_sync_analysis_runs)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="最近待后台分析内容",
                url="https://example.com/background-queue",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow(),
            )
        )
        await db.commit()

        background_tasks = BackgroundTasks()
        result = await analyses_api.analyze_all_pending(
            limit=10,
            hours=24,
            sync=False,
            background_tasks=background_tasks,
            db=db,
        )

    assert result["mode"] == "background"
    assert result["queued_ids"] == [1]
    assert result["analyzed_ids"] == []
    assert result["job_id"]
    assert result["hours"] == 24
    assert len(background_tasks.tasks) == 1

    job = await get_analysis_job(result["job_id"])
    assert job["status"] == "QUEUED"
    assert job["queued_ids"] == [1]
    assert job["pending_ids"] == [1]

    async with session_factory() as db:
        content = await db.get(ContentItem, 1)
    assert content.status == ContentStatus.ANALYZING

    await engine.dispose()
    await reset_analysis_jobs()


@pytest.mark.asyncio
async def test_analyze_pending_deduplicates_inflight_background_jobs(monkeypatch):
    await reset_analysis_jobs()

    async def fail_if_sync_analysis_runs(*args, **kwargs):
        raise AssertionError("pending endpoint should not analyze synchronously by default")

    monkeypatch.setattr(analyses_api, "analyze_batch_concurrent", fail_if_sync_analysis_runs)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="重复提交的后台分析内容",
                url="https://example.com/background-queue-dedupe",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow(),
            )
        )
        await db.commit()

        first_tasks = BackgroundTasks()
        first = await analyses_api.analyze_all_pending(
            limit=10,
            hours=24,
            sync=False,
            background_tasks=first_tasks,
            db=db,
        )
        second_tasks = BackgroundTasks()
        second = await analyses_api.analyze_all_pending(
            limit=10,
            hours=24,
            sync=False,
            background_tasks=second_tasks,
            db=db,
        )

    assert first["queued_ids"] == [1]
    assert first["job_id"]
    assert len(first_tasks.tasks) == 1
    assert second["queued_ids"] == []
    assert second["skipped_inflight_ids"] == []
    assert second["job_id"] is None
    assert len(second_tasks.tasks) == 0

    await engine.dispose()
    await reset_analysis_jobs()


@pytest.mark.asyncio
async def test_analysis_job_status_records_completion():
    await reset_analysis_jobs()
    job = await create_analysis_job([1, 2])

    await mark_analysis_job_running(job.job_id)
    await finish_analysis_job(job.job_id, analyzed_ids=[1], failed_ids=[2])

    status = await analyses_api.get_analysis_job_status(job.job_id)

    assert status["status"] == "PARTIAL"
    assert status["analyzed_ids"] == [1]
    assert status["failed_ids"] == [2]
    assert status["pending_ids"] == []
    assert status["started_at"] is not None
    assert status["finished_at"] is not None
    await reset_analysis_jobs()


@pytest.mark.asyncio
async def test_background_analysis_releases_failed_claims(monkeypatch):
    await reset_analysis_jobs()
    engine, session_factory = await _session_factory()
    monkeypatch.setattr(analyses_api, "async_session", session_factory)

    async def fake_concurrent(content_ids, **_kwargs):
        async with session_factory() as db:
            content = await db.get(ContentItem, 1)
            analysis_record = AiAnalysis(
                content_id=1,
                summary="后台已分析",
                curation_score=60,
            )
            db.add(analysis_record)
            content.status = ContentStatus.ANALYZED
            await db.commit()
        return [SimpleNamespace(content_id=1)]

    monkeypatch.setattr(analyses_api, "analyze_batch_concurrent", fake_concurrent)

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=1,
                title="后台成功内容",
                url="https://example.com/background-success",
                status=ContentStatus.ANALYZING,
                crawled_at=datetime.utcnow(),
            ),
            ContentItem(
                id=2,
                title="后台失败释放内容",
                url="https://example.com/background-release-failed",
                status=ContentStatus.ANALYZING,
                crawled_at=datetime.utcnow(),
            ),
        ])
        await db.commit()

    job = await create_analysis_job([1, 2])
    await analyses_api._run_batch_background(job.job_id, [1, 2])

    async with session_factory() as db:
        statuses = {
            item.id: item.status
            for item in (await db.execute(select(ContentItem))).scalars().all()
        }
    job_status = await get_analysis_job(job.job_id)

    assert statuses == {
        1: ContentStatus.ANALYZED,
        2: ContentStatus.PENDING,
    }
    assert job_status["status"] == "PARTIAL"
    assert job_status["analyzed_ids"] == [1]
    assert job_status["failed_ids"] == [2]
    await engine.dispose()
    await reset_analysis_jobs()


@pytest.mark.asyncio
async def test_background_analysis_releases_claims_on_batch_exception(monkeypatch):
    await reset_analysis_jobs()
    engine, session_factory = await _session_factory()
    monkeypatch.setattr(analyses_api, "async_session", session_factory)

    async def failing_concurrent(*_args, **_kwargs):
        raise RuntimeError("background worker crashed")

    monkeypatch.setattr(analyses_api, "analyze_batch_concurrent", failing_concurrent)

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=1,
                title="后台异常释放一",
                url="https://example.com/background-exception-release-1",
                status=ContentStatus.ANALYZING,
                crawled_at=datetime.utcnow(),
            ),
            ContentItem(
                id=2,
                title="后台异常释放二",
                url="https://example.com/background-exception-release-2",
                status=ContentStatus.ANALYZING,
                crawled_at=datetime.utcnow(),
            ),
        ])
        await db.commit()

    job = await create_analysis_job([1, 2])

    with pytest.raises(RuntimeError):
        await analyses_api._run_batch_background(job.job_id, [1, 2])

    async with session_factory() as db:
        statuses = {
            item.id: item.status
            for item in (await db.execute(select(ContentItem))).scalars().all()
        }
    job_status = await get_analysis_job(job.job_id)

    assert statuses == {
        1: ContentStatus.PENDING,
        2: ContentStatus.PENDING,
    }
    assert job_status["status"] == "FAILED"
    assert job_status["failed_ids"] == [1, 2]
    assert "background worker crashed" in job_status["error_message"]
    await engine.dispose()
    await reset_analysis_jobs()


@pytest.mark.asyncio
async def test_analysis_job_inflight_ttl_releases_stuck_ids(monkeypatch):
    await reset_analysis_jobs()
    monkeypatch.setattr(analysis_jobs.settings, "ANALYSIS_JOB_INFLIGHT_TTL_SECONDS", 60)

    first = await create_analysis_job([1])
    first.queued_at = datetime.utcnow() - timedelta(seconds=90)
    second = await create_analysis_job([1])

    expired = await get_analysis_job(first.job_id)
    active = await get_analysis_job(second.job_id)

    assert expired["status"] == "EXPIRED"
    assert second.content_ids == [1]
    assert second.skipped_inflight_ids == []
    assert active["status"] == "QUEUED"
    await reset_analysis_jobs()


@pytest.mark.asyncio
async def test_analyze_pending_sync_uses_concurrent_analysis(monkeypatch):
    called = {}

    async def fake_concurrent(content_ids, **_kwargs):
        called["ids"] = content_ids
        return [
            AiAnalysis(
                content_id=content_id,
                summary="并发分析完成",
                curation_score=60,
            )
            for content_id in content_ids
        ]

    async def fail_if_sequential_analysis_runs(*args, **kwargs):
        raise AssertionError("pending sync endpoint should use concurrent analysis")

    monkeypatch.setattr(analyses_api, "analyze_batch_concurrent", fake_concurrent)
    monkeypatch.setattr(analyses_api, "analyze_batch", fail_if_sequential_analysis_runs)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=1,
                title="最近待同步分析一",
                url="https://example.com/sync-concurrent-1",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow(),
            ),
            ContentItem(
                id=2,
                title="最近待同步分析二",
                url="https://example.com/sync-concurrent-2",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow() - timedelta(minutes=1),
            ),
        ])
        await db.commit()

        result = await analyses_api.analyze_all_pending(
            limit=10,
            hours=24,
            sync=True,
            background_tasks=BackgroundTasks(),
            db=db,
        )

    assert called["ids"] == [1, 2]
    assert result["mode"] == "sync"
    assert result["queued_ids"] == []
    assert result["analyzed_ids"] == [1, 2]
    assert result["count"] == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_recovers_from_empty_llm_response(monkeypatch):
    async def empty_llm_response(*args, **kwargs):
        return {"raw_response": ""}

    monkeypatch.setattr(analysis, "call_llm_json", empty_llm_response)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="最近的创作者选题信号",
                url="https://example.com/recent-topic",
                source_name="测试信源",
                source_type="RSS",
                platform="rsshub",
                status=ContentStatus.PENDING,
                summary="一个关于创作者工具升级的短摘要。",
                raw_content="这是一个用于测试的内容。它需要在 LLM 返回空响应时仍然生成本地基础分析结果，避免算法流程 24 小时窗口没有评分样本。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_analysis = await db.scalar(select(AiAnalysis).where(AiAnalysis.content_id == 1))
        stored_content = await db.get(ContentItem, 1)

    assert [item.content_id for item in results] == [1]
    assert stored_analysis is not None
    assert stored_analysis.summary
    assert stored_analysis.curation_score and stored_analysis.curation_score > 0
    assert stored_content.status == ContentStatus.ANALYZED
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_normalizes_malformed_llm_contract(monkeypatch):
    async def malformed_llm_response(*args, **kwargs):
        return {
            "summary": {"bad": "object"},
            "key_points": "单点观点",
            "recommendation": 123,
            "creator_angles": ["角度", " ", "角度", {"bad": 1}],
            "title_suggestions": '["标题一", "标题二"]',
            "risk_notes": {"bad": "risk"},
            "tags": '["AI", "AI", " ", "%s", "工具"]' % ("x" * 80),
            "scores": {
                "quality_score": 120,
                "hot_score": -5,
                "freshness_score": "80",
                "creator_score": None,
                "viral_score": "bad",
                "risk_score": 90,
            },
            "curation": {
                "curation_score": 150,
                "info_density": -10,
                "actionability": "70",
                "source_weight": "bad",
            },
        }

    monkeypatch.setattr(analysis, "call_llm_json", malformed_llm_response)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="格式漂移的分析结果",
                url="https://example.com/malformed-analysis-contract",
                status=ContentStatus.PENDING,
                raw_content="用于验证 LLM 返回局部格式异常时，分析结果仍会以稳定契约落库。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_analysis = await db.scalar(select(AiAnalysis).where(AiAnalysis.content_id == 1))
        stored_content = await db.get(ContentItem, 1)

    assert [item.content_id for item in results] == [1]
    assert stored_content.status == ContentStatus.ANALYZED
    assert stored_analysis.quality_score == 100
    assert stored_analysis.hot_score == 0
    assert stored_analysis.freshness_score == 80
    assert stored_analysis.creator_score == 50
    assert stored_analysis.viral_score == 50
    assert stored_analysis.risk_score == 90
    assert stored_analysis.curation_score == 100
    assert stored_analysis.info_density == 0
    assert stored_analysis.actionability == 70
    assert stored_analysis.source_weight == 50
    assert stored_analysis.summary == ""
    assert stored_analysis.key_points == ["单点观点"]
    assert stored_analysis.creator_angles == ["角度"]
    assert stored_analysis.title_suggestions == ["标题一", "标题二"]
    assert stored_analysis.recommendation == ""
    assert stored_analysis.risk_notes == {"notes": ""}
    assert stored_analysis.tags == ["AI", "x" * 40, "工具"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_retries_stale_analyzing_content(monkeypatch):
    async def empty_llm_response(*args, **kwargs):
        return {"raw_response": ""}

    monkeypatch.setattr(analysis, "call_llm_json", empty_llm_response)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="超时分析任务",
                url="https://example.com/stale-analysis-task",
                source_name="测试信源",
                source_type="RSS",
                platform="rsshub",
                status=ContentStatus.ANALYZING,
                updated_at=datetime.utcnow() - timedelta(minutes=ANALYSIS_STALE_MINUTES + 5),
                raw_content="这是一条分析中状态超时的内容，应当重新进入算法分析流程。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_analysis = await db.scalar(select(AiAnalysis).where(AiAnalysis.content_id == 1))
        stored_content = await db.get(ContentItem, 1)

    assert [item.content_id for item in results] == [1]
    assert stored_analysis is not None
    assert stored_content.status == ContentStatus.ANALYZED
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_retries_stale_error_content(monkeypatch):
    async def empty_llm_response(*args, **kwargs):
        return {"raw_response": ""}

    monkeypatch.setattr(analysis, "call_llm_json", empty_llm_response)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="失败后可恢复内容",
                url="https://example.com/stale-error-analysis-task",
                source_name="测试信源",
                source_type="RSS",
                platform="rsshub",
                status=ContentStatus.ERROR,
                updated_at=datetime.utcnow() - timedelta(minutes=ANALYSIS_STALE_MINUTES + 5),
                raw_content="这是一条之前分析失败的内容，冷却后应当重新进入算法分析流程。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_analysis = await db.scalar(select(AiAnalysis).where(AiAnalysis.content_id == 1))
        stored_content = await db.get(ContentItem, 1)

    assert [item.content_id for item in results] == [1]
    assert stored_analysis is not None
    assert stored_content.status == ContentStatus.ANALYZED
    await engine.dispose()


@pytest.mark.asyncio
async def test_analysis_failure_sets_error_cooldown_timestamp(monkeypatch):
    async def failing_llm(*args, **kwargs):
        raise RuntimeError("temporary provider failure")

    monkeypatch.setattr(analysis, "call_llm_json", failing_llm)
    engine, session_factory = await _session_factory()
    old_timestamp = datetime.utcnow() - timedelta(days=1)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="临时失败内容",
                url="https://example.com/temporary-provider-failure",
                status=ContentStatus.PENDING,
                updated_at=old_timestamp,
                raw_content="用于验证失败后不会被立即忙等重试。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_content = await db.get(ContentItem, 1)

    assert results == []
    assert stored_content.status == ContentStatus.ERROR
    assert stored_content.updated_at > old_timestamp
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_skips_fresh_analyzing_content(monkeypatch):
    async def fail_if_llm_runs(*args, **kwargs):
        raise AssertionError("fresh analyzing content should not be retried")

    monkeypatch.setattr(analysis, "call_llm_json", fail_if_llm_runs)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="刚开始分析任务",
                url="https://example.com/fresh-analysis-task",
                status=ContentStatus.ANALYZING,
                updated_at=datetime.utcnow(),
                raw_content="这是一条刚进入分析中的内容，不应被重复抢占。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_content = await db.get(ContentItem, 1)

    assert results == []
    assert stored_content.status == ContentStatus.ANALYZING
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_commits_analyzing_status_before_llm_call(monkeypatch):
    engine, session_factory = await _session_factory()
    observed = {}

    async def fake_analyze_content(content, db):
        async with session_factory() as observer:
            stored_content = await observer.get(ContentItem, content.id)
            observed["status_before_analysis"] = stored_content.status

        analysis_record = AiAnalysis(
            content_id=content.id,
            summary="已分析",
            curation_score=60,
            quality_score=60,
            hot_score=60,
            freshness_score=60,
            creator_score=60,
            viral_score=60,
            risk_score=20,
        )
        db.add(analysis_record)
        content.status = ContentStatus.ANALYZED
        await db.flush()
        return analysis_record

    monkeypatch.setattr(analysis, "analyze_content", fake_analyze_content)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="事务边界测试内容",
                url="https://example.com/analysis-transaction",
                status=ContentStatus.PENDING,
                raw_content="用于验证批量分析不会把外部 LLM 调用包在长写事务中。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_content = await db.get(ContentItem, 1)

    assert observed["status_before_analysis"] == ContentStatus.ANALYZING
    assert [item.content_id for item in results] == [1]
    assert stored_content.status == ContentStatus.ANALYZED
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_invalidates_scoring_cache_after_commit(monkeypatch):
    engine, session_factory = await _session_factory()
    invalidate_scoring_flow_cache()
    cache_payload((24, 160, 80), build_empty_payload(
        hours=24,
        analyzed_total=0,
        window_total=0,
        ignored_count=0,
        limit=160,
        sample_limit=80,
    ))
    observed = {}

    async def fake_analyze_content(content, db):
        analysis_record = AiAnalysis(
            content_id=content.id,
            summary="已分析",
            curation_score=60,
            quality_score=60,
            hot_score=60,
            freshness_score=60,
            creator_score=60,
            viral_score=60,
            risk_score=20,
        )
        db.add(analysis_record)
        content.status = ContentStatus.ANALYZED
        await db.flush()
        observed["cache_before_commit"] = get_cached_scoring_flow_json(hours=24, limit=160) is not None
        return analysis_record

    monkeypatch.setattr(analysis, "analyze_content", fake_analyze_content)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="缓存提交边界测试内容",
                url="https://example.com/analysis-cache-boundary",
                status=ContentStatus.PENDING,
                raw_content="用于验证分析完成后只在提交成功之后刷新算法缓存。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

    assert observed["cache_before_commit"] is True
    assert [item.content_id for item in results] == [1]
    assert get_cached_scoring_flow_json(hours=24, limit=160) is None

    invalidate_scoring_flow_cache()
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_single_commits_analyzing_status_before_llm_call(monkeypatch):
    engine, session_factory = await _session_factory()
    observed = {}

    async def fake_analyze_content(content, db):
        async with session_factory() as observer:
            stored_content = await observer.get(ContentItem, content.id)
            observed["status_before_analysis"] = stored_content.status

        analysis_record = AiAnalysis(
            content_id=content.id,
            summary="已分析",
            curation_score=60,
            quality_score=60,
            hot_score=60,
            freshness_score=60,
            creator_score=60,
            viral_score=60,
            risk_score=20,
        )
        db.add(analysis_record)
        content.status = ContentStatus.ANALYZED
        await db.flush()
        return analysis_record

    monkeypatch.setattr(analyses_api, "analyze_content", fake_analyze_content)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="单条事务边界测试内容",
                url="https://example.com/single-analysis-transaction",
                status=ContentStatus.PENDING,
                raw_content="用于验证单条分析接口不会把外部 LLM 调用包在长写事务中。",
            )
        )
        await db.commit()

        result = await analyses_api.analyze_single(1, db=db)

        stored_content = await db.get(ContentItem, 1)

    assert observed["status_before_analysis"] == ContentStatus.ANALYZING
    assert result.content_id == 1
    assert stored_content.status == ContentStatus.ANALYZED
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_single_invalidates_scoring_cache_after_commit(monkeypatch):
    engine, session_factory = await _session_factory()
    invalidate_scoring_flow_cache()
    cache_payload((24, 160, 80), build_empty_payload(
        hours=24,
        analyzed_total=0,
        window_total=0,
        ignored_count=0,
        limit=160,
        sample_limit=80,
    ))
    observed = {}

    async def fake_analyze_content(content, db):
        analysis_record = AiAnalysis(
            content_id=content.id,
            summary="单条已分析",
            curation_score=60,
            quality_score=60,
            hot_score=60,
            freshness_score=60,
            creator_score=60,
            viral_score=60,
            risk_score=20,
        )
        db.add(analysis_record)
        content.status = ContentStatus.ANALYZED
        await db.flush()
        observed["cache_before_commit"] = get_cached_scoring_flow_json(hours=24, limit=160) is not None
        return analysis_record

    monkeypatch.setattr(analyses_api, "analyze_content", fake_analyze_content)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="单条缓存提交边界测试内容",
                url="https://example.com/single-analysis-cache-boundary",
                status=ContentStatus.PENDING,
                raw_content="用于验证单条分析接口只在提交成功之后刷新算法缓存。",
            )
        )
        await db.commit()

        result = await analyses_api.analyze_single(1, db=db)

    assert observed["cache_before_commit"] is True
    assert result.content_id == 1
    assert get_cached_scoring_flow_json(hours=24, limit=160) is None

    invalidate_scoring_flow_cache()
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_single_failure_sets_error_cooldown_timestamp(monkeypatch):
    async def failing_analyze_content(content, db):
        raise RuntimeError("temporary single analysis failure")

    monkeypatch.setattr(analyses_api, "analyze_content", failing_analyze_content)
    engine, session_factory = await _session_factory()
    old_timestamp = datetime.utcnow() - timedelta(days=1)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="单条临时失败内容",
                url="https://example.com/single-temporary-failure",
                status=ContentStatus.PENDING,
                updated_at=old_timestamp,
                raw_content="用于验证单条分析接口失败后不会被后台队列立即忙等重试。",
            )
        )
        await db.commit()

        with pytest.raises(Exception):
            await analyses_api.analyze_single(1, db=db)

        stored_content = await db.get(ContentItem, 1)

    assert stored_content.status == ContentStatus.ERROR
    assert stored_content.updated_at > old_timestamp
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_skips_sqlite_locked_item_without_crashing(monkeypatch):
    async def locked_write(*args, **kwargs):
        raise OperationalError("UPDATE content_items", {}, Exception("database is locked"))

    monkeypatch.setattr(analysis, "retry_sqlite_locked", locked_write)
    engine, session_factory = await _session_factory()

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="数据库锁测试内容",
                url="https://example.com/sqlite-locked",
                status=ContentStatus.PENDING,
                raw_content="用于验证 SQLite 锁定时分析批处理不会因为回滚后的 ORM 属性访问而崩溃。",
            )
        )
        await db.commit()

        results = await analysis.analyze_batch([1], db)

        stored_content = await db.get(ContentItem, 1)

    assert results == []
    assert stored_content.status == ContentStatus.PENDING
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_batch_concurrent_runs_items_in_parallel(monkeypatch):
    engine, session_factory = await _session_factory()
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def fake_analyze_content(content, db):
        nonlocal active, max_active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        async with lock:
            active -= 1

        analysis_record = AiAnalysis(
            content_id=content.id,
            summary="已分析",
            curation_score=60,
            quality_score=60,
            hot_score=60,
            freshness_score=60,
            creator_score=60,
            viral_score=60,
            risk_score=20,
        )
        db.add(analysis_record)
        content.status = ContentStatus.ANALYZED
        await db.flush()
        return analysis_record

    monkeypatch.setattr(analysis, "analyze_content", fake_analyze_content)

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=item_id,
                title=f"并发分析内容 {item_id}",
                url=f"https://example.com/concurrent-{item_id}",
                status=ContentStatus.PENDING,
                raw_content="用于验证并发分析 worker 不共享 session，且 LLM 调用可以重叠执行。",
            )
            for item_id in range(1, 5)
        ])
        await db.commit()

    results = await analysis.analyze_batch_concurrent(
        [1, 2, 3, 4],
        concurrency=2,
        session_factory=session_factory,
    )

    async with session_factory() as db:
        statuses = {
            item.id: item.status
            for item in (await db.execute(select(ContentItem))).scalars().all()
        }

    assert [item.content_id for item in results] == [1, 2, 3, 4]
    assert max_active == 2
    assert statuses == {
        1: ContentStatus.ANALYZED,
        2: ContentStatus.ANALYZED,
        3: ContentStatus.ANALYZED,
        4: ContentStatus.ANALYZED,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_post_sync_drain_processes_backlog_and_stale_analyzing(monkeypatch):
    engine, session_factory = await _session_factory()
    now = datetime.utcnow()

    monkeypatch.setattr(scheduler_module, "async_session", session_factory)

    async def fake_analyze_batch(content_ids, **_kwargs):
        results = []
        async with session_factory() as db:
            for content_id in content_ids:
                content = await db.get(ContentItem, content_id)
                if content is None:
                    continue
                analysis_record = AiAnalysis(
                    content_id=content.id,
                    summary="已分析",
                    curation_score=60,
                    quality_score=60,
                    hot_score=60,
                    freshness_score=60,
                    creator_score=60,
                    viral_score=60,
                    risk_score=20,
                )
                db.add(analysis_record)
                content.status = ContentStatus.ANALYZED
                await db.flush()
                results.append(analysis_record)
            await db.commit()
        return results

    monkeypatch.setattr(scheduler_module, "analyze_batch_concurrent", fake_analyze_batch)

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=1,
                title="最新待分析一",
                url="https://example.com/pending-1",
                status=ContentStatus.PENDING,
                crawled_at=now,
            ),
            ContentItem(
                id=2,
                title="最新待分析二",
                url="https://example.com/pending-2",
                status=ContentStatus.PENDING,
                crawled_at=now - timedelta(minutes=1),
            ),
            ContentItem(
                id=3,
                title="超时分析中内容",
                url="https://example.com/stale-analyzing",
                status=ContentStatus.ANALYZING,
                crawled_at=now - timedelta(minutes=2),
                updated_at=now - timedelta(minutes=ANALYSIS_STALE_MINUTES + 1),
            ),
        ])
        await db.commit()

    stats = await scheduler_module._drain_pending_analysis(
        batch_size=2,
        time_budget_seconds=120,
    )

    async with session_factory() as db:
        statuses = {
            item.id: item.status
            for item in (await db.execute(select(ContentItem))).scalars().all()
        }

    assert stats == {
        "attempted": 3,
        "analyzed": 3,
        "batches": 2,
        "remaining": False,
        "stop_reason": "no_pending",
    }
    assert statuses == {
        1: ContentStatus.ANALYZED,
        2: ContentStatus.ANALYZED,
        3: ContentStatus.ANALYZED,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_post_sync_drain_releases_claims_after_batch_timeout(monkeypatch):
    engine, session_factory = await _session_factory()
    monkeypatch.setattr(scheduler_module, "async_session", session_factory)

    async def fake_analyze_batch(content_ids, **_kwargs):
        async with session_factory() as db:
            for content_id in content_ids:
                content = await db.get(ContentItem, content_id)
                if content is not None:
                    content.status = ContentStatus.ANALYZING
            await db.commit()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(scheduler_module, "analyze_batch_concurrent", fake_analyze_batch)

    async with session_factory() as db:
        db.add_all([
            ContentItem(
                id=1,
                title="超时释放一",
                url="https://example.com/timeout-release-1",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow(),
            ),
            ContentItem(
                id=2,
                title="超时释放二",
                url="https://example.com/timeout-release-2",
                status=ContentStatus.PENDING,
                crawled_at=datetime.utcnow() - timedelta(minutes=1),
            ),
        ])
        await db.commit()

    stats = await scheduler_module._drain_pending_analysis(
        batch_size=2,
        time_budget_seconds=120,
    )

    async with session_factory() as db:
        statuses = {
            item.id: item.status
            for item in (await db.execute(select(ContentItem))).scalars().all()
        }

    assert stats == {
        "attempted": 2,
        "analyzed": 0,
        "batches": 1,
        "remaining": True,
        "stop_reason": "batch_timeout",
    }
    assert statuses == {
        1: ContentStatus.PENDING,
        2: ContentStatus.PENDING,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_post_sync_pipeline_request_only_when_new_content(monkeypatch):
    created = []

    async def fake_pipeline():
        await asyncio.Event().wait()

    class FakeLoop:
        def create_task(self, coroutine):
            task = asyncio.create_task(coroutine)
            created.append(task)
            return task

    scheduler_module._post_sync_task = None
    scheduler_module._post_sync_rerun_requested = False
    monkeypatch.setattr(scheduler_module, "_run_post_sync_pipeline", fake_pipeline)
    monkeypatch.setattr(scheduler_module.asyncio, "get_running_loop", lambda: FakeLoop())

    assert scheduler_module._request_post_sync_pipeline({"new": 0}) is False
    assert scheduler_module._request_post_sync_pipeline({"new": "bad"}) is False
    assert scheduler_module._request_post_sync_pipeline({"new": 2}) is True
    assert scheduler_module._request_post_sync_pipeline({"new": 3}) is True
    assert len(created) == 1
    assert scheduler_module._post_sync_rerun_requested is True

    created[0].cancel()
    await asyncio.gather(created[0], return_exceptions=True)
    scheduler_module._post_sync_task = None
    scheduler_module._post_sync_rerun_requested = False


@pytest.mark.asyncio
async def test_post_sync_pipeline_task_reference_clears_when_done(monkeypatch):
    async def fake_pipeline():
        return None

    class FakeLoop:
        def create_task(self, coroutine):
            return asyncio.create_task(coroutine)

    scheduler_module._post_sync_task = None
    scheduler_module._post_sync_rerun_requested = False
    monkeypatch.setattr(scheduler_module, "_run_post_sync_pipeline", fake_pipeline)
    monkeypatch.setattr(scheduler_module.asyncio, "get_running_loop", lambda: FakeLoop())

    assert scheduler_module._request_post_sync_pipeline({"new": 1}) is True
    assert scheduler_module._post_sync_task is not None
    await scheduler_module._post_sync_task
    await asyncio.sleep(0)

    assert scheduler_module._post_sync_task is None


@pytest.mark.asyncio
async def test_sync_single_source_requests_post_sync_pipeline_for_new_content(monkeypatch):
    engine, session_factory = await _session_factory()
    requested = []

    monkeypatch.setattr(scheduler_module, "async_session", session_factory)

    async def fake_ingest_from_source(source, db):
        return {"fetched": 3, "new": 2, "duplicates": 1}

    def fake_request_post_sync_pipeline(stats):
        requested.append(stats)
        return True

    monkeypatch.setattr(scheduler_module, "ingest_from_source", fake_ingest_from_source)
    monkeypatch.setattr(scheduler_module, "_request_post_sync_pipeline", fake_request_post_sync_pipeline)

    async with session_factory() as db:
        db.add(
            Source(
                id=1,
                name="测试信源",
                source_type="RSS",
                url="https://example.com/rss.xml",
                enabled=True,
            )
        )
        await db.commit()

    await scheduler_module._sync_single_source(1)

    assert requested == [{"fetched": 3, "new": 2, "duplicates": 1}]
    await engine.dispose()


@pytest.mark.asyncio
async def test_source_sort_order_backfill_skips_sqlite_lock(monkeypatch):
    async def locked_backfill(*args, **kwargs):
        raise OperationalError("UPDATE sources", {}, Exception("database is locked"))

    monkeypatch.setattr(app_main, "database_profile", SimpleNamespace(is_sqlite=True))
    monkeypatch.setattr(app_main, "retry_sqlite_locked", locked_backfill)
    engine, session_factory = await _session_factory()

    async with engine.begin() as conn:
        await app_main.ensure_source_sort_order_column(conn)

    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_upgrade_schema_skips_non_sqlite_backends(monkeypatch):
    class NoSqlConn:
        async def execute(self, statement):
            raise AssertionError(f"non-SQLite backend should not execute SQLite upgrade SQL: {statement}")

    monkeypatch.setattr(app_main, "database_profile", SimpleNamespace(is_sqlite=False))

    await app_main.ensure_sqlite_upgrade_schema(NoSqlConn())


@pytest.mark.asyncio
async def test_sqlite_upgrade_schema_runs_helpers_for_sqlite(monkeypatch):
    calls = []

    def helper(name):
        async def _run(_conn):
            calls.append(name)
        return _run

    monkeypatch.setattr(app_main, "database_profile", SimpleNamespace(is_sqlite=True))
    monkeypatch.setattr(app_main, "ensure_source_sort_order_column", helper("source_sort_order"))
    monkeypatch.setattr(app_main, "ensure_daily_report_version_schema", helper("daily_report_version"))
    monkeypatch.setattr(app_main, "ensure_llm_call_logs_schema", helper("llm_call_logs"))
    monkeypatch.setattr(app_main, "ensure_llm_models_route_schema", helper("llm_models_route"))
    monkeypatch.setattr(app_main, "ensure_performance_indexes", helper("performance_indexes"))
    monkeypatch.setattr(app_main, "ensure_content_status_values", helper("content_status_values"))
    monkeypatch.setattr(app_main, "ensure_favorite_items_schema", helper("favorite_items"))
    monkeypatch.setattr(app_main, "ensure_user_auth_schema", helper("user_auth"))
    monkeypatch.setattr(app_main, "ensure_user_integrations_schema", helper("user_integrations"))
    monkeypatch.setattr(app_main, "ensure_user_feedback_schema", helper("user_feedback"))
    monkeypatch.setattr(app_main, "ensure_product_feedback_schema", helper("product_feedback"))

    await app_main.ensure_sqlite_upgrade_schema(object())

    assert calls == [
        "source_sort_order",
        "daily_report_version",
        "llm_call_logs",
        "llm_models_route",
        "performance_indexes",
        "content_status_values",
        "favorite_items",
        "user_auth",
        "user_integrations",
        "user_feedback",
        "product_feedback",
    ]


@pytest.mark.asyncio
async def test_user_feedback_schema_upgrade_adds_user_scope(monkeypatch):
    monkeypatch.setattr(app_main, "database_profile", SimpleNamespace(is_sqlite=True))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL DEFAULT 1,
                feedback_type VARCHAR(12) NOT NULL,
                score_delta FLOAT NOT NULL,
                comment TEXT,
                created_at DATETIME NOT NULL
            )
        """))
        await conn.execute(text("""
            INSERT INTO user_feedback (content_id, user_id, feedback_type, score_delta, created_at)
            VALUES
                (1, 1, 'like', 10.0, '2026-01-01 00:00:00'),
                (1, 1, 'dislike', -15.0, '2026-01-02 00:00:00'),
                (1, 2, 'like', 10.0, '2026-01-01 00:00:00')
        """))

        await app_main.ensure_user_feedback_schema(conn)

        columns = {
            row[1]: row
            for row in (await conn.execute(text("PRAGMA table_info(user_feedback)"))).fetchall()
        }
        indexes = {
            row[1]
            for row in (await conn.execute(text("PRAGMA index_list(user_feedback)"))).fetchall()
        }
        feedback_rows = (
            await conn.execute(text(
                "SELECT content_id, user_id, feedback_type "
                "FROM user_feedback ORDER BY user_id"
            ))
        ).fetchall()

    assert "user_id" in columns
    assert columns["user_id"][3] == 1
    assert columns["user_id"][4] == "1"
    assert feedback_rows == [(1, 1, "dislike"), (1, 2, "like")]
    assert "uq_user_feedback_content_user" in indexes
    assert "ix_user_feedback_content_user" in indexes
    assert "ix_user_feedback_user_created" in indexes
    await engine.dispose()
