"""Published public output survives requests/processes without reassembly."""

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport, AsyncClient

from app.api.v1 import rardar
from app.core.config import settings
from app.integrations.rardar import historical_daily, public_reading, read_cache, trending_metadata, trending_store
from app.services import rardar_trending as service
from app.services.llm.provider_budget import atomic
from tests_rardar_llm.test_managed_materials import seed
from tests_rardar_llm.test_rardar_trending_store import board
from tests_rardar_selection.test_profile_cache_v2 import _project


def candidate(view="trending-today", *, summary="A saved public introduction", stars=100):
    repository = "scope/example"
    identifier = service.project_id_for_repository(repository)
    project = {
        "projectId": identifier,
        "repository": repository,
        "repositoryUrl": f"https://github.com/{repository}",
        "githubRepositoryId": 123,
        "description": summary,
        "totalStars": stars,
        "profile": None,
        "materialState": "unavailable",
    }
    value = {
        "schemaVersion": 1,
        "generationId": "boards-saved",
        "publishedAt": "2026-10-27T01:00:00+00:00",
        "sources": [],
        "projects": [project],
    }
    return {
        "view": view,
        "board": value,
        "details": {
            identifier: {**deepcopy(project), **{k: value[k] for k in ("generationId", "publishedAt", "sources")}}
        },
        "identifiers": {identifier: identifier},
    }


def test_identical_publication_is_idempotent_and_immutable(tmp_path):
    original = candidate()
    first = public_reading.publish(tmp_path, "trending-today", lambda: deepcopy(original))
    pointer = (tmp_path / "trending-boards/public-reading/current.json").read_bytes()
    second = public_reading.publish(tmp_path, "trending-today", lambda: deepcopy(original))
    assert first["status"] == "published" and second["status"] == "reused"
    assert first["revision"] == second["revision"]
    assert pointer == (tmp_path / "trending-boards/public-reading/current.json").read_bytes()
    value = public_reading.board(tmp_path, "trending-today")
    value["projects"][0]["description"] = "not saved"
    assert (
        public_reading.board(tmp_path, "trending-today")["projects"][0]["description"]
        == original["board"]["projects"][0]["description"]
    )
    assert len(list((tmp_path / "trending-boards/public-reading/trending-today").glob("*.json"))) == 1


@pytest.mark.parametrize("view", public_reading.VIEWS)
def test_detail_stays_on_list_revision_after_material_or_generation_changes(tmp_path, monkeypatch, view):
    original = candidate(view)
    first = public_reading.publish(tmp_path, view, lambda: deepcopy(original))
    identifier = original["board"]["projects"][0]["projectId"]
    changed = candidate(view, summary="A newer saved introduction")
    public_reading.publish(tmp_path, view, lambda: deepcopy(changed))
    changed["board"]["generationId"] = "boards-new-generation"
    next(iter(changed["details"].values()))["generationId"] = "boards-new-generation"
    public_reading.publish(tmp_path, view, lambda: changed)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))

    def forbidden(*args, **kwargs):
        raise AssertionError("a versioned link used the legacy assembly path")

    monkeypatch.setattr(service, "detail", forbidden)
    result = service.published_detail(
        identifier, "boards-saved", historical=view == "historical-hot", reading_revision=first["revision"]
    )
    assert result["generationId"] == "boards-saved"
    assert result["description"] == original["board"]["projects"][0]["description"]
    assert result["readingRevision"] == first["revision"]
    with pytest.raises(LookupError):
        service.published_detail(identifier, "boards-saved", reading_revision="a" * 64)


@pytest.mark.parametrize("view,state", [("trending-today", "not_synced"), ("historical-hot", "pending_daily_review")])
def test_bootstrap_without_source_cannot_replace_durable_real_board(tmp_path, monkeypatch, view, state):
    first = public_reading.publish(tmp_path, view, lambda: candidate(view))
    empty = candidate(view)
    empty["board"].update(projects=[], generationId=None, state=state)
    empty.update(details={}, identifiers={})
    monkeypatch.setattr(service, "_reading_product", lambda target, selected: empty)
    alias = "today" if view == "trending-today" else "history"
    result = service.publish_reading_snapshots(tmp_path, views=(alias,))
    assert result[alias]["status"] == "failed"
    assert public_reading.board(tmp_path, view)["readingRevision"] == first["revision"]


