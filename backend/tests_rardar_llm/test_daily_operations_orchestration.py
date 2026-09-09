from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import rardar_daily_operations as daily
from app.services.llm import daily_provider_budget as budget
from app.services.llm.provider_budget import atomic, file_lock


@pytest.mark.asyncio
async def test_inventory_serializes_real_candidate_universe_summary(tmp_path, monkeypatch):
    from dataclasses import asdict
    from unittest.mock import Mock

    from app.integrations.rardar import selection_source, selection_source_local, serving
    from app.integrations.rardar.selection import build_candidate_universe
    from tests_rardar_selection.source_fixture import copy_and_load

    target, source = copy_and_load(tmp_path)
    expected, summary = build_candidate_universe(source)
    monkeypatch.setattr(
        serving.ServingProjectionLoader, "load_today_with_etag",
        lambda _self: (SimpleNamespace(generationId=source.today_generation_id), "fixture-etag"),
    )
    built = object()
    monkeypatch.setattr(selection_source_local, "build_selection_source_from_today_mirror", Mock(return_value=built))
    install = Mock()
    monkeypatch.setattr(selection_source, "install_selection_source", install)
    monkeypatch.setattr(
        selection_source.SelectionSourceAdapter, "from_config",
        lambda _path: SimpleNamespace(load=lambda: source),
    )
    result, actual_source, universe = await daily._inventory(target)
    assert actual_source is source
    assert universe == expected
    assert result["universe"] == asdict(summary)
    assert result["managedCandidateCount"] == len(expected)
    assert result["checked"] == len(source.captures[-1]["observations"])
    install.assert_called_once_with(target, built)


@pytest.mark.asyncio
async def test_midnight_manual_catchup_does_not_consume_next_scheduled_cycle(tmp_path, monkeypatch):
    class Clock(datetime):
        instant = datetime(2026, 9, 9, 16, 1, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz) if tz else cls.instant

    monkeypatch.setattr(daily, "datetime", Clock)
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path)
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(budget, "daily_execution_budget", AsyncMock(return_value=None))
    today = AsyncMock(return_value={"status": "unchanged"})
    monkeypatch.setattr(daily, "_today", today)
    monkeypatch.setattr(daily, "_news_refresh", AsyncMock(return_value={"status": "completed"}))
    monkeypatch.setattr(daily, "_inventory", AsyncMock(return_value=({"status": "checked"}, None, [])))
    monkeypatch.setattr(daily, "_public_materials", AsyncMock(return_value={"status": "completed"}))
    before = await daily.run_daily_operations()
    assert before["date"] == "2026-09-09"
    Clock.instant = datetime(2026, 9, 10, 0, 31, tzinfo=UTC)
    after = await daily.run_daily_operations()
    assert after["date"] == "2026-09-10"
    assert after["attempts"] == 1
    assert today.await_count == 2


@pytest.mark.asyncio
async def test_discover_traverses_all_managed_candidates_not_research_limit(tmp_path, monkeypatch):
    from app.integrations.rardar import selection, selection_serving
    from app.services import rardar_discover_operations as manual, rardar_llm_control
    from scripts import rebuild_rardar_discover_selection as builder

    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    ledger = budget.daily_ledger(100)
    monkeypatch.setattr(manual, "latest_operation", lambda: None)
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    source = SimpleNamespace(
        source_observation_set_id="source", manifest_sha256="manifest", today_generation_id="today"
    )
    universe = [SimpleNamespace(githubRepositoryId=index) for index in range(1, 126)]
    artifacts = {}
    calls = []

    async def rebuild(_target, **kwargs):
        ids = kwargs["process_candidate_ids"]
        calls.extend(ids)
        identifier = f"generation-{len(artifacts)}"
        artifacts[identifier] = SimpleNamespace(
            assessments=[SimpleNamespace(gate=object(), valueFailureCode=None, copyFailureCode=None) for _ in ids],
            publishedCount=0,
            selectionGenerationId=identifier,
            inputDigest="binding",
        )
        return {"selectionGenerationId": identifier, "currentChanged": False}

    class Loader:
        def __init__(self, _target):
            pass

        def validate_generation(self, identifier=None):
            return artifacts[identifier] if identifier else list(artifacts.values())[-1]

    monkeypatch.setattr(builder, "rebuild", rebuild)
    monkeypatch.setattr(selection_serving, "SelectionServingLoader", Loader)
    monkeypatch.setattr(selection, "selection_input_digest", lambda *_a, **_k: "binding")
    progress = {}
    result = await daily._discover(tmp_path, source, universe, ledger, progress, lambda: None)
    assert sorted(calls) == list(range(1, 126))
    assert len(calls) == len(set(calls))
    assert result["completed"] == 125
    assert result["unfinished"] == 0
    # A repeated orchestration checks saved artifacts and spends no new work.
    repeated = await daily._discover(tmp_path, source, universe, ledger, progress, lambda: None)
    assert len(calls) == 125
    assert repeated["reused"] == 125
    assert ledger.snapshot()["attempted"] == 0
    artifacts.clear()
    with pytest.raises(KeyError):
        await daily._discover(tmp_path, source, universe, ledger, progress, lambda: None)
    assert len(calls) == 125  # Progress cannot authorize a missing/corrupt artifact.


