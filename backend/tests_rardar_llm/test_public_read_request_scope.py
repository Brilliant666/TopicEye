"""One read may reuse validated inputs; later reads must see changed inputs."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.core.config import settings
from app.integrations.rardar import project_identity, read_cache, trending_metadata, trending_store
from app.integrations.rardar.read_scope import once, read_scoped
from app.services import rardar_trending as service
from app.services.llm.provider_budget import atomic
from tests_rardar_llm.test_managed_materials import seed
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import _project


@pytest.fixture(autouse=True)
def isolated_cache():
    read_cache.clear()
    yield
    read_cache.clear()


def test_nested_scope_reuses_inputs_without_sharing_mutable_results():
    builds = []

    def build():
        builds.append(1)
        return {"items": [len(builds)]}

    @read_scoped
    def nested():
        return once(("input",), build)

    @read_scoped
    def read():
        first = nested()
        first["items"].append(999)
        return nested()

    assert read() == {"items": [1]}
    assert read() == {"items": [2]}
    assert len(builds) == 2
    # Unscoped background/writer paths do not retain a read's memoized input.
    assert nested() == {"items": [3]}


def test_scopes_are_independent_between_threads_and_reset_after_failure():
    barrier = Barrier(2)

    @read_scoped
    def read(value):
        first = once(("same",), lambda: value)
        barrier.wait(timeout=5)
        return first, once(("same",), lambda: "unexpected")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(read, ["first", "second"])) == [("first", "first"), ("second", "second")]

    @read_scoped
    def fail():
        once(("same",), lambda: "failed-read")
        raise ValueError("expected")

    with pytest.raises(ValueError, match="expected"):
        fail()
    assert once(("same",), lambda: "new-input") == "new-input"


def test_failed_input_is_not_memoized_as_a_completed_read():
    calls = []

    def build():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("invalid")
        return "valid"

    @read_scoped
    def read():
        with pytest.raises(ValueError, match="invalid"):
            once(("input",), build)
        return once(("input",), build)

    assert read() == "valid"
    assert len(calls) == 2


def test_reused_identity_still_checks_each_callers_numeric_identity(tmp_path, monkeypatch):
    project = {"repository": "scope/example"}
    trending_metadata.save(tmp_path, project, {"full_name": "scope/example", "id": 123})
    original = project_identity._resolved_identity
    calls = []

    def tracked(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(project_identity, "_resolved_identity", tracked)

    @read_scoped
    def read():
        identity = project_identity.resolve(tmp_path, project)
        identity["aliases"].append("forged/alias")
        assert project_identity.resolve(tmp_path, {**project, "githubRepositoryId": 123})["aliases"] == ["scope/example"]
        with pytest.raises(ValueError, match="repository_identity_mismatch"):
            project_identity.resolve(tmp_path, {**project, "githubRepositoryId": 456})
        with pytest.raises(ValueError, match="repository_identity_evidence_required"):
            project_identity.resolve(tmp_path, {**project, "identityState": "needs_identity_evidence"})

    read()
    assert len(calls) == 1


def test_metadata_next_request_sees_new_stars_and_keeps_binding_checks(tmp_path, monkeypatch):
    project = {"repository": "scope/example"}
    meta = {"full_name": "scope/example", "id": 123, "stargazers_count": 100}
    trending_metadata.save(tmp_path, project, meta)
    original = trending_metadata.read_json
    reads = []

    def tracked(*args, **kwargs):
        reads.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(trending_metadata, "read_json", tracked)

    @read_scoped
    def read():
        first = trending_metadata.read(tmp_path, project)
        first["topics"].append("not-saved")
        second = trending_metadata.read(tmp_path, {**project, "githubRepositoryId": 123})
        assert "not-saved" not in second["topics"]
        with pytest.raises(ValueError, match="repository_identity_mismatch"):
            trending_metadata.read(tmp_path, {**project, "githubRepositoryId": 456})
        return second["totalStars"]

    assert read() == 100
    assert len(reads) == 1
    trending_metadata.save(tmp_path, project, {**meta, "stargazers_count": 200})
    reads.clear()
    assert read() == 200
    assert len(reads) == 1


def test_next_request_rejects_atomically_corrupted_identity_in_same_epoch(tmp_path, monkeypatch):
    monkeypatch.setattr(read_cache, "monotonic", lambda: 101.0)
    project = {"repository": "scope/example", "githubRepositoryId": 123}
    trending_metadata.save(tmp_path, project, {"full_name": "scope/example", "id": 123})

    @read_scoped
    def read():
        return project_identity.resolve(tmp_path, project)

    assert read()["githubRepositoryId"] == 123
    atomic(project_identity._index_path(tmp_path), {"schemaVersion": 1, "payload": {}})
    with pytest.raises(ValueError, match="repository_identity_index_invalid"):
        read()


@pytest.mark.asyncio
async def test_actual_today_reuses_snapshot_and_refreshes_on_next_request(tmp_path, monkeypatch):
    await seed(tmp_path)
    project = _project()
    source = board("github", [project.repository])
    source["entries"][0].update(reportedDelta=200, githubRepositoryId=project.githubRepositoryId)
    first_publication = trending_store.publish_sources(tmp_path, [source])
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    original = trending_store._load_snapshot
    calls = []

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(trending_store, "_load_snapshot", tracked)
    first = service.today()
    assert first["generationId"] == first_publication["generationId"]
    assert len(calls) == 1
    assert first["projects"][0]["displayCard"]
    assert "displayEvidence" not in first["projects"][0]

    source["entries"][0]["reportedDelta"] = 300
    second_publication = trending_store.publish_sources(tmp_path, [source])
    calls.clear()
    second = service.today()
    assert second_publication["generationId"] != first_publication["generationId"]
    assert second["generationId"] == second_publication["generationId"]
    assert len(calls) == 1
