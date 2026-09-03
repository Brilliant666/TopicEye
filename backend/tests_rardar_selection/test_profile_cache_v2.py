from __future__ import annotations

import base64
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.profile_cache_v2 import (
    ProfileCacheIntegrityError,
    evidence_ref_remap,
    latest_attempt,
    load_profile_store,
    profile_cache_identity,
    profile_store_path,
    record_failure,
    retry_is_due,
)
from app.integrations.rardar.serving_profiles import (
    _build_evidence_context,
    _digest,
    _github_get,
    _model_route_cache_identity,
    _profile_identity_candidates,
    _profile_identity_for_result,
    _profile_identity_versions,
    collect_official_project_profile,
)

FIXTURE = Path(__file__).parents[1] / "tests" / "fixtures" / "rardar_intelligence" / "revision-a"
MARKDOWN = """
# Evidence Map

**把公开仓库证据整理成可验证、可交付的项目地图。**

这是一套基于 Node.js 的渲染与校验系统，由 Agent 生成 Typed JSON IR，再确定性编译为独立 HTML。

- **打开就是成品** —— 生成可交互的独立 HTML 文件
- **合并前看清变化** —— 对比两份经过校验的架构快照
- **每次探索都有依据** —— 所有结论都回指版本化源码

## 快速开始
运行公开 CLI 并打开生成的 HTML。
"""
TREE = [
    {"path": "README_ZH.md", "type": "file"},
    {"path": "src", "type": "dir"},
    {"path": "package.json", "type": "file"},
]


def _project():
    return RardarIntelligenceAdapter.from_config(str(FIXTURE.resolve())).load_explosion_board().exactRanked[0]


def _readme(sha: str = "a" * 40) -> dict[str, object]:
    return {"path": "README_ZH.md", "sha": sha, "markdown": MARKDOWN, "etag": '"fixture"'}


def _handler(calls: list[str], *, sha: str = "a" * 40):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=TREE)
        return httpx.Response(
            200,
            json={
                "path": "README_ZH.md",
                "sha": sha,
                "encoding": "base64",
                "content": base64.b64encode(MARKDOWN.encode()).decode(),
            },
            headers={"etag": '"fixture"'},
        )

    return handler


def _identity(project, evidence, *, route: str | None = None):
    versions = _profile_identity_versions()
    return profile_cache_identity(
        project,
        evidence,
        derivation_mode="official_zh",
        model_route_identity=route,
        profile_schema_version=versions["profileSchemaVersion"],
        profile_prompt_version=versions["profilePromptVersion"],
        official_narrative_prompt_version=versions["officialNarrativePromptVersion"],
        official_positioning_prompt_version=versions["officialPositioningPromptVersion"],
        rardar_assessment_prompt_version=versions["rardarAssessmentPromptVersion"],
    )


def test_model_route_identity_preserves_legacy_translation_cache_keys() -> None:
    legacy_payload = {
        "githubRepositoryId": 123,
        "revision": "readme-sha",
        "schema": "profile-v1",
        "prompt": "prompt-v1",
        "namespace": "rardar_assessment",
        "narrativeMode": "rardar_derived",
    }

    assert _model_route_cache_identity(legacy_payload, None) == _digest(legacy_payload)
    assert _model_route_cache_identity(legacy_payload, "route-v1") == _digest(
        {**legacy_payload, "modelRouteIdentity": "route-v1"}
    )
    assert _model_route_cache_identity(legacy_payload, "route-v1") != _digest(legacy_payload)