@pytest.mark.asyncio
async def test_failed_module_isolated_and_repeat_run_resumes_without_repeating_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    monkeypatch.setattr(budget, "daily_execution_budget", AsyncMock(return_value=(ledger, "project_profile")))
    today = AsyncMock(return_value={"status": "completed"})
    news = AsyncMock(return_value={"status": "completed"})
    discover = AsyncMock(side_effect=[ValueError("must not leak"), {"status": "completed", "processed": 6}])
    enhance = AsyncMock(return_value={"status": "completed", "cached": 4})
    profile = AsyncMock(return_value={"status": "completed", "cached": 20})
    monkeypatch.setattr(daily, "_today", today)
    monkeypatch.setattr(daily, "_news_refresh", news)
    monkeypatch.setattr(daily, "_discover", discover)
    monkeypatch.setattr(daily, "_news_enhance", enhance)
    monkeypatch.setattr(daily, "_today_profiles", profile)
    monkeypatch.setattr(daily, "_inventory", AsyncMock(return_value=({"status": "checked"}, object(), [])))
    monkeypatch.setattr(daily, "_public_materials", AsyncMock(return_value={"status": "completed"}))
    first = await daily.run_daily_operations()
    assert first["status"] == "partial"
    assert first["modules"]["discover"] == {"status": "failed", "errorCode": "ValueError"}
    assert first["modules"]["news_enhance"]["status"] == "completed"
    assert first["modules"]["today_profiles"]["status"] == "completed"
    second = await daily.run_daily_operations()
    assert second["status"] == "completed"
    assert second["attempts"] == 2
    third = await daily.run_daily_operations()
    assert third["status"] == "skipped"
    assert third["reason"] == "already_completed"
    assert today.await_count == news.await_count == 1
    assert discover.await_count == 2
    assert ledger.snapshot()["attempted"] == 0
    assert "must not leak" not in (tmp_path / "operations" / "latest.json").read_text()


@pytest.mark.asyncio
async def test_no_budget_keeps_zero_model_modules_and_retry_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(budget, "daily_execution_budget", AsyncMock(return_value=None))
    today = AsyncMock(return_value={"status": "completed"})
    news = AsyncMock(return_value={"status": "completed"})
    model = AsyncMock(side_effect=AssertionError("No model work without configured budget"))
    monkeypatch.setattr(daily, "_today", today)
    monkeypatch.setattr(daily, "_news_refresh", news)
    monkeypatch.setattr(daily, "_discover", model)
    monkeypatch.setattr(daily, "_news_enhance", model)
    monkeypatch.setattr(daily, "_today_profiles", model)
    monkeypatch.setattr(daily, "_inventory", AsyncMock(return_value=({"status": "checked"}, object(), [])))
    monkeypatch.setattr(daily, "_public_materials", AsyncMock(return_value={"status": "completed"}))
    for _ in range(daily.MAX_DAILY_ATTEMPTS):
        result = await daily.run_daily_operations()
        assert result["status"] == "partial"
    assert (await daily.run_daily_operations())["reason"] == "daily_retry_limit"
    assert today.await_count == news.await_count == 1
    assert model.await_count == 0


@pytest.mark.asyncio
async def test_news_progress_does_not_bypass_material_prompt_route_cache_validation(tmp_path, monkeypatch):
    from app.services import rardar_hotspot_news, rardar_news_quickread

    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    item = SimpleNamespace(id=1, model_dump=lambda **_: {"title": "fixed"})

    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(daily, "async_session", session)
    monkeypatch.setattr(
        rardar_hotspot_news,
        "load_hotspot_news",
        AsyncMock(return_value=(SimpleNamespace(items=[item], totalPages=1), None)),
    )
    enhance = AsyncMock(
        return_value=SimpleNamespace(
            considered=1,
            enhanced=0,
            cacheHits=1,
            alreadyChinese=0,
            failed=0,
            status="completed",
        )
    )
    monkeypatch.setattr(rardar_news_quickread, "enhance_hotspot_news", enhance)
    progress = {"1": {"identity": daily._digest({"title": "fixed"}), "complete": True}}
    result = await daily._news_enhance(ledger, progress, lambda: None)
    assert enhance.await_count == 1
    assert result["cached"] == 1
    monkeypatch.setattr(daily, "_same_budget_day", lambda _: False)
    expired = await daily._news_enhance(ledger, progress, lambda: None)
    assert expired["reason"] == "calendar_day_changed"
    assert enhance.await_count == 1


