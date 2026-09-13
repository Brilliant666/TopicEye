"""Deterministic public-read scope and invalidation, without business requests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.core.config import settings
from app.integrations.rardar import read_cache, trending_metadata, trending_store
from app.services import rardar_trending as service
from tests_rardar_llm.test_managed_materials import seed
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import _project


@pytest.fixture(autouse=True)
def clear_read_cache():
    read_cache.clear()
    yield
    read_cache.clear()


def test_single_flight_capacity_copy_and_failed_build(monkeypatch):
    monkeypatch.setattr(read_cache, "monotonic", lambda: 100)
    calls = []

    def build():
        calls.append(1)
        return {"items": [1]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: read_cache.cached(("same",), build), range(12)))
    assert len(calls) == 1
    results[0]["items"].append(2)
    assert read_cache.cached(("same",), build) == {"items": [1]}
    for index in range(read_cache.MAX_ENTRIES * 2):
        read_cache.cached(("bounded", index), dict)
    assert len(read_cache._entries) == read_cache.MAX_ENTRIES

    def fail():
        raise ValueError("invalid")

    with pytest.raises(ValueError, match="invalid"):
        read_cache.cached(("failure",), fail)
    assert read_cache.cached(("failure",), build) == {"items": [1]}


def test_shared_epoch_does_not_compound_nested_ttl(monkeypatch):
    clock = [101.0]
    source = [1]
    monkeypatch.setattr(read_cache, "monotonic", lambda: clock[0])

    def outer():
        return read_cache.cached(("inner",), lambda: source[0])

    assert read_cache.cached(("outer",), outer) == 1
    clock[0] = 119.9
    source[0] = 2
    assert read_cache.cached(("outer",), outer) == 1
    clock[0] = 120.0
    assert read_cache.cached(("outer",), outer) == 2


@pytest.mark.asyncio
async def test_scoped_files_empty_unknown_and_repeated_reads(tmp_path, monkeypatch):
    selected = await seed(tmp_path)
    project = _project()
    trending_metadata.save(
        tmp_path,
        {"repository": project.repository},
        {"full_name": project.repository, "id": project.githubRepositoryId},
    )
    other = selected.parent.parent / "999999"
    other.mkdir()
    (other / "invalid.json").write_text("{}")
    original = service._read_plain
    reads = []

    def track(path, **kwargs):
        reads.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(service, "_read_plain", track)
    assert service.saved_materials(tmp_path, repositories=set()) == {}
    assert reads == []
    expected = service.saved_materials(tmp_path, repositories={project.repository})
    assert reads == [selected]
    reads.clear()
    assert service.saved_materials(tmp_path, repositories={project.repository}) == expected
    assert reads == []
    assert service.saved_materials(tmp_path, repositories={"missing/unknown"}) == {}
    reads.clear()
    assert service.saved_materials(tmp_path, repositories={"missing/unknown"}) == {}
    assert reads == []  # missing ID does not turn every read into all bodies


def test_history_warm_read_does_not_rebuild_or_read_unrelated_metadata(tmp_path, monkeypatch):
    source = board("github", [f"org/project-{index}" for index in range(150)])
    trending_store.publish_sources(tmp_path, [source])
    calls = []
    original = Path.read_bytes

    def tracked(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    first = service._history_with_materials(tmp_path, {}, repositories={"org/project-0"})
    assert len(first["projects"]) == 1
    assert sum(path.parent.name == "captures" for path in calls) == 1
    calls.clear()
    second = service._history_with_materials(tmp_path, {}, repositories={"org/project-0"})
    assert second["projects"] == first["projects"]
    assert not any(path.parent.name == "captures" for path in calls)
    assert not any(path.parent.name == "profile-store" for path in calls)


def test_atomic_source_addition_and_latest_check_are_visible(tmp_path):
    source = board("github", ["org/first"])
    trending_store.publish_sources(tmp_path, [source])
    assert len(trending_store.historical_snapshot(tmp_path)["projects"]) == 1
    trending_store.publish_sources(tmp_path, [board("github", ["org/second"])])
    assert len(trending_store.historical_snapshot(tmp_path)["projects"]) == 2
    trending_store.publish_sources(tmp_path, [{"source": "github", "status": "failed", "errorCode": "fixture_failure"}])
    snapshot = trending_store.historical_snapshot(tmp_path)
    assert snapshot["sources"][0]["status"] == "stale"
    assert snapshot["sources"][0]["errorCode"] == "source_unavailable_or_invalid"


@pytest.mark.asyncio
async def test_same_generation_material_file_change_revalidates_within_epoch(tmp_path, monkeypatch):
    clock = [101.0]
    monkeypatch.setattr(read_cache, "monotonic", lambda: clock[0])
    path = await seed(tmp_path)
    project = _project()
    trending_metadata.save(
        tmp_path,
        {"repository": project.repository},
        {"full_name": project.repository, "id": project.githubRepositoryId},
    )
    assert service.saved_materials(tmp_path, repositories={project.repository})
    path.write_text("{}")  # simulate another process/in-place write, no writer hook
    clock[0] = 120.0
    assert service.saved_materials(tmp_path, repositories={project.repository}) == {}


@pytest.mark.asyncio
async def test_today_only_expands_qualified_and_card_detail_split(tmp_path, monkeypatch):
    await seed(tmp_path)
    source = board("github", [_project().repository, "unrelated/repository"])
    source["entries"][0].update(reportedDelta=200, githubRepositoryId=_project().githubRepositoryId)
    source["entries"][1]["reportedDelta"] = 199
    published = trending_store.publish_sources(tmp_path, [source])
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    calls = []
    original = service.project_material

    def tracked(profile, evidence, **kwargs):
        calls.append(profile.repository.lower())
        return original(profile, evidence, **kwargs)

    monkeypatch.setattr(service, "project_material", tracked)
    card = service.today()["projects"][0]
    assert calls and set(calls) == {_project().repository.lower()}
    assert "displayProfile" not in card and "displayEvidence" not in card
    assert "capabilities" not in card["profile"]
    detail = service.detail(card["projectId"], published["generationId"])
    assert detail["displayProfile"]["capabilities"] and detail["displayEvidence"]["selectedSections"]
    assert all(detail["displayProfile"][key] == value for key, value in card["displayCard"].items())
