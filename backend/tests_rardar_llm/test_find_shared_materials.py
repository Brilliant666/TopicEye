"""Find reuses verified raw shared sources, not previously generated AI claims."""

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import settings
from app.schemas.rardar_product import FindProjectRequest, RequirementProfile
from app.services import rardar_product, rardar_project_evidence as evidence_service
from tests_rardar_llm.test_find_requirement_first import comparison, profile, repo, wire_comparison
from tests_rardar_llm.test_shared_material_consumers import _metadata, _seed
from tests_rardar_selection.test_profile_cache_v2 import MARKDOWN


@pytest.fixture(autouse=True)
def clear_evidence_cache():
    evidence_service.clear_project_evidence_cache()
    yield
    evidence_service.clear_project_evidence_cache()


@pytest.mark.asyncio
async def test_find_reuses_verified_alias_raw_readme_without_another_source_call(tmp_path, monkeypatch):
    project = await _seed(tmp_path)
    _metadata(tmp_path, project)
    renamed = "new-owner/shared-project"
    _metadata(tmp_path, project, renamed)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    facts = {
        **project.model_dump(mode="json"),
        "repository": renamed,
        "pushedAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
    }
    requests = []

    def denied(request):
        requests.append(request.url.path)
        raise AssertionError("compatible shared README must not be fetched again")

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(denied)) as client:
        material = await evidence_service.collect_project_evidence(
            renamed, facts, client=client, include_readme_body=True, readme_only=True
        )
    assert requests == []
    assert material.cache_hit is True
    assert material.payload["evidenceIndex"]["readme:body:1"] == MARKDOWN
    snapshot = material.payload["sourceSnapshot"]
    assert snapshot["mode"] == "saved_shared_readme"
    assert snapshot["repository"] == project.repository
    assert snapshot["readmeBlobSha"] == "a" * 40
    assert snapshot["fetchedAt"] and snapshot["checkedAt"]
    assert material.payload["collectionLimits"]["githubRequests"] == 0
    sources = rardar_product._find_sources(renamed, material)
    readme_sources = [source for source in sources if source["kind"] == "readme"]
    assert readme_sources and all(
        source["url"] == f"https://api.github.com/repos/{project.repository}/git/blobs/{'a' * 40}"
        for source in readme_sources
    )
    assert all(source["repository"] == renamed for source in sources)
    assert "官方中文 README" not in material.payload["evidenceIndex"]["readme:body:1"]


@pytest.mark.parametrize(
    "change",
    ["new_push", "unknown_push", "stale_source", "unproven_alias", "id_conflict", "changed_pointer", "polluted_body"],
)
@pytest.mark.asyncio
async def test_find_falls_back_to_its_live_public_reader_when_shared_version_is_not_proven(
    tmp_path, monkeypatch, change
):
    project = await _seed(tmp_path)
    _metadata(tmp_path, project)
    repository = project.repository
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    facts = {**project.model_dump(mode="json"), "pushedAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
    root = tmp_path / "profile-cache" / "readmes" / str(project.githubRepositoryId)
    pointer = root / "current.json"
    saved = evidence_service.json.loads(pointer.read_bytes())
    if change == "new_push":
        # A <24h cache is not proof that a later push left README unchanged.
        facts["pushedAt"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    elif change == "unknown_push":
        facts["pushedAt"] = None
    elif change == "stale_source":
        saved["checkedAt"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        pointer.write_text(evidence_service.json.dumps(saved), encoding="utf-8")
    elif change == "unproven_alias":
        repository = "unproven-owner/similar-project"
    elif change == "id_conflict":
        facts["githubRepositoryId"] += 1
    elif change == "changed_pointer":
        saved["sha"] = "b" * 40
        saved["record"] = "b" * 40 + ".json"
        pointer.write_text(evidence_service.json.dumps(saved), encoding="utf-8")
    elif change == "polluted_body":
        path = root / saved["record"]
        record = evidence_service.json.loads(path.read_bytes())
        record["markdown"] = "# Unrelated\n\nThis claim does not belong to the stored evidence."
        path.write_text(evidence_service.json.dumps(record), encoding="utf-8")
    calls = []
    fresh_text = "# Public tool\n\nA fresh source body read through the existing Find path."

    def live_source(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "path": "README.md",
                "encoding": "base64",
                "content": base64.b64encode(fresh_text.encode()).decode(),
            },
        )

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(live_source)
    ) as client:
        material = await evidence_service.collect_project_evidence(
            repository, facts, client=client, include_readme_body=True, readme_only=True
        )
    assert calls == [f"/repos/{repository}/readme"]
    assert "sourceSnapshot" not in material.payload
    assert material.payload["evidenceIndex"]["readme:body:1"] == fresh_text
    assert material.payload["collectionLimits"]["githubRequests"] == 1


@pytest.mark.asyncio
async def test_same_shared_content_reuses_after_metric_or_check_time_churn(tmp_path, monkeypatch):
    project = await _seed(tmp_path)
    _metadata(tmp_path, project)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    facts = {**project.model_dump(mode="json"), "pushedAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}
    requests = []

    def forbidden(request):
        requests.append(request.url.path)
        raise AssertionError("unchanged shared sources must not be fetched")

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(forbidden)) as client:
        first = await evidence_service.collect_project_evidence(
            project.repository, facts, client=client, include_readme_body=True, readme_only=True
        )
        later = {**facts, "totalStars": 999999, "rank": 8, "fetchedAt": datetime.now(UTC).isoformat()}
        second = await evidence_service.collect_project_evidence(
            project.repository, later, client=client, include_readme_body=True, readme_only=True
        )
    assert requests == []
    assert second.cache_hit and second.payload == first.payload
    assert second.digest == first.digest


@pytest.mark.asyncio
async def test_find_business_entry_still_searches_and_reuses_proven_shared_raw_source(tmp_path, monkeypatch):
    project = await _seed(tmp_path)
    _metadata(tmp_path, project)
    renamed = "new-owner/shared-project"
    _metadata(tmp_path, project, renamed)
    monkeypatch.setattr(settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    model_scenes = []

    async def virtual_model(**kwargs):
        model_scenes.append(kwargs["response_model"].__name__)
        if kwargs["response_model"] is RequirementProfile:
            return SimpleNamespace(value=profile())
        return SimpleNamespace(
            value=wire_comparison(comparison([renamed], status="unknown", refs=[])),
            metadata=SimpleNamespace(model_display_name="virtual", provider="virtual", cache_hit=False),
        )

    monkeypatch.setattr(rardar_product, "call_rardar_structured", virtual_model)
    calls = []

    def search_only(request):
        calls.append(request.url.path)
        assert request.url.path == "/search/repositories"
        candidate = {
            **repo(project.githubRepositoryId),
            "full_name": renamed,
            "html_url": f"https://github.com/{renamed}",
        }
        return httpx.Response(200, json={"items": [candidate]})

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(search_only)
    ) as client:
        result = await rardar_product.find_projects(
            FindProjectRequest(requirement="团队自托管文档全文搜索"), client=client
        )
    assert calls == ["/search/repositories"]
    assert result.aiState == "ready" and result.comparison.candidates[0].repository == renamed
    assert model_scenes == ["RequirementProfile", "FindWireComparison"]  # virtual, not Provider traffic
    readme = [source for source in result.evidenceSources if source.kind == "readme"]
    assert readme and all("/git/blobs/" in str(source.url) for source in readme)
