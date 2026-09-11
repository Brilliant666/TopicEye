"""Shared real material-work entry; synthetic repository IO and Provider responses."""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services import rardar_llm_control, rardar_trending as service
from app.services.llm import daily_provider_budget


@pytest.fixture
def work(tmp_path, monkeypatch):
    (tmp_path / "trending-boards").mkdir()
    today = ["current/one", "current/two", "current/three", "current/four"]
    history = ["history/one", "history/two", "history/three", "history/four"]
    projects = [
        {"repository": repo, "projectId": service.project_id_for_repository(repo), "profile": None, "totalStars": 10}
        for repo in today + history
    ]
    monkeypatch.setattr(service, "saved_materials", lambda _: {})
    monkeypatch.setattr(
        service, "_history_with_materials", lambda *_: {"projects": projects, "generationId": "fixture"}
    )
    monkeypatch.setattr(
        service, "load_snapshot", lambda _: {"projects": [p for p in projects if p["repository"] in today]}
    )
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 3)
    ledger = SimpleNamespace(snapshot=lambda: {"remaining": 80})
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", AsyncMock(return_value=(ledger, {})))
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="unchanged-route"))
    monkeypatch.setattr(service, "project_material", lambda *_: {"profile": {"summary": "fixture"}})
    called = []

    async def collect(_target, project, _generation, _client, _route):
        called.append(project["repository"])
        project["profile"] = {"summary": "fixture", "generatedAt": datetime.now(UTC).isoformat()}
        project["displayProfile"] = {"officialSummaryZh": "fixture"}
        return SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")

    monkeypatch.setattr(service, "_collect_project_material", collect)
    return SimpleNamespace(target=tmp_path, today=today, history=history, projects=projects, calls=called)


@pytest.mark.asyncio
async def test_used_historical_admissions_do_not_stop_today_and_resume_same_day(work):
    progress = {"attempts": {repo: 1 for repo in work.history[:3]}}
    first = await service.historical_work(work.target, progress, lambda: None)
    assert first["processed"] > 0
    assert work.calls and work.calls[0] in work.today
    assert "history/four" not in work.calls
    while any(p["profile"] is None for p in work.projects if p["repository"] in work.today):
        await service.historical_work(work.target, progress, lambda: None)
    assert set(work.today) <= set(work.calls)
    assert len(work.calls) == len(set(work.calls))
    assert progress["attempts"] == {repo: 1 for repo in work.history[:3]}


@pytest.mark.asyncio
async def test_paid_cooperative_continuations_are_not_real_failures_or_new_projects(work, monkeypatch):
    work.projects[:] = work.projects[:1]
    calls = 0

    async def collect(*_args):
        nonlocal calls
        calls += 1
        daily_provider_budget._work_slice.get().used_requests += 1  # simulated reservation only
        if calls <= 3:
            raise daily_provider_budget.ProviderWorkYield("work_slice_exhausted")
        work.projects[0]["profile"] = {"summary": "fixture", "generatedAt": datetime.now(UTC).isoformat()}
        return SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    for _ in range(3):
        result = await service.historical_work(work.target, progress, lambda: None)
        assert result["status"] == "pending"
        assert result["failed"] == 0
    final = await service.historical_work(work.target, progress, lambda: None)
    assert final["processed"] == 1
    assert calls == 4


@pytest.mark.asyncio
async def test_history_unique_admission_survives_paid_resume_but_zero_wait_is_not_admission(work, monkeypatch):
    work.today.clear()
    work.projects[:] = work.projects[4:6]
    monkeypatch.setattr(settings, "RARDAR_HISTORICAL_DAILY_LIMIT", 1)
    waiting = True
    paid = False

    async def collect(*_args):
        if waiting:
            raise daily_provider_budget.ProviderWorkYield("interactive_request_waiting")
        if not paid:
            daily_provider_budget._work_slice.get().used_requests += 1
        raise daily_provider_budget.ProviderWorkYield("work_slice_exhausted")

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    for _ in range(4):
        result = await service.historical_work(work.target, progress, lambda: None)
        assert result["historicalAdmitted"] == 0
        assert result["providerRequests"] == 0
        assert result["failedAttempts"] == 0
    waiting = False
    first = await service.historical_work(work.target, progress, lambda: None)
    assert first["historicalAdmitted"] == 1
    admitted = dict(progress["materialWork"]["projects"])
    paid = True
    for _ in range(3):
        resumed = await service.historical_work(work.target, progress, lambda: None)
        assert resumed["historicalAdmitted"] == 1
        assert resumed["historicalNewAdmitted"] == 0
        assert resumed["failedAttempts"] == 0
    assert set(progress["materialWork"]["projects"]) == set(admitted)