def test_missing_history_source_keeps_legitimate_empty_review(tmp_path):
    empty = candidate("historical-hot")
    empty["board"].update(projects=[], generationId=None, state="ready", dailyReview={"date": "2026-10-27"})
    empty.update(details={}, identifiers={})
    first = public_reading.publish(tmp_path, "historical-hot", lambda: deepcopy(empty))
    empty["board"].update(state="pending_daily_review", dailyReview=None)
    with pytest.raises(ValueError, match="source_unavailable"):
        public_reading.publish(tmp_path, "historical-hot", lambda: empty)
    assert public_reading.board(tmp_path, "historical-hot")["readingRevision"] == first["revision"]


def test_same_view_writers_serialize_and_failed_first_writer_keeps_previous(tmp_path):
    first = public_reading.publish(tmp_path, "trending-today", candidate)
    entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()

    def invalid():
        entered.set()
        assert release.wait(5)
        raise ValueError("isolated candidate failure")

    def valid():
        second_entered.set()
        return candidate(summary="A saved valid successor")

    with ThreadPoolExecutor(max_workers=2) as pool:
        failed = pool.submit(public_reading.publish, tmp_path, "trending-today", invalid)
        assert entered.wait(5)
        successor = pool.submit(public_reading.publish, tmp_path, "trending-today", valid)
        try:
            assert not second_entered.wait(0.05)
            assert public_reading.board(tmp_path, "trending-today")["readingRevision"] == first["revision"]
        finally:
            release.set()
        with pytest.raises(ValueError, match="candidate failure"):
            failed.result(timeout=5)
        result = successor.result(timeout=5)
    assert public_reading.board(tmp_path, "trending-today")["readingRevision"] == result["revision"]


def test_missing_pointer_get_is_unavailable_without_building(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))

    def forbidden(*args, **kwargs):
        raise AssertionError("unpublished GET attempted a build")

    monkeypatch.setattr(service, "_reading_product", forbidden)
    with pytest.raises(LookupError, match="not_published"):
        service.published_today()
    with pytest.raises(ValueError, match="not_ready"):
        service.published_detail("missing", "boards-saved")
    assert not (tmp_path / "trending-boards/public-reading").exists()


@pytest.mark.asyncio
async def test_http_versioned_routes_keep_product_scope_and_validation(tmp_path, monkeypatch):
    receipt = public_reading.publish(tmp_path, "trending-today", candidate)
    identifier = candidate()["board"]["projects"][0]["projectId"]
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rardar, "is_rardar_product", lambda: True)
    app = FastAPI()
    app.include_router(rardar.router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        base = "/api/v1/rardar"
        response = await client.get(f"{base}/public-reading/trending-today/{receipt['revision']}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        exact = await client.get(
            f"{base}/trending-projects/{identifier}",
            params={"generation": "boards-saved", "readingRevision": receipt["revision"]},
        )
        assert exact.status_code == 200 and exact.json()["readingRevision"] == receipt["revision"]
        for revision, status in (("a" * 64, 404), ("bad", 422)):
            response = await client.get(
                f"{base}/trending-projects/{identifier}",
                params={"generation": "boards-saved", "readingRevision": revision},
            )
            assert response.status_code == status
        monkeypatch.setattr(rardar, "is_rardar_product", lambda: False)
        assert (await client.get(f"{base}/public-reading")).status_code == 404
        assert (await client.get(f"{base}/public-reading/trending-today/{receipt['revision']}")).status_code == 404


@pytest.mark.parametrize("change", ["description", "totalStars", "materialAttempt"])
def test_same_fact_generation_new_visible_material_has_new_revision(tmp_path, change):
    original = candidate()
    first = public_reading.publish(tmp_path, "trending-today", lambda: deepcopy(original))
    newer = deepcopy(original)
    value = {
        "description": "Updated saved introduction",
        "totalStars": 200,
        "materialAttempt": {"status": "failed", "stage": "source"},
    }[change]
    newer["board"]["projects"][0][change] = value
    next(iter(newer["details"].values()))[change] = value
    second = public_reading.publish(tmp_path, "trending-today", lambda: newer)
    assert second["revision"] != first["revision"]
    assert public_reading.board(tmp_path, "trending-today")["generationId"] == "boards-saved"
    assert public_reading.board(tmp_path, "trending-today", first["revision"])["projects"][0].get(change) != value


def test_invalid_or_failed_candidate_keeps_old_view_and_other_view_can_publish(tmp_path):
    first = public_reading.publish(tmp_path, "trending-today", candidate)
    invalid = candidate()
    invalid["board"]["projects"][0]["githubRepositoryId"] = 456
    with pytest.raises(ValueError, match="identity_mismatch"):
        public_reading.publish(tmp_path, "trending-today", lambda: invalid)
    assert public_reading.current(tmp_path)["views"]["trending-today"]["revision"] == first["revision"]
    history = public_reading.publish(tmp_path, "historical-hot", lambda: candidate("historical-hot"))
    assert history["status"] == "published"
    assert set(public_reading.current(tmp_path)["views"]) == set(public_reading.VIEWS)


def test_failed_pointer_install_keeps_previous_readable_revision(tmp_path, monkeypatch):
    first = public_reading.publish(tmp_path, "trending-today", candidate)
    original = public_reading.atomic

    def fail_pointer(path, value):
        if path.name == "current.json":
            raise OSError("simulated install failure")
        original(path, value)

    monkeypatch.setattr(public_reading, "atomic", fail_pointer)
    with pytest.raises(OSError):
        public_reading.publish(tmp_path, "trending-today", lambda: candidate(stars=999))
    assert public_reading.board(tmp_path, "trending-today")["readingRevision"] == first["revision"]


def test_list_reads_do_not_load_project_bodies_and_status_changes_reuse_them(tmp_path, monkeypatch):
    original = candidate()
    detail = next(iter(original["details"].values()))
    detail["displayEvidence"] = {"publicReadme": "saved public evidence " * 1000}
    public_reading.publish(tmp_path, "trending-today", lambda: deepcopy(original))
    changed = deepcopy(original)
    changed["board"]["checkedAt"] = "2026-10-27T03:00:00+00:00"
    public_reading.publish(tmp_path, "trending-today", lambda: changed)
    assert len(list((tmp_path / "trending-boards/public-reading/projects").glob("*.json"))) == 1

    def forbidden(*args, **kwargs):
        raise AssertionError("a list read loaded a full project body")

    monkeypatch.setattr(public_reading, "_project", forbidden)
    public_reading._load.cache_clear()
    assert public_reading.board(tmp_path, "trending-today")["projects"][0]["materialState"] == "unavailable"


def test_concurrent_views_keep_both_pointers_and_project_blobs_are_shared(tmp_path):
    def publish(view):
        return public_reading.publish(tmp_path, view, lambda: candidate(view))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, public_reading.VIEWS))
    assert all(value["status"] == "published" for value in results)
    assert set(public_reading.current(tmp_path)["views"]) == set(public_reading.VIEWS)
    assert len(list((tmp_path / "trending-boards/public-reading/projects").glob("*.json"))) == 1