@pytest.mark.asyncio
async def test_generation_and_momentum_do_not_change_profile_content_identity(tmp_path: Path) -> None:
    project = _project()
    first_evidence = _build_evidence_context(project, "observation-a", TREE, _readme()).evidence
    dynamic_project = project.model_copy(
        update={
            "rank": project.rank + 7,
            "totalStars": project.totalStars + 900,
            "baselineStars": project.baselineStars + 100,
            "observedStarDelta": project.observedStarDelta + 800,
            "windowStartedAt": project.windowStartedAt + timedelta(hours=2),
            "windowEndedAt": project.windowEndedAt + timedelta(hours=2),
        }
    )
    second_evidence = _build_evidence_context(dynamic_project, "observation-b", TREE, _readme()).evidence

    first = _identity(project, first_evidence)
    second = _identity(dynamic_project, second_evidence)
    assert first.identityDigest == second.identityDigest
    assert first.profileEvidenceManifestDigest == second.profileEvidenceManifestDigest

    changed_description = dynamic_project.model_copy(update={"description": "不同的静态仓库说明"})
    changed_evidence = _build_evidence_context(changed_description, "observation-b", TREE, _readme()).evidence
    assert _identity(changed_description, changed_evidence).identityDigest != first.identityDigest

    changed_metadata = dynamic_project.model_copy(update={"topics": [*project.topics, "new-static-topic"]})
    metadata_evidence = _build_evidence_context(changed_metadata, "observation-b", TREE, _readme()).evidence
    assert _identity(changed_metadata, metadata_evidence).identityDigest != first.identityDigest


@pytest.mark.asyncio
async def test_equivalent_profile_rebind_is_zero_call_and_preserves_semantic_revision(tmp_path: Path) -> None:
    project = _project()
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler(calls)),
    ) as client:
        first = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="a" * 64,
        )
    assert first.profile_cache_state == "rebuilt"
    assert calls

    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("safe rebind must not call GitHub")

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(unexpected),
    ) as client:
        rebound = await collect_official_project_profile(
            project.model_copy(update={"rank": project.rank + 1, "totalStars": project.totalStars + 1}),
            "observation-b",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="a" * 64,
        )

    assert rebound.profile_cache_state == "rebound"
    assert rebound.github_requests == 0
    assert rebound.translation_calls == 0
    assert rebound.profile_revision == first.profile_revision
    assert rebound.profile_binding_digest != first.profile_binding_digest
    assert rebound.profile.generationId == "observation-b"
    serialized = rebound.profile.model_dump_json().casefold()
    assert "observedstardelta" not in serialized
    assert "totalstars" not in serialized


@pytest.mark.asyncio
async def test_safe_v1_lazy_migration_is_non_destructive_and_zero_call(tmp_path: Path) -> None:
    project = _project()
    calls: list[str] = []
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler(calls)),
    ) as client:
        first = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="b" * 64,
        )
    legacy = list((tmp_path / "profiles" / str(project.githubRepositoryId)).glob("*.json"))
    assert legacy
    shutil.rmtree(tmp_path / "profile-store")

    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("safe V1 migration must not call GitHub")

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(unexpected),
    ) as client:
        migrated = await collect_official_project_profile(
            project,
            "observation-b",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="b" * 64,
        )

    assert migrated.profile_cache_state == "migrated"
    assert migrated.profile_revision == first.profile_revision
    assert migrated.github_requests == migrated.translation_calls == 0
    assert all(path.exists() for path in legacy)
    assert migrated.migrated_from_v1 is True


@pytest.mark.asyncio
async def test_v1_ai_derived_profile_without_route_proof_is_preserved_and_rebuilt(tmp_path: Path) -> None:
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler([])),
    ) as client:
        await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="7" * 64,
        )
    legacy = next((tmp_path / "profiles" / str(project.githubRepositoryId)).glob("*.json"))
    payload = json.loads(legacy.read_text(encoding="utf-8"))
    payload["profile"].update(
        {
            "officialNarrativeMode": "rardar_derived",
            "positioningSourceMode": "rardar_derived",
        }
    )
    payload["deterministicFallbackUsed"] = False
    legacy.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy_bytes = legacy.read_bytes()
    shutil.rmtree(tmp_path / "profile-store")

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("no GitHub call"))),
    ) as client:
        rebuilt = await collect_official_project_profile(
            project,
            "observation-b",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="7" * 64,
        )

    assert rebuilt.profile_cache_state == "rebuilt"
    assert rebuilt.migrated_from_v1 is False
    assert rebuilt.github_requests == 0
    assert legacy.read_bytes() == legacy_bytes


