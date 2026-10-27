"""Write-boundary publication uses saved inputs, never real sources or Providers."""

import asyncio
import importlib
import json
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.integrations.rardar import trending_boards, trending_store
from app.schemas.rardar_today_operations import TodayOperationRequest
from app.services import rardar_cache_reassembly, rardar_daily_refresh, rardar_today_operations, rardar_trending
from app.services.llm.provider_budget import file_lock
from scripts import refresh_rardar_boards
from tests_rardar_llm.test_daily_refresh_policy import at, io  # noqa: F401
from tests_rardar_llm.test_material_correction_once import correction, grant  # noqa: F401
from tests_rardar_llm.test_today_operations import isolated  # noqa: F401


def publisher(monkeypatch, events, *, fail=False):
    def publish(target, views=None):
        events.append(("publish", tuple(views)))
        if fail:
            raise OSError("isolated publication failure")
        return {view: {"status": "published", "revision": str(len(events))} for view in views}

    monkeypatch.setattr(rardar_trending, "publish_reading_snapshots", publish, raising=False)


@pytest.mark.asyncio
async def test_daily_publishes_facts_before_metadata_and_each_material_slice(io, monkeypatch):  # noqa: F811
    target, _fetch = io
    events = []
    material_calls = []
    publisher(monkeypatch, events)
    monkeypatch.setattr(settings, "RARDAR_DAILY_MATERIAL_SLICES", 2)

    async def review(_clock, _kind):
        events.append(("review",))
        return {"date": "2026-09-12", "projectIds": []}

    async def history_metadata(_target, _clock):
        events.append(("history_metadata",))
        return {"status": "completed"}

    async def metadata(_target, _projects):
        events.append(("metadata",))
        return {"failed": [], "pending": 0}

    async def material():
        assert trending_store.load_snapshot(target)["generationId"]
        material_calls.append(True)
        events.append(("material",))
        return {
            "status": "completed" if len(material_calls) == 2 else "partial",
            "waitReason": "next_scheduled_pass",
            "visited": 1,
            "providerRequests": 0,
        }

    monkeypatch.setattr(rardar_trending, "refresh_history_metadata", history_metadata)
    monkeypatch.setattr(rardar_trending, "refresh_metadata", metadata)
    result = await rardar_daily_refresh.run_refresh(
        target, now=at(), trigger="automatic", review_work=review, material_work=material
    )
    assert events == [
        ("review",),
        ("publish", ("history",)),
        ("history_metadata",),
        ("publish", ("history",)),
        ("publish", ("today", "history")),
        ("metadata",),
        ("publish", ("today", "history")),
        ("material",),
        ("publish", ("today", "history")),
        ("material",),
        ("publish", ("today", "history")),
    ]
    assert result["providerCalls"] == 0
    assert all(value["status"] == "published" for value in result["readingPublication"].values())


@pytest.mark.asyncio
async def test_metadata_compensation_republishes_same_board_without_source_refetch(io, monkeypatch):  # noqa: F811
    target, fetch = io
    events = []
    publisher(monkeypatch, events)
    metadata = AsyncMock(side_effect=[{"failed": ["saved-gap"]}, {"failed": [], "pending": 0}])
    monkeypatch.setattr(rardar_trending, "refresh_metadata", metadata)
    monkeypatch.setattr(rardar_trending, "refresh_history_metadata", AsyncMock(return_value={"status": "completed"}))
    first = await rardar_daily_refresh.run_refresh(target, now=at(), trigger="automatic")
    events.clear()
    second = await rardar_daily_refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert second["generationId"] == first["generationId"]
    assert second["sourceRequests"] == 0 and fetch.await_count == 2
    assert events == [("publish", ("today", "history"))]
    assert second["readingPublication"]["today"]["status"] == "published"


