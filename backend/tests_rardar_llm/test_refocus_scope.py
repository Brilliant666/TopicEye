"""Paused product work fails before locks, writes or Provider dispatch."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, rardar
from app.core.config import settings
from app.core.rardar_scope import RardarModulePaused, require_module_execution


@pytest.fixture
def rardar_mode(monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", True)


def test_scope_leaves_shared_work_and_standalone_topiceye(monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", True)
    for module in ("news", "discover", "candidates", "watchlist"):
        with pytest.raises(RardarModulePaused, match=f"rardar_{module}_paused"):
            require_module_execution(module)
    for module in ("find", "today", "historical", "project_materials"):
        require_module_execution(module)
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", False)
    require_module_execution("news")
    require_module_execution("discover")


@pytest.mark.asyncio
async def test_news_web_and_cli_services_do_not_touch_storage(rardar_mode):
    from app.services import rardar_hotspot_news, rardar_news_operations, rardar_news_quickread

    for call in (
        lambda: rardar_hotspot_news.refresh_hotspot_news(None),
        lambda: rardar_news_quickread.enhance_hotspot_news(None),
        lambda: rardar_news_operations.start_operation(None, user_id=1),
    ):
        with pytest.raises(RardarModulePaused, match="rardar_news_paused"):
            await call()


@pytest.mark.asyncio
async def test_generic_source_ingestion_cannot_bypass_news_pause(rardar_mode):
    from fastapi import HTTPException

    from app.api.v1.sources import _check_product_source_sync
    from app.services.content_pipeline import ingest_from_source

    with pytest.raises(RardarModulePaused):
        await ingest_from_source(SimpleNamespace(platform="rardar_hotspot_news"), None)
    with pytest.raises(HTTPException) as error:
        _check_product_source_sync("rardar_hotspot_news")
    assert error.value.status_code == 409
    _check_product_source_sync("rss")


@pytest.mark.asyncio
async def test_generic_analysis_cannot_spend_on_retained_rardar_news(rardar_mode):
    from app.services.analysis import analyze_content

    with pytest.raises(RardarModulePaused, match="rardar_news_paused"):
        await analyze_content(SimpleNamespace(platform="rardar_hotspot_news"), None)


@pytest.mark.asyncio
async def test_rardar_startup_does_not_register_generic_content_workers(rardar_mode, monkeypatch):
    from unittest.mock import MagicMock

    from app import scheduler as module

    scheduler = MagicMock(running=False)
    monkeypatch.setattr(module, "scheduler", scheduler)
    monkeypatch.setattr(settings, "RARDAR_DAILY_OPERATIONS_ENABLED", True)
    catchup = AsyncMock()
    monkeypatch.setattr(module, "_rardar_startup_catchup", catchup)
    module.start_scheduler()
    await asyncio.sleep(0)
    assert [call.kwargs["id"] for call in scheduler.add_job.call_args_list] == ["rardar_daily_operations"]
    catchup.assert_awaited_once()


@pytest.mark.asyncio
async def test_discover_entrypoints_cannot_resume_backlog(rardar_mode, tmp_path):
    from app.services import rardar_discover_operations, rardar_product
    from scripts import rebuild_rardar_discover_selection, rebuild_rardar_discover_serving

    for call in (
        lambda: rardar_discover_operations.prepare_operation(None, user_id=1),
        lambda: rardar_discover_operations.start_operation(None, user_id=1),
        lambda: rebuild_rardar_discover_selection.rebuild(tmp_path),
        lambda: rebuild_rardar_discover_selection.rebuild_period(tmp_path),
        lambda: rardar_product.explain_discover_project_by_id(1, "retained"),
    ):
        with pytest.raises(RardarModulePaused, match="rardar_discover_paused"):
            await call()
    with pytest.raises(RardarModulePaused):
        rebuild_rardar_discover_serving.rebuild(tmp_path)
    assert not list(tmp_path.iterdir())


def test_authorized_paused_posts_have_explicit_result(rardar_mode, monkeypatch):
    app = FastAPI()
    app.include_router(rardar.router)
    app.dependency_overrides[auth.get_current_admin_user] = lambda: SimpleNamespace(id=1)
    with TestClient(app) as client:
        for path, payload, module in (
            ("hotspot-news/operations", {"action": "refresh", "requestId": str(uuid4())}, "news"),
            ("discover/operations/prepare", {"requestId": str(uuid4())}, "discover"),
            ("discover/operations", {"requestId": str(uuid4()), "planId": str(uuid4())}, "discover"),
        ):
            response = client.post(f"/rardar/{path}", json=payload, headers={"Authorization": "Bearer test"})
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == f"rardar_{module}_paused"


@pytest.mark.asyncio
async def test_daily_scheduler_dispatches_refocus_not_old_backlog(rardar_mode, monkeypatch):
    import sys

    from app.services import rardar_daily_operations as daily

    refocus = AsyncMock(return_value={"status": "completed", "news": "paused", "discover": "paused"})
    monkeypatch.setitem(sys.modules, "app.services.rardar_trending", SimpleNamespace(run_daily_refocus=refocus))
    old = AsyncMock(side_effect=AssertionError("retired pipeline called"))
    for name in ("_today", "_news_refresh", "_inventory", "_discover", "_news_enhance"):
        monkeypatch.setattr(daily, name, old)
    assert (await daily.run_daily_operations())["discover"] == "paused"
    refocus.assert_awaited_once()
    old.assert_not_called()