@pytest.mark.asyncio
async def test_unprovable_v1_entry_is_preserved_and_rebuilt_instead_of_rebound(tmp_path: Path) -> None:
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler([])),
    ) as client:
        await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="2" * 64,
        )
    legacy = next((tmp_path / "profiles" / str(project.githubRepositoryId)).glob("*.json"))
    payload = json.loads(legacy.read_text(encoding="utf-8"))
    payload["evidence"]["readmeBlobSha"] = "f" * 40
    legacy.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    legacy_bytes = legacy.read_bytes()
    shutil.rmtree(tmp_path / "profile-store")

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError(str(request.url)))),
    ) as client:
        rebuilt = await collect_official_project_profile(
            project,
            "observation-b",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="2" * 64,
        )

    assert rebuilt.profile_cache_state == "rebuilt"
    assert rebuilt.migrated_from_v1 is False
    assert legacy.read_bytes() == legacy_bytes


@pytest.mark.asyncio
async def test_healthy_store_precedes_later_retryable_attempt(tmp_path: Path) -> None:
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler([])),
    ) as client:
        healthy = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="c" * 64,
        )
    assert healthy.profile_cache_identity is not None
    record_failure(
        tmp_path,
        project.githubRepositoryId,
        healthy.profile_cache_identity,
        error_code="profile_source_timeout",
        retryable=True,
        source_failure_stage="readme",
        now=datetime(2026, 9, 3, tzinfo=UTC),
    )

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("no call"))),
    ) as client:
        loaded = await collect_official_project_profile(
            project,
            "observation-b",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="c" * 64,
        )
    assert loaded.profile_failure_code is None
    assert loaded.profile_revision == healthy.profile_revision
    assert loaded.profile_cache_state == "rebound"


@pytest.mark.asyncio
async def test_corrupt_v2_profile_store_fails_closed_instead_of_becoming_unavailable(tmp_path: Path) -> None:
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler([])),
    ) as client:
        healthy = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="8" * 64,
        )
    assert healthy.profile_cache_identity is not None
    store = next((tmp_path / "profile-store" / "v2" / str(project.githubRepositoryId)).glob("*.json"))
    payload = json.loads(store.read_text(encoding="utf-8"))
    payload["recordDigest"] = "0" * 64
    store.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _request: (_ for _ in ()).throw(AssertionError("no GitHub call"))),
    ) as client:
        with pytest.raises(ProfileCacheIntegrityError, match="record is invalid"):
            await collect_official_project_profile(
                project,
                "observation-b",
                tmp_path,
                client=client,
                translate=True,
                model_route_identity="8" * 64,
            )


def test_attempt_ledger_backoff_is_bounded_and_evidence_scoped(tmp_path: Path) -> None:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    first = record_failure(
        tmp_path,
        42,
        "a" * 64,
        error_code="profile_source_timeout",
        retryable=True,
        source_failure_stage="readme",
        now=now,
    )
    second = record_failure(
        tmp_path,
        42,
        "a" * 64,
        error_code="profile_source_timeout",
        retryable=True,
        source_failure_stage="readme",
        now=now + timedelta(minutes=5),
    )
    missing = record_failure(
        tmp_path,
        42,
        "b" * 64,
        error_code="profile_source_http_404",
        retryable=True,
        source_failure_stage="readme",
        now=now,
    )
    assert first.nextRetryAt == now + timedelta(minutes=5)
    assert second.nextRetryAt == now + timedelta(minutes=35)
    assert missing.nextRetryAt == now + timedelta(hours=2)
    assert retry_is_due(tmp_path, 42, "a" * 64, now=now + timedelta(minutes=4)) is False
    assert retry_is_due(tmp_path, 42, "a" * 64, now=now + timedelta(hours=1)) is True
    assert retry_is_due(tmp_path, 42, "c" * 64, now=now) is True
    assert latest_attempt(tmp_path, 42, "a" * 64) == second
    permanent = record_failure(
        tmp_path,
        42,
        "d" * 64,
        error_code="profile_evidence_mismatch",
        retryable=False,
        source_failure_stage="evidence_rebind",
        now=now,
    )
    assert permanent.nextRetryAt is None
    assert retry_is_due(tmp_path, 42, "d" * 64, now=now + timedelta(days=30)) is False