@pytest.mark.asyncio
async def test_true_failure_retry_is_bounded_without_blocking_other_today_projects(work, monkeypatch):
    work.projects[:] = work.projects[:2]
    original = service._collect_project_material

    async def collect(*args):
        if args[1]["repository"] == "current/one":
            work.calls.append("current/one")
            raise ValueError("repository_metadata_invalid")
        return await original(*args)

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    await service.historical_work(work.target, progress, lambda: None)
    await service.historical_work(work.target, progress, lambda: None)
    third = await service.historical_work(work.target, progress, lambda: None)
    assert work.calls.count("current/one") == 2
    assert work.calls.count("current/two") == 1
    assert third["waitReason"] == "material_retry_limit_reached"
    assert third["failedAttempts"] == 2
    assert third["providerRequests"] == 0  # metadata failures are not model requests


@pytest.mark.asyncio
async def test_explicit_entry_shares_daily_progress_and_saved_cache_with_scheduler(work, monkeypatch):
    from app.services import rardar_daily_operations

    work.projects[:] = work.projects[:1]
    root = work.target / "daily"
    monkeypatch.setattr(rardar_daily_operations, "operation_root", lambda: root)
    identifier = work.projects[0]["projectId"]
    first = await service.generate_project_material(work.target, identifier)
    assert first["status"] == "processed"
    path = next(root.glob("*-refocus-v1.json"))
    progress = service.read_json(path)["progress"]["historical"]
    second = await service.historical_work(work.target, progress, lambda: None)
    third = await service.generate_project_material(work.target, identifier)
    assert second["reused"] == 1
    assert third["status"] == "reused"
    assert work.calls == ["current/one"]
    assert list(progress["materialWork"]["projects"]) == ["current/one"]


@pytest.mark.asyncio
async def test_explicit_entry_cannot_reset_legacy_retry_debits(work, monkeypatch):
    from app.services import rardar_daily_operations

    work.projects[:] = work.projects[:1]
    root = work.target / "daily"
    root.mkdir()
    monkeypatch.setattr(rardar_daily_operations, "operation_root", lambda: root)
    path = root / f"{daily_provider_budget.calendar_day()}-refocus-v1.json"
    service.atomic(
        path,
        {
            "date": daily_provider_budget.calendar_day(),
            "modules": {},
            "progress": {"historical": {"attempts": {"current/one": 2}}},
        },
    )
    result = await service.generate_project_material(work.target, work.projects[0]["projectId"])
    assert result["waitReason"] == "material_retry_limit_reached"
    assert work.calls == []
    saved = service.read_json(path)["progress"]["historical"]
    assert saved["attempts"] == {"current/one": 2}


def test_unknown_interruption_retains_bounded_debit_and_does_not_refund_requests():
    progress = {
        "materialWork": {
            "schemaVersion": 2,
            "projects": {
                "current/one": {
                    "scope": "today",
                    "status": "running",
                    "failures": 0,
                    "providerRequests": 2,
                    "interruptions": 0,
                    "legacyAttempts": 0,
                }
            },
        }
    }
    record = service._material_work_records(progress, {"current/one"})["current/one"]
    assert record["interruptions"] == 1
    assert record["failures"] == 0  # unknown interruption is not a fabricated confirmed failure
    assert record["providerRequests"] == 2
    assert record["status"] == "interrupted"


@pytest.mark.asyncio
async def test_one_pass_shares_six_request_slice_and_next_pass_keeps_daily_consumption(work, monkeypatch):
    work.projects[:] = work.projects[:3]
    ledger = SimpleNamespace(
        requests=0,
        reservation_limit=100,
        interactive_reserve=10,
        early_background_limit=20,
        limit=100,
        execution_lock=work.target / "execution.lock",
    )
    ledger.snapshot = lambda: {"reserved": ledger.requests, "remaining": 100 - ledger.requests}
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", AsyncMock(return_value=(ledger, {})))

    @contextmanager
    def reservation(*_args, **_kwargs):
        ledger.requests += 1  # simulated durable reservation; no actual Provider or ledger
        yield

    monkeypatch.setattr(daily_provider_budget, "combined_budget_execution", reservation)

    async def collect(_target, project, *_args):
        for _ in range(3):
            async with daily_provider_budget.managed_budget_execution(
                None, (ledger, {}), scene="rardar_project_profile"
            ):
                pass
        project["profile"] = {"summary": "fixture", "generatedAt": datetime.now(UTC).isoformat()}
        return SimpleNamespace(profile=object(), evidence=object(), profile_cache_state="rebuilt")

    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    first = await service.historical_work(work.target, progress, lambda: None)
    assert first["processed"] == 2
    assert first["providerRequests"] == 6
    assert first["waitReason"] == "work_slice_exhausted"
    assert len(progress["materialWork"]["projects"]) == 2
    second = await service.historical_work(work.target, progress, lambda: None)
    assert second["processed"] == 1
    assert second["providerRequests"] == 3
    assert ledger.requests == 9  # new pass, same daily consumption
