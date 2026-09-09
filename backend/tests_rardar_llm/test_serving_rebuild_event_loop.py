"""Application rebuild keeps async DB/model work on its owning event loop."""

import asyncio
from types import SimpleNamespace

import pytest

from app.services.llm.provider_budget import execution_budget, selection_execution_budget
from scripts import rebuild_rardar_serving as serving


@pytest.mark.asyncio
async def test_async_rebuild_preserves_owner_loop_and_budget(monkeypatch, tmp_path):
    owner = asyncio.get_running_loop()
    board = SimpleNamespace(generationId="fixed-source", exactRanked=["project"])
    source = (board, "manifest", "explosion", None)
    ledger = SimpleNamespace(snapshot=lambda: {}, stages={"project_profile"}, task_id="test")
    profiles = object()
    observed = []
    monkeypatch.setattr(serving, "_load_rebuild_source", lambda target: source)

    async def collect(projects, generation, cache, **kwargs):
        assert asyncio.get_running_loop() is owner
        assert execution_budget("rardar_project_profile")[0] is ledger
        # An asyncpg-like resource created on the owner loop cannot be awaited
        # in the former to_thread -> asyncio.run worker event loop.
        future = owner.create_future()
        owner.call_soon(future.set_result, profiles)
        observed.append((projects, generation, kwargs["allow_model_generation"]))
        return await future

    def finish(target, loaded, *, profile_provider, publication_audit):
        assert loaded is source
        assert profile_provider(["project"], "fixed-source", target / "profile-cache") is profiles
        assert execution_budget("rardar_project_profile")[0] is ledger
        return {"changed": True}

    monkeypatch.setattr(serving, "build_official_profiles", collect)
    monkeypatch.setattr(serving, "_build_and_install", finish)
    with selection_execution_budget(ledger):
        result = await serving.rebuild_async(tmp_path, concurrency=1, generate_profiles=True)
    assert result == {"changed": True}
    assert observed == [(["project"], "fixed-source", True)]


def test_cli_rebuild_still_owns_its_standalone_loop(monkeypatch, tmp_path):
    board = SimpleNamespace(generationId="fixed-source", exactRanked=["project"])
    source = (board, "manifest", "explosion", None)
    observed = []
    monkeypatch.setattr(serving, "_load_rebuild_source", lambda target: source)

    async def collect(projects, generation, cache, **kwargs):
        observed.append(asyncio.get_running_loop().is_running())
        return "profiles"

    def finish(target, loaded, *, profile_provider, publication_audit):
        assert profile_provider(["project"], "fixed-source", target / "profile-cache") == "profiles"
        return {"changed": False}

    monkeypatch.setattr(serving, "build_official_profiles", collect)
    monkeypatch.setattr(serving, "_build_and_install", finish)
    assert serving.rebuild(tmp_path) == {"changed": False}
    assert observed == [True]


@pytest.mark.asyncio
async def test_daily_entry_uses_async_rebuild_on_scheduler_loop(monkeypatch, tmp_path):
    from app.services import rardar_daily_operations as daily

    owner = asyncio.get_running_loop()
    ledger = SimpleNamespace(snapshot=lambda: {"remaining": 1}, task_id="test", stages={"project_profile"})

    async def rebuild(target, **kwargs):
        assert asyncio.get_running_loop() is owner
        assert execution_budget("rardar_project_profile")[0] is ledger
        return {
            "status": "healthy",
            "changed": False,
            "servingGenerationId": "serving",
            "profiles": {"total": 20, "complete": 18, "partial": 2, "sourceUnavailable": 0},
            "translationCalls": 0,
            "translationCacheHits": 18,
        }

    monkeypatch.setattr(serving, "rebuild_async", rebuild)
    result = await daily._today_profiles(tmp_path, ledger)
    assert result["status"] == "partial"
    assert result["completed"] == 18


@pytest.mark.parametrize("change", ["generation", "manifest", "explosion"])
def test_source_changed_during_collection_cannot_roll_back_serving(monkeypatch, tmp_path, change):
    original = (SimpleNamespace(generationId="old"), "manifest", "explosion", None)
    current = list(original)
    if change == "generation":
        current[0] = SimpleNamespace(generationId="new")
    else:
        current[1 if change == "manifest" else 2] = "changed"
    monkeypatch.setattr(serving, "_load_rebuild_source", lambda target: tuple(current))
    installed = []
    monkeypatch.setattr(serving, "_build_and_install", lambda *args, **kwargs: installed.append(True))
    with pytest.raises(serving.ServingProjectionError) as failure:
        serving._build_and_install_current(tmp_path, original, profile_provider=None, publication_audit=None)
    assert failure.value.code == "rardar_serving_source_changed"
    assert installed == []
    assert not (tmp_path.parent / f".{tmp_path.name}.sync.lock").exists()


def test_current_install_respects_existing_sync_lock(monkeypatch, tmp_path):
    lock = tmp_path.parent / f".{tmp_path.name}.sync.lock"
    lock.write_text("other writer", encoding="ascii")
    with pytest.raises(serving.ServingProjectionError) as failure:
        serving._build_and_install_current(tmp_path, (), profile_provider=None, publication_audit=None)
    assert failure.value.code == "rardar_sync_already_running"
    assert lock.read_text(encoding="ascii") == "other writer"