def test_static_evidence_versions_and_model_route_invalidate_only_their_dependents() -> None:
    project = _project()
    versions = _profile_identity_versions()
    evidence = _build_evidence_context(project, "observation-a", TREE, _readme()).evidence

    def identity(*, mode="official_zh", route=None, readme=None, tree=None, prompt=None):
        current = _build_evidence_context(
            project,
            "observation-a",
            TREE if tree is None else tree,
            _readme() if readme is None else readme,
        ).evidence
        return profile_cache_identity(
            project,
            current,
            derivation_mode=mode,
            model_route_identity=route,
            profile_schema_version=versions["profileSchemaVersion"],
            profile_prompt_version=prompt or versions["profilePromptVersion"],
            official_narrative_prompt_version=versions["officialNarrativePromptVersion"],
            official_positioning_prompt_version=versions["officialPositioningPromptVersion"],
            rardar_assessment_prompt_version=versions["rardarAssessmentPromptVersion"],
        )

    baseline = identity()
    assert baseline.releaseEvidenceDigest is None
    assert identity(route="1" * 64).identityDigest == baseline.identityDigest
    assert identity(readme=_readme("b" * 40)).identityDigest != baseline.identityDigest
    assert identity(tree=[*TREE, {"path": "new-module", "type": "dir"}]).identityDigest != baseline.identityDigest
    assert identity(prompt="profile-prompt-next").identityDigest != baseline.identityDigest
    assert (
        identity(mode="official_translated", route="1" * 64).identityDigest
        != identity(
            mode="official_translated",
            route="2" * 64,
        ).identityDigest
    )
    assert evidence.generationId == "observation-a"