@pytest.mark.asyncio
async def test_cancellation_saved_and_dead_process_status_is_read_only(tmp_path, monkeypatch):
    root = tmp_path / "operations"
    monkeypatch.setattr(daily, "operation_root", lambda: root)
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    monkeypatch.setattr(daily, "_today", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await daily.run_daily_operations()
    status = daily.latest_status()
    assert status["status"] == "interrupted"
    assert status["completedAt"]
    # Simulate SIGKILL: the durable record says running, but its lock is free.
    atomic(root / "latest.json", {"status": "running", "date": "2026-09-09"})
    before = (root / "latest.json").read_bytes()
    assert daily.latest_status()["status"] == "interrupted"
    assert (root / "latest.json").read_bytes() == before
    with file_lock(root / "writer.lock", blocking=False):
        assert daily.latest_status()["status"] == "running"


@pytest.mark.asyncio
async def test_failed_discover_prefix_does_not_starve_later_candidates(tmp_path, monkeypatch):
    from app.integrations.rardar import selection
    from app.services import rardar_discover_operations as manual, rardar_llm_control
    from scripts import rebuild_rardar_discover_selection as builder

    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    ledger = budget.daily_ledger(100)
    monkeypatch.setattr(manual, "latest_operation", lambda: None)
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    monkeypatch.setattr(selection, "selection_input_digest", lambda *_a, **_k: "binding")
    source = SimpleNamespace(
        source_observation_set_id="source", manifest_sha256="manifest", today_generation_id="today"
    )
    universe = [SimpleNamespace(githubRepositoryId=index) for index in range(1, 19)]
    attempts = []

    async def fail(_target, **kwargs):
        attempts.append(kwargs["process_candidate_ids"])
        raise TimeoutError("simulated failure")

    monkeypatch.setattr(builder, "rebuild", fail)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            # Empty progress also models the next operation cycle: cursor is
            # durable, but no historic result is rebound or marked complete.
            await daily._discover(tmp_path, source, universe, ledger, {}, lambda: None)
    assert attempts == [tuple(range(1, 7)), tuple(range(7, 13)), tuple(range(13, 19))]
    assert ledger.snapshot()["attempted"] == 0


@pytest.mark.asyncio
async def test_exhausting_first_module_rotates_next_days_first_opportunity(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(daily.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "facts"))
    available = {"remaining": 100}
    ledger = SimpleNamespace(
        task_id="isolated",
        snapshot=lambda: {
            "remaining": available["remaining"],
            "attempted": 100 - available["remaining"],
            "limit": 100,
        },
    )
    monkeypatch.setattr(budget, "daily_execution_budget", AsyncMock(return_value=(ledger, "project_profile")))
    monkeypatch.setattr(daily, "_today", AsyncMock(return_value={"status": "completed"}))
    monkeypatch.setattr(daily, "_news_refresh", AsyncMock(return_value={"status": "completed"}))
    monkeypatch.setattr(daily, "_inventory", AsyncMock(return_value=({"status": "checked"}, object(), [])))
    monkeypatch.setattr(daily, "_public_materials", AsyncMock(return_value={"status": "completed"}))
    firsts = []

    def action(name):
        async def consume(*_args):
            if available["remaining"]:
                firsts.append(name)
                available["remaining"] = 0
            return {"status": "partial"}

        return consume

    monkeypatch.setattr(daily, "_discover", action("discover"))
    monkeypatch.setattr(daily, "_news_enhance", action("news"))
    monkeypatch.setattr(daily, "_today_profiles", action("today"))
    current = datetime(2026, 9, 10, 4, tzinfo=UTC)

    class Clock:
        @staticmethod
        def now(_zone):
            return current

    monkeypatch.setattr(daily, "datetime", Clock)
    for _ in range(3):
        available["remaining"] = 100
        assert (await daily.run_daily_operations())["status"] == "partial"
        # Same-day catch-up has no replenishment.
        assert (await daily.run_daily_operations())["status"] == "partial"
        current += timedelta(days=1)
    assert len(firsts) == 3
    assert set(firsts) == {"discover", "news", "today"}


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid, expected", [(0, "completed"), (1, "partial")])
async def test_managed_cache_diagnostics_are_not_project_failures(tmp_path, monkeypatch, invalid, expected):
    from app.services import rardar_managed_materials, rardar_project_evidence

    monkeypatch.setattr(rardar_project_evidence, "_persistent_root", lambda: tmp_path / "materials")
    monkeypatch.setattr(
        rardar_managed_materials,
        "inventory_managed_materials",
        lambda _: {
            "projects": [],
            "failed": invalid,
            "invalidCacheRecords": invalid,
            "incompatibleCacheRecords": 5,
            "invalidCurrentArtifact": 0,
            "unresolvedProjectCount": 0,
        },
    )
    result = await daily._public_materials({}, lambda: None)
    assert result["status"] == expected
    assert result["checked"] == result["failed"] == 0
    assert result["incompatibleCacheRecords"] == 5
    assert result["invalidCacheRecords"] == invalid
