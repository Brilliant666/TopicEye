"""The real scheduled worker recovers saved stages before any budgeted IO."""

import shutil
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.integrations.rardar import read_cache
from app.services import rardar_trending as service
from app.services.llm import daily_provider_budget
from tests_rardar_llm.test_shared_material_lifecycle_flow import run, source  # noqa: F401


@pytest.mark.asyncio
async def test_actual_daily_entry_persists_recovered_material_with_exhausted_daily_budget(
    source,  # noqa: F811
    monkeypatch,
):
    initial = await run(source, {})
    assert initial["processed"] == 1 and initial["providerRequests"] == 0
    board_before = (source.target / "trending-boards" / "current.json").read_bytes()
    shutil.rmtree(source.target / "profile-cache" / "profile-store")
    read_cache.clear()
    assert service.today()["projects"][0]["displayCard"] is None
    actual_calls = len(source.calls)
    exhausted = AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 0}), {}))
    monkeypatch.setattr(daily_provider_budget, "daily_execution_budget", exhausted)

    @asynccontextmanager
    async def no_new_source(_token):
        raise AssertionError("saved-stage recovery must not reopen a source client")
        yield  # pragma: no cover - asynccontextmanager protocol

    monkeypatch.setattr(service, "github_material_client", no_new_source)
    progress = {}
    restored = await run(source, progress)
    assert restored["status"] == "completed"
    assert restored["cacheReassembled"] == restored["refreshed"] == 1
    assert restored["providerRequests"] == 0
    assert len(source.calls) == actual_calls
    exhausted.assert_awaited_once()  # existing budget may be read; no Provider reservation is made
    record = service.read_json(source.target / "progress.json")["materialWork"]["projects"][source.repository]
    assert record["status"] == "completed" and record["nextAction"] == "reuse_healthy"
    assert record["sourceReceipt"]["sourceMode"] == "saved_evidence_not_refetched"
    item = service.today()["projects"][0]
    assert item["displayCard"] and item["profile"]["positioning"]
    assert (source.target / "trending-boards" / "current.json").read_bytes() == board_before
    assert (source.target / "profile-cache" / "profile-store").exists()
    repeated = await run(source, progress)
    assert repeated["processed"] == repeated["providerRequests"] == 0
    assert len(source.calls) == actual_calls