@pytest.mark.asyncio
async def test_manual_publication_failure_is_saved_before_metadata_stage(io, monkeypatch):  # noqa: F811
    target, _fetch = io
    events = []
    publisher(monkeypatch, events, fail=True)
    path = target / "trending-boards/daily-refresh/day-2026-09-12.json"

    async def metadata(_target, _projects):
        day = trending_store.read_json(path)
        assert day["rounds"] == []
        assert all(value["status"] == "failed" for value in day["readingPublication"].values())
        return {"failed": [], "pending": 0}

    monkeypatch.setattr(rardar_trending, "refresh_metadata", metadata)
    result = await rardar_daily_refresh.run_refresh(target, now=at())
    assert result["readingReceipt"] == {"status": "saved", "date": "2026-09-12"}
    assert rardar_daily_refresh._reading_pending(trending_store.read_json(path)) == ("today", "history")


def test_manual_receipt_initializes_only_existing_daily_schema_and_merges_views(tmp_path):
    first = {"history": {"status": "published", "revision": "a" * 64}}
    saved = rardar_daily_refresh.record_reading_publication(tmp_path, first, now=at())
    assert saved == {"status": "saved", "date": "2026-09-12"}
    path = tmp_path / "trending-boards/daily-refresh/day-2026-09-12.json"
    day = trending_store.read_json(path)
    assert day == {"schemaVersion": 1, "date": "2026-09-12", "rounds": [], "readingPublication": first}
    day.update(rounds=[{"kind": "main", "status": "completed"}], materials={"status": "completed"})
    rardar_daily_refresh.atomic(path, day)
    failure = {"today": {"status": "failed", "errorCode": "fixture_failure"}}
    assert rardar_daily_refresh.record_reading_publication(tmp_path, failure, now=at(10))["status"] == "saved"
    merged = trending_store.read_json(path)
    assert merged == {**day, "readingPublication": {**first, **failure}}


def test_manual_receipt_busy_preserves_parallel_day_and_original_receipt(tmp_path):
    publication = {"today": {"status": "failed", "errorCode": "fixture_failure"}}
    initial = rardar_daily_refresh.record_reading_publication(tmp_path, {"history": {"status": "published"}}, now=at())
    root = tmp_path / "trending-boards/daily-refresh"
    path = root / f"day-{initial['date']}.json"
    before = path.read_bytes()
    with file_lock(root / "writer.lock", blocking=False):
        result = rardar_daily_refresh.record_reading_publication(tmp_path, publication, now=at(10))
    assert result == {"status": "busy", "date": "2026-09-12", "errorCode": "reading_publication_receipt_busy"}
    assert path.read_bytes() == before
    assert publication == {"today": {"status": "failed", "errorCode": "fixture_failure"}}


@pytest.mark.asyncio
async def test_manual_failure_receipt_gets_existing_zero_io_compensation(io, monkeypatch):  # noqa: F811
    target, fetch = io
    events = []
    publisher(monkeypatch, events)
    monkeypatch.setattr(rardar_trending, "refresh_history_metadata", AsyncMock(return_value={"status": "completed"}))
    material = AsyncMock(return_value={"status": "completed", "providerRequests": 0})
    await rardar_daily_refresh.run_refresh(target, now=at(), trigger="automatic", material_work=material)
    receipt = rardar_daily_refresh.record_reading_publication(target, {"today": {"status": "failed"}}, now=at(10))
    assert receipt["status"] == "saved"
    events.clear()
    result = await rardar_daily_refresh.run_refresh(target, now=at(11), trigger="automatic", material_work=material)
    assert result["automaticRound"] == "compensation"
    assert result["sourceRequests"] == result["providerCalls"] == 0
    assert fetch.await_count == 2 and material.await_count == 1
    assert events == [("publish", ("today",))]


