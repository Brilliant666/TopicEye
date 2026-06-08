from datetime import datetime, timedelta
from types import SimpleNamespace
import asyncio

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.exc import OperationalError
from sqlalchemy import select
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
from app import scheduler as scheduler_module


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
        ])
        await db.commit()

        pending = await ContentRepo(db).list_pending_for_analysis(limit=10, hours=24)

    assert [item.id for item in pending] == [4, 2]
    await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_pending_defaults_to_background_queue(monkeypatch):
    async def fail_if_sync_analysis_runs(*args, **kwargs):
        raise AssertionError("pending endpoint should not analyze synchronously by default")

    monkeypatch.setattr(analyses_api, "analyze_batch", fail_if_sync_analysis_runs)
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

        result = await analyses_api.analyze_all_pending(
            limit=10,
            hours=24,
            sync=False,
            background_tasks=BackgroundTasks(),
            db=db,
        )

    assert result["mode"] == "background"
    assert result["queued_ids"] == [1]
    assert result["analyzed_ids"] == []
    assert result["hours"] == 24
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

    async def fake_analyze_batch(content_ids):
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
        "product_feedback",
    ]