def test_corrupt_project_body_cannot_be_served_as_a_partial_detail(tmp_path):
    receipt = public_reading.publish(tmp_path, "trending-today", candidate)
    payload, _ = public_reading.product(tmp_path, "trending-today")
    identifier = next(iter(payload["details"]))
    public_reading.detail(tmp_path, "trending-today", identifier, "boards-saved")
    path = tmp_path / "trending-boards/public-reading/projects" / f"{payload['details'][identifier]}.json"
    envelope = json.loads(path.read_bytes())
    envelope["payload"]["description"] = "corrupted after publication"
    atomic(path, envelope)
    with pytest.raises(ValueError, match="project_digest_mismatch"):
        public_reading.detail(tmp_path, "trending-today", identifier, "boards-saved")
    assert public_reading.board(tmp_path, "trending-today")["readingRevision"] == receipt["revision"]


def test_reads_are_persistent_lockless_and_do_not_invoke_builders(tmp_path, monkeypatch):
    receipt = public_reading.publish(tmp_path, "trending-today", candidate)

    def forbidden(*args, **kwargs):
        raise AssertionError("GET must not write, lock or assemble")

    monkeypatch.setattr(public_reading, "atomic", forbidden)
    monkeypatch.setattr(public_reading, "file_lock", forbidden)
    monkeypatch.setattr(service, "saved_materials", forbidden)
    monkeypatch.setattr(service, "today", forbidden)
    monkeypatch.setattr(service, "history", forbidden)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    read_cache.clear()
    with ThreadPoolExecutor(max_workers=4) as pool:
        reads = list(pool.map(lambda _: service.published_today(), range(8)))
    assert {value["readingRevision"] for value in reads} == {receipt["revision"]}
    public_reading._load.cache_clear()
    assert service.published_today() == reads[0]