@pytest.mark.asyncio
async def test_unchanged_source_publication_still_updates_reading(io, monkeypatch):  # noqa: F811
    target, _fetch = io
    events = []
    publisher(monkeypatch, events)
    original = rardar_daily_refresh.publish_sources

    def unchanged(*args, **kwargs):
        return {**original(*args, **kwargs), "changed": False}

    monkeypatch.setattr(rardar_daily_refresh, "publish_sources", unchanged)
    result = await rardar_daily_refresh.run_refresh(target, now=at())
    assert not result["changed"]
    assert ("publish", ("today", "history")) in events


@pytest.mark.asyncio
async def test_snapshot_failure_does_not_reclassify_source_or_review_success(io, monkeypatch):  # noqa: F811
    target, _fetch = io
    events = []
    publisher(monkeypatch, events, fail=True)
    review = AsyncMock(return_value={"date": "2026-09-12", "projectIds": []})
    result = await rardar_daily_refresh.run_refresh(target, now=at(), trigger="automatic", review_work=review)
    assert result["status"] == "partial"
    assert result["sourceStatus"] == "updated"
    assert result["readingStatus"] == "failed" and result["readingDisplay"] == "previous"
    assert result["historyReview"]["status"] == "published"
    assert result["generationId"]
    assert all(value["status"] == "failed" for value in result["readingPublication"].values())


@pytest.mark.asyncio
async def test_snapshot_only_failure_qualifies_zero_io_compensation(io, monkeypatch):  # noqa: F811
    target, fetch = io
    events = []
    publisher(monkeypatch, events, fail=True)
    monkeypatch.setattr(rardar_trending, "refresh_history_metadata", AsyncMock(return_value={"status": "completed"}))
    first = await rardar_daily_refresh.run_refresh(target, now=at(), trigger="automatic")
    assert first["sourceStatus"] == "updated" and first["readingStatus"] == "failed"
    day = trending_store.read_json(target / "trending-boards/daily-refresh/day-2026-09-12.json")
    assert all(value["status"] == "failed" for value in day["readingPublication"].values())
    publisher(monkeypatch, events)
    events.clear()
    second = await rardar_daily_refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert second["automaticRound"] == "compensation"
    assert second["sourceRequests"] == second["providerCalls"] == 0
    assert fetch.await_count == 2
    assert second["sourceStatus"] == "unchanged" and second["readingStatus"] == "published"
    assert events == [("publish", ("today", "history"))]


@pytest.mark.asyncio
async def test_history_snapshot_failure_does_not_relabel_published_today(io, monkeypatch):  # noqa: F811
    target, fetch = io

    def partial(_target, views=None):
        return {view: {"status": "failed" if view == "history" else "published"} for view in views}

    monkeypatch.setattr(rardar_trending, "publish_reading_snapshots", partial)
    monkeypatch.setattr(rardar_trending, "refresh_history_metadata", AsyncMock(return_value={"status": "completed"}))
    first = await rardar_daily_refresh.run_refresh(target, now=at(), trigger="automatic")
    assert first["status"] == first["sourceStatus"] == "updated"
    assert first["readingStatus"] == "published" and first["readingDisplay"] == "current"
    assert first["readingPublication"]["history"]["status"] == "failed"
    events = []
    publisher(monkeypatch, events)
    second = await rardar_daily_refresh.run_refresh(target, now=at(11), trigger="automatic")
    assert second["sourceRequests"] == second["providerCalls"] == 0 and fetch.await_count == 2
    assert second["readingStatus"] == "published"
    assert events == [("publish", ("history",))]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("today_status", "history_status", "expected_status"),
    [("failed", "published", "partial"), ("published", "failed", "updated"), ("reused", "published", "updated")],
)
async def test_manual_today_success_time_follows_today_publication_not_history(
    isolated,  # noqa: F811
    monkeypatch,
    today_status,
    history_status,
    expected_status,  # noqa: F811
):
    ops = rardar_today_operations
    monkeypatch.setattr(ops, "_current_scope", lambda: "dual_board")
    ops.atomic(isolated / "last-successful-sync.json", {"scope": "dual_board", "completedAt": "old"})
    sources = [{"source": "github", "status": "healthy"}]
    monkeypatch.setattr(
        ops,
        "_sync",
        lambda: {
            "status": "updated",
            "sourceStatus": "updated",
            "changed": True,
            "generationId": "boards-" + "b" * 64,
            "sources": sources,
            "readingPublication": {"today": {"status": today_status}, "history": {"status": history_status}},
        },
    )
    operation = await ops.start_operation(TodayOperationRequest(requestId=uuid4()), user_id=1)
    await asyncio.gather(*list(ops._tasks))
    result = ops.get_operation(operation["id"])
    assert result["status"] == expected_status
    assert result["result"]["sourceStatus"] == "updated"
    assert result["result"]["sources"] == sources
    assert result["result"]["readingStatus"] == today_status
    assert result["result"]["readingPublication"]["history"]["status"] == history_status
    assert (ops.last_successful_sync_at() == "old") is (today_status == "failed")