@pytest.mark.asyncio
async def test_ai_profile_route_identity_survives_deterministic_supplements(tmp_path: Path) -> None:
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler([])),
    ) as client:
        collected = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            model_route_identity="1" * 64,
        )
    profile = collected.profile.model_copy(
        update={"officialNarrativeMode": "rardar_derived", "translationState": "not_needed"}
    )
    ai_identity = _profile_identity_for_result(
        project,
        collected.evidence,
        profile,
        model_route_identity="1" * 64,
        model_derived_used=True,
        deterministic_fallback_used=True,
    )
    deterministic_identity = _profile_identity_for_result(
        project,
        collected.evidence,
        profile,
        model_route_identity="1" * 64,
        model_derived_used=False,
        deterministic_fallback_used=True,
    )
    assert ai_identity.modelRouteIdentity == "1" * 64
    assert deterministic_identity.modelRouteIdentity is None
    assert ai_identity.identityDigest != deterministic_identity.identityDigest

    candidates = _profile_identity_candidates(
        project,
        collected.evidence,
        "official_translated",
        "1" * 64,
    )
    assert candidates[0].modelRouteIdentity == "1" * 64
    assert any(item.derivationMode == "rardar_derived" and item.modelRouteIdentity is None for item in candidates)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_kind", "expected"),
    [
        ("timeout", "profile_source_timeout"),
        ("rate", "profile_source_rate_limited"),
        ("server", "profile_source_http_5xx"),
        ("disconnect", "profile_source_remote_disconnected"),
        ("missing", "profile_source_http_404"),
        ("invalid", "profile_source_invalid"),
    ],
)
async def test_github_source_failures_have_stable_safe_codes(response_kind: str, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if response_kind == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if response_kind == "disconnect":
            raise httpx.RemoteProtocolError("disconnected")
        if response_kind == "rate":
            return httpx.Response(429)
        if response_kind == "server":
            return httpx.Response(503)
        if response_kind == "missing":
            return httpx.Response(404)
        return httpx.Response(200, content=b"x" * 1_500_001)

    failures = []
    counter = [0]
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert await _github_get(client, "/fixture", counter, failures=failures, stage="readme") is None
    assert counter == [1]
    assert failures == [("readme", expected)]


@pytest.mark.asyncio
async def test_transient_source_failure_is_bounded_and_force_retry_recovers(tmp_path: Path) -> None:
    project = _project()
    failed_calls: list[str] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        failed_calls.append(request.url.path)
        return httpx.Response(503)

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(unavailable),
    ) as client:
        failed = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="d" * 64,
        )
    assert failed.profile_cache_state == "unavailable"
    assert failed.profile_failure_code == "profile_source_http_5xx"
    assert failed.profile_failure_retryable is True
    assert failed.profile_next_retry_at is not None
    assert failed_calls

    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("retry before nextRetryAt must be suppressed")

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(unexpected),
    ) as client:
        suppressed = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="d" * 64,
        )
    assert suppressed.profile_failure_code == failed.profile_failure_code
    assert suppressed.profile_next_retry_at == failed.profile_next_retry_at

    recovery_calls: list[str] = []
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler(recovery_calls)),
    ) as client:
        recovered = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="d" * 64,
            force_retryable=True,
        )
    assert recovered.profile_failure_code is None
    assert recovered.profile_cache_state == "rebuilt"
    assert recovery_calls
    assert latest_attempt(tmp_path, project.githubRepositoryId, failed.profile_cache_identity).errorCode == (
        "profile_source_http_5xx"
    )


@pytest.mark.asyncio
async def test_changed_repository_metadata_bypasses_old_negative_cache(tmp_path: Path) -> None:
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(lambda _request: httpx.Response(404)),
    ) as client:
        failed = await collect_official_project_profile(
            project,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="e" * 64,
        )
    calls: list[str] = []
    changed = project.model_copy(update={"description": "A changed static repository description."})
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(_handler(calls)),
    ) as client:
        recovered = await collect_official_project_profile(
            changed,
            "observation-a",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="e" * 64,
        )
    assert failed.profile_cache_identity != recovered.profile_cache_identity
    assert calls


def test_evidence_remap_is_exact_and_cross_repository_fails(tmp_path: Path) -> None:
    del tmp_path
    project = _project()
    old = _build_evidence_context(project, "observation-a", TREE, _readme()).evidence
    current = _build_evidence_context(project, "observation-b", TREE, _readme()).evidence
    identity = _identity(project, old)
    assert evidence_ref_remap(old, identity, current, _identity(project, current))["description"] == "description"

    changed_project = project.model_copy(update={"description": "Changed bounded evidence."})
    changed = _build_evidence_context(changed_project, "observation-b", TREE, _readme()).evidence
    with pytest.raises(ValueError, match="cannot be mapped"):
        evidence_ref_remap(old, identity, changed, _identity(changed_project, changed))

    other_project = project.model_copy(update={"githubRepositoryId": project.githubRepositoryId + 1})
    other = _build_evidence_context(other_project, "observation-b", TREE, _readme()).evidence
    with pytest.raises(ValueError, match="cross-repository"):
        evidence_ref_remap(old, identity, other, _identity(other_project, other))


@pytest.mark.asyncio
async def test_profile_store_rejects_symlink_component(tmp_path: Path) -> None:
    project = _project()
    context = _build_evidence_context(project, "observation-a", TREE, _readme())
    identity = _identity(project, context.evidence)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / "profile-store").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="unsafe"):
        load_profile_store(tmp_path, identity)
    assert not profile_store_path(tmp_path, identity).exists()