def test_process_restart_reads_saved_product_without_source_tree(tmp_path):
    public_reading.publish(tmp_path, "trending-today", candidate)
    code = """
import json, socket, sys
from pathlib import Path
from app.integrations.rardar import public_reading
def forbidden(*args, **kwargs): raise AssertionError('no network')
socket.socket.connect = forbidden
socket.getaddrinfo = forbidden
value=public_reading.board(Path(sys.argv[1]), 'trending-today')
print(json.dumps({'projects':len(value['projects']), 'revision':value['readingRevision']}))
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert json.loads(result.stdout)["projects"] == 1


def test_corrupt_product_is_rejected_even_after_warming_and_not_overwritten(tmp_path):
    receipt = public_reading.publish(tmp_path, "trending-today", candidate)
    public_reading.board(tmp_path, "trending-today")
    path = tmp_path / "trending-boards/public-reading/trending-today" / f"{receipt['revision']}.json"
    value = json.loads(path.read_bytes())
    value["payload"]["board"]["projects"][0]["description"] = "forged"
    atomic(path, value)
    with pytest.raises(ValueError, match="digest_mismatch"):
        public_reading.board(tmp_path, "trending-today")
    with pytest.raises(ValueError, match="digest_mismatch"):
        public_reading.publish(tmp_path, "trending-today", candidate)


@pytest.mark.parametrize("revision", ["../outside", "A" * 64, "x", ""])
def test_revision_cannot_escape_public_product_store(tmp_path, revision):
    with pytest.raises(ValueError, match="revision_invalid"):
        public_reading.board(tmp_path, "trending-today", revision)


@pytest.mark.asyncio
async def test_actual_api_reads_saved_product_and_revision_route_not_materials(tmp_path, monkeypatch):
    await seed(tmp_path)
    project = _project()
    source = board("github", [project.repository])
    source["entries"][0].update(reportedDelta=200, githubRepositoryId=project.githubRepositoryId)
    publication = trending_store.publish_sources(tmp_path, [source])
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(rardar, "is_rardar_product", lambda: True)
    result = service.publish_reading_snapshots(tmp_path)
    assert result["today"]["status"] == "published", result
    revision = result["today"]["revision"]

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP read attempted source/material reassembly")

    for name in ("today", "history", "detail", "saved_materials", "daily_history_view", "_reading_product"):
        monkeypatch.setattr(service, name, forbidden)
    response = Response()
    today = await rardar.trending_today(response)
    assert today["generationId"] == publication["generationId"]
    assert len(today["projects"]) == 1 and today["projects"][0]["displayCard"]
    assert "displayEvidence" not in today["projects"][0]
    version_response = Response()
    assert await rardar.public_reading_board(version_response, "trending-today", revision) == today
    assert version_response.headers["Cache-Control"].endswith("immutable")
    detail = await rardar.trending_project(today["projects"][0]["projectId"], publication["generationId"])
    assert detail["displayEvidence"] and detail["readingRevision"] == revision


@pytest.mark.asyncio
async def test_partial_and_missing_materials_publish_all_fact_members_and_keep_daily_ids(tmp_path, monkeypatch):
    await seed(tmp_path)
    project = _project()
    source = board("github", [project.repository, "new/no-material"])
    for entry in source["entries"]:
        entry["reportedDelta"] = 250
    source["entries"][0]["githubRepositoryId"] = project.githubRepositoryId
    trending_store.publish_sources(tmp_path, [source])
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    now = datetime(2026, 10, 27, 1, tzinfo=UTC)
    fixed = historical_daily.publish(
        tmp_path, [service._today_projection(tmp_path)["projects"][0]], now=now, trigger="main"
    )
    receipt = service.publish_reading_snapshots(tmp_path)
    assert all(item["status"] == "published" for item in receipt.values()), receipt
    today = service.published_today()
    assert len(today["projects"]) == 2
    assert next(p for p in today["projects"] if p["repository"] == "new/no-material")["materialState"] == "unavailable"
    history = service.published_history()
    assert history["dailyReview"]["projectIds"] == fixed["projectIds"]
    assert historical_daily.read_latest(tmp_path) == fixed


@pytest.mark.asyncio
async def test_new_metadata_same_fact_generation_requires_writer_publication_not_get(tmp_path, monkeypatch):
    await seed(tmp_path)
    project = _project()
    source = board("github", [project.repository])
    source["entries"][0].update(reportedDelta=200, githubRepositoryId=project.githubRepositoryId)
    facts = trending_store.publish_sources(tmp_path, [source])
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    trending_metadata.save(
        tmp_path,
        {"repository": project.repository},
        {"full_name": project.repository, "id": project.githubRepositoryId, "language": "Python"},
    )
    first = service.publish_reading_snapshots(tmp_path, views=("today",))
    trending_metadata.save(
        tmp_path,
        {"repository": project.repository},
        {"full_name": project.repository, "id": project.githubRepositoryId, "language": "Rust"},
    )
    assert service.published_today()["projects"][0]["language"] == "Python"
    second = service.publish_reading_snapshots(tmp_path, views=("today",))
    assert second["today"]["revision"] != first["today"]["revision"]
    current = service.published_today()
    assert current["generationId"] == facts["generationId"]
    assert current["projects"][0]["language"] == "Rust"
