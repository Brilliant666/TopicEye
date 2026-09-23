from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import httpx
import pytest

from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.project_identity import project_id_for_repository
from app.integrations.rardar.serving_profiles import (
    DerivedPositioning,
    EvidenceClaim,
    ProfileTranslation,
    collect_official_project_profile,
)
from app.integrations.rardar.serving_schemas import ServingCapability
from app.services import rardar_cache_reassembly as repair
from app.services.llm.provider_budget import ProviderBudgetError, file_lock

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence" / "revision-a"
ROUTE = "a" * 64


@pytest.mark.asyncio
async def test_preview_apply_stale_and_idempotent_are_cache_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = RardarIntelligenceAdapter.from_config(str(FIXTURE.resolve())).load_explosion_board().exactRanked[0]
    project = project.model_copy(update={"description": "逐条标明成本和证据，并按收益排序的生活指南。"})
    markdown = """# Evidence guide

一份帮助读者权衡生活选择的指南。

## 内容

逐条标明行动成本、收益、证据等级和原始出处，并按性价比排序。
"""
    tree = [{"path": "README.md", "type": "file"}]

    def source(request):
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=tree)
        return httpx.Response(
            200,
            json={
                "path": "README.md",
                "sha": "a" * 40,
                "encoding": "base64",
                "content": base64.b64encode(markdown.encode()).decode(),
            },
        )

    async def structure(payload):
        ref = next(key for key, value in payload["evidenceIndex"].items() if "证据等级" in value)
        return ProfileTranslation(
            summary=EvidenceClaim(text="一份帮助读者权衡生活选择的指南。", evidenceRefs=["description"]),
            positioning=DerivedPositioning(
                positioningZh="通过逐条标明行动成本、收益和证据等级并按性价比排序，帮助读者识别优先选择。",
                includedEvidenceRefs=[ref],
                includedRoles=["core_mechanism", "primary_outcome"],
            ),
            capabilities=[
                ServingCapability(
                    title="证据追踪",
                    detail="逐条列出证据等级与原始出处，支持核对生活建议。",
                    evidenceRefs=[ref],
                    sourceMode="rardar_derived",
                )
            ],
            productForms=[],
            supportedEnvironments=[],
            useCases=[],
            deliveryForms=[],
        )

    cache_root = tmp_path / "profile-cache"
    async with httpx.AsyncClient(transport=httpx.MockTransport(source), base_url="https://api.github.com") as client:
        initial = await collect_official_project_profile(
            project,
            "fixture-generation",
            cache_root,
            client=client,
            translate=True,
            translator=structure,
            model_route_identity=ROUTE,
            save_partial_introduction=True,
        )
    assert initial.translation_calls == 1
    shutil.rmtree(cache_root / "profile-store")  # only the isolated fixture, to model a failed production Profile
    fact = {
        "repository": project.repository,
        "projectId": project_id_for_repository(project.repository),
        "githubRepositoryId": project.githubRepositoryId,
    }
    metadata = {
        "githubRepositoryId": project.githubRepositoryId,
        "language": project.primaryLanguage,
        "topics": project.topics,
        "license": project.licenseSpdxId,
    }

    async def route_identity():
        return ROUTE

    monkeypatch.setattr(repair, "ALLOWED_REPOSITORIES", frozenset({project.repository}))
    monkeypatch.setattr(repair.settings, "RARDAR_INTELLIGENCE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(repair, "detail", lambda *_args, **_kwargs: fact)
    monkeypatch.setattr(repair.trending_metadata, "read", lambda *_args: metadata)
    monkeypatch.setattr(repair, "resolve_rardar_route_identity", route_identity)
    monkeypatch.setattr(repair, "operation_root", lambda: tmp_path / "operations")

    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    plan, *_ = await repair.preview(project.repository)
    assert plan["externalRequests"] == 0
    assert plan["materialState"] == "complete"
    assert before == {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    with pytest.raises(ValueError, match="cache_reassembly_repository_not_allowed"):
        await repair.preview("unknown/other")

    readme = cache_root / "readmes" / str(project.githubRepositoryId) / ("a" * 40 + ".json")
    readme_before = readme.read_bytes()
    wrong_repository = json.loads(readme_before)
    wrong_repository["repository"] = "other/repository"
    readme.write_text(json.dumps(wrong_repository), encoding="utf-8")
    with pytest.raises(ValueError, match="cache_reassembly_readme_mismatch"):
        await repair.preview(project.repository)
    readme.write_bytes(readme_before)

    operations = tmp_path / "operations"
    operations.mkdir()
    with (
        file_lock(operations / "writer.lock", blocking=False),
        pytest.raises(ProviderBudgetError, match="provider_budget_busy"),
    ):
        await repair.apply(project.repository, plan["planDigest"])

    stage = next((cache_root / "rardar-assessments").glob("*/*.json"))
    original = stage.read_bytes()
    wrong_reference = json.loads(original)
    wrong_reference["positioning"]["includedEvidenceRefs"] = ["readme:missing"]
    stage.write_text(json.dumps(wrong_reference), encoding="utf-8")
    with pytest.raises(ValueError, match="cache_reassembly_assessment_missing"):
        await repair.preview(project.repository)
    stage.write_bytes(original)
    stage.write_bytes(original + b" ")  # byte change with identical parsed stage: stale digest must still fail
    with pytest.raises(ValueError, match="cache_reassembly_plan_stale"):
        await repair.apply(project.repository, plan["planDigest"])
    stage.write_bytes(original)
    receipt = await repair.apply(project.repository, plan["planDigest"])
    assert receipt["materialState"] == "complete"
    assert receipt["externalRequests"] == 0
    assert (await repair.apply(project.repository, plan["planDigest"]))["state"] == "reused"
    assert (
        json.loads((tmp_path / "operations" / "cache-reassembly" / f"{fact['projectId']}.json").read_text())[
            "sourceEvidenceDigest"
        ]
        == initial.evidence.digest
    )