def test_publish_only_cli_has_no_source_route_budget_or_review_initialization(tmp_path, monkeypatch, capsys):
    events = []
    publisher(monkeypatch, events)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(refresh_rardar_boards, "is_rardar_product", lambda: True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("publish-only must use saved inputs only")

    monkeypatch.setattr(refresh_rardar_boards, "refresh_boards", forbidden)
    monkeypatch.setattr(refresh_rardar_boards, "refresh_metadata", forbidden)
    monkeypatch.setattr(rardar_trending, "publish_history_review", forbidden)
    monkeypatch.setattr(trending_boards, "fetch_board", forbidden)
    from app.services import rardar_llm_control
    from app.services.llm import daily_provider_budget

    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", forbidden)
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", forbidden)
    monkeypatch.setattr(sys, "argv", ["refresh_rardar_boards", "--publish-reading-only"])
    refresh_rardar_boards.main()
    output = json.loads(capsys.readouterr().out)
    assert output["providerCalls"] == 0
    assert events == [("publish", ("today", "history"))]
    assert output["readingReceipt"]["status"] == "saved"
    day = trending_store.read_json(
        tmp_path / "trending-boards/daily-refresh" / f"day-{output['readingReceipt']['date']}.json"
    )
    assert day["rounds"] == []
    assert set(day) == {"schemaVersion", "date", "rounds", "readingPublication"}


def test_publish_only_cli_rejects_source_options(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(refresh_rardar_boards, "is_rardar_product", lambda: True)
    monkeypatch.setattr(sys, "argv", ["refresh_rardar_boards", "--publish-reading-only", "--history-once"])
    with pytest.raises(SystemExit) as error:
        refresh_rardar_boards.main()
    assert error.value.code == 2


@pytest.mark.asyncio
async def test_manual_cache_reassembly_success_survives_snapshot_failure(tmp_path, monkeypatch):
    events = []
    publisher(monkeypatch, events, fail=True)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(rardar_cache_reassembly, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(rardar_cache_reassembly, "apply_locked", AsyncMock(return_value={"materialState": "complete"}))
    result = await rardar_cache_reassembly.apply("org/repo", "a" * 64)
    assert result["materialState"] == "complete"
    assert result["readingReceipt"]["status"] == "saved"
    assert all(value["status"] == "failed" for value in result["readingPublication"].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("reassembly_fails", [False, True])
async def test_cache_correction_keeps_original_outcome_when_snapshot_fails(
    correction,  # noqa: F811
    monkeypatch,
    reassembly_fails,
):
    from app.services import rardar_material_correction

    events = []
    publisher(monkeypatch, events, fail=True)
    monkeypatch.setattr(
        rardar_cache_reassembly,
        "apply_locked",
        AsyncMock(
            side_effect=ValueError("cache_reassembly_readback_failed") if reassembly_fails else None,
            return_value={"materialState": "complete"},
        ),
    )
    authorization = grant(correction, mode="cache-only", maximum=0)
    result = await rardar_material_correction.apply_once(
        correction.name,
        mode="cache-only",
        expected_plan_digest="a" * 64,
        operator_grant=authorization,
    )
    expected = "failed" if reassembly_fails else "completed"
    assert result["status"] == expected
    if reassembly_fails:
        assert result["errorCode"] == "cache_reassembly_readback_failed"
    _, receipt_path = rardar_material_correction._receipt_paths(
        correction.runtime, correction.name, authorization["authorizationId"]
    )
    assert receipt_path is not None
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["status"] == expected
    assert receipt["readingReceipt"]["status"] == "saved"
    assert all(value["status"] == "failed" for value in result["readingPublication"].values())


@pytest.mark.asyncio
async def test_cache_correction_retains_own_receipt_when_daily_writer_is_busy(correction, monkeypatch):  # noqa: F811
    from app.services import rardar_material_correction

    events = []
    publisher(monkeypatch, events)
    monkeypatch.setattr(rardar_cache_reassembly, "apply_locked", AsyncMock(return_value={"materialState": "complete"}))
    prior = rardar_daily_refresh.record_reading_publication(correction.target, {"history": {"status": "published"}})
    root = correction.target / "trending-boards/daily-refresh"
    day_path = root / f"day-{prior['date']}.json"
    before = day_path.read_bytes()
    authorization = grant(correction, mode="cache-only", maximum=0)
    with file_lock(root / "writer.lock", blocking=False):
        result = await rardar_material_correction.apply_once(
            correction.name,
            mode="cache-only",
            expected_plan_digest="a" * 64,
            operator_grant=authorization,
        )
    assert result["status"] == "completed" and result["readingReceipt"]["status"] == "busy"
    assert day_path.read_bytes() == before
    _, receipt_path = rardar_material_correction._receipt_paths(
        correction.runtime, correction.name, authorization["authorizationId"]
    )
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["readingReceipt"]["status"] == "busy"
    assert receipt["readingPublication"] == result["readingPublication"]


@pytest.mark.parametrize("script", ["repair_rardar_material_content", "repair_rardar_material_traits"])
@pytest.mark.parametrize("apply", [False, True])
def test_revision_cli_publishes_after_apply_only(script, apply, tmp_path, monkeypatch, capsys):
    module = importlib.import_module(f"scripts.{script}")
    events = []
    publisher(monkeypatch, events)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    name = "org/repo"
    before = {"identitySummaryZh": "旧简介", "productFormsZh": ["旧类型"]}
    profile = SimpleNamespace(
        **before,
        generatedAt=datetime(2026, 9, 12, tzinfo=UTC),
        model_dump=lambda **_kwargs: {**before, "generatedAt": "2026-09-12T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        module, "OfficialProjectProfile", SimpleNamespace(model_validate_json=lambda _raw, **_kw: profile)
    )
    monkeypatch.setattr(
        module, "ProjectEvidenceProjection", SimpleNamespace(model_validate_json=lambda _raw, **_kw: object())
    )
    monkeypatch.setattr(
        module, "saved_materials", lambda _target: {name: {"material": {}, "displayProfile": {}, "displayEvidence": {}}}
    )
    if script.endswith("content"):
        monkeypatch.setattr(module, "derive", lambda *_args: {"identitySummaryZh": "新简介"})
    else:
        monkeypatch.setattr(module, "FIELDS", ("productFormsZh",))
        monkeypatch.setattr(module, "derive", lambda *_args: ({"productFormsZh": ["新类型"]}, {}))

    def install(*_args):
        events.append(("install",))
        return {"changed": True, "state": "installed"}

    monkeypatch.setattr(module, "install", install)
    monkeypatch.setattr(sys, "argv", [script, "--repository", name, *(["--apply"] if apply else [])])
    module.main()
    output = json.loads(capsys.readouterr().out)
    assert events == ([("install",), ("publish", ("today", "history"))] if apply else [])
    assert ("readingPublication" in output) is apply
    assert ("readingReceipt" in output) is apply
