"""Actual service projection over persisted selection; explicitly synthetic material IO."""

import json
from datetime import datetime

import pytest

from app.core.config import settings
from app.integrations.rardar import historical_daily
from app.integrations.rardar.trending_periods import ZONE
from app.services import rardar_trending as service
from tests_rardar_adapter.test_serving import _install_two, _root
from tests_rardar_llm.test_managed_materials import seed
from tests_rardar_selection.test_profile_cache_v2 import _project


def test_default_service_only_loads_selected_bodies_and_keeps_missing_slot(tmp_path, monkeypatch):
    rows = [
        {
            "repository": f"org/repo-{index}",
            "projectId": service.project_id_for_repository(f"org/repo-{index}"),
            "githubRepositoryId": index + 1,
            "profile": None,
        }
        for index in range(132)
    ]
    batch = historical_daily.publish(tmp_path, rows, now=datetime(2026, 9, 13, 9, tzinfo=ZONE), trigger="main")
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    requested = []

    def materials(_target, *, repositories=None):
        assert repositories is not None
        requested.append(repositories)
        return {repo: {"profile": {"summary": f"SAVED-BODY-{repo}"}} for repo in repositories}

    def snapshot(_target, saved, *, repositories=None):
        assert repositories == requested[-1]
        return {
            "generationId": "synthetic-archive",
            "publishedAt": "2026-09-12T01:00:00Z",
            "sources": [],
            "projects": [{**row, **saved.get(row["repository"], {})} for row in rows],
        }

    monkeypatch.setattr(service, "saved_materials", materials)
    monkeypatch.setattr(service, "_history_with_materials", snapshot)
    result = service.history()
    assert [row["projectId"] for row in result["projects"]] == batch["projectIds"]
    assert len(result["projects"]) == len(requested[0]) == 8
    assert json.dumps(result).count("SAVED-BODY-") == 8
    assert result["publishedAt"] == batch["publishedAt"]
    missing = batch["projectIds"][0]
    rows[:] = [row for row in rows if row["projectId"] != missing]
    repeated = service.history()
    assert [row["projectId"] for row in repeated["projects"]] == batch["projectIds"]
    assert repeated["projects"][0]["materialState"] == "unavailable"
    assert repeated["projects"][0]["profile"] is None
    assert len(repeated["projects"]) == 8


def test_default_service_does_not_create_first_batch_or_load_catalog_on_get(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("GET must not load catalog materials before first publication")

    monkeypatch.setattr(service, "saved_materials", forbidden)
    assert service.history()["state"] == "pending_daily_review"
    assert not (tmp_path / "historical-daily").exists()


def test_real_retained_fact_loader_never_opens_project_bodies_for_history_index(tmp_path, monkeypatch):
    from app.integrations.rardar.serving import ServingProjectionLoader, clear_serving_cache

    root = _root(tmp_path)
    _install_two(root)
    clear_serving_cache()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("history fact index must not read Profile/detail bodies")

    monkeypatch.setattr(ServingProjectionLoader, "load_project_with_etag", forbidden)
    snapshot = service._history_with_materials(root, {})
    assert snapshot["projects"]
    assert any(row.get("historicalRardarEvidence") for row in snapshot["projects"])
    assert all(row["profile"] is None for row in snapshot["projects"])


def test_real_retained_detail_loader_reads_only_requested_repositories(tmp_path, monkeypatch):
    from app.integrations.rardar.serving import ServingProjectionLoader, clear_serving_cache

    root = _root(tmp_path)
    _install_two(root)
    clear_serving_cache()
    today, _ = ServingProjectionLoader(root).load_today_with_etag()
    selected = today.exactRanked[0]
    original = ServingProjectionLoader.load_project_with_etag
    called = []

    def tracked(self, identifier, generation=None):
        called.append(identifier)
        return original(self, identifier, generation)

    monkeypatch.setattr(ServingProjectionLoader, "load_project_with_etag", tracked)
    values = list(service._retained_serving_details(root, repositories={selected.repository.lower()}))
    assert values
    assert set(called) == {selected.githubRepositoryId}
    assert all(row.project.repository.lower() == selected.repository.lower() for row in values)


@pytest.mark.asyncio
async def test_real_profile_loader_uses_known_numeric_index_before_reading_envelopes(tmp_path, monkeypatch):
    from app.integrations.rardar import trending_metadata

    selected_path = await seed(tmp_path)
    project = _project()
    trending_metadata.save(
        tmp_path,
        {"repository": project.repository, "githubRepositoryId": project.githubRepositoryId},
        {"full_name": project.repository, "id": project.githubRepositoryId},
    )
    other = selected_path.parent.parent / str(project.githubRepositoryId + 100)
    other.mkdir()
    (other / "unrelated.json").write_text("{}", encoding="utf-8")
    original = service._read_plain
    reads = []

    def tracked(path, **kwargs):
        reads.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(service, "_read_plain", tracked)
    loaded = service.saved_materials(tmp_path, repositories={project.repository.lower()})
    assert set(loaded) == {project.repository.lower()}
    assert reads == [selected_path]
    assert loaded[project.repository.lower()]["displayEvidence"]
