"""Independently valid primary fields survive optional-stage failure and restart."""

import httpx
import pytest

from app.integrations.rardar import project_introductions as introductions, serving_profiles as profiles
from tests_rardar_selection.test_profile_cache_v2 import _handler, _project, _readme


def _files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*.json")}


@pytest.mark.asyncio
async def test_partial_primary_reassembles_without_source_or_provider_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        first = await profiles.collect_official_project_profile(
            project,
            "board-first",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    assert first.profile.positioningZh and not first.profile.capabilities
    assert not profiles._profile_is_publishable(first.profile)  # full contract remains unchanged
    saved = introductions.saved(tmp_path)[project.repository.lower()]
    assert saved["reuseIdentity"]["repositoryId"] == project.githubRepositoryId
    assert saved["reuseIdentity"]["identityDigest"]
    readme = profiles._cached_readme(tmp_path, project)
    assert readme is not None and readme["sha"] == first.evidence.readmeBlobSha
    source = (first.evidence.topLevelTree, readme)
    before = _files(tmp_path)

    def deny(_request):
        raise AssertionError("partial reuse must not fetch a source or call a Provider")

    async def deny_model(_payload):
        raise AssertionError("partial reuse must not regenerate the already valid primary")

    async with httpx.AsyncClient(transport=httpx.MockTransport(deny)) as client:
        resumed = await profiles.collect_official_project_profile(
            project,
            "board-after-restart",
            tmp_path,
            client=client,
            translate=True,
            translator=deny_model,
            narrative_translator=deny_model,
            positioning_translator=deny_model,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            cache_only=True,
            cached_source=source,
        )
    assert resumed.profile_cache_state == "partial_reused"
    assert resumed.translation_calls == resumed.github_requests == 0
    assert resumed.profile.positioningZh == first.profile.positioningZh
    assert resumed.profile.generatedAt == first.profile.generatedAt
    assert resumed.profile.generationId == "board-after-restart"
    assert resumed.profile.evidenceDigest == resumed.evidence.digest
    assert resumed.profile.capabilities == []
    assert not profiles._profile_is_publishable(resumed.profile)
    assert _files(tmp_path) == before


@pytest.mark.asyncio
async def test_partial_reuse_binding_does_not_bless_changed_material_or_route(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        first = await profiles.collect_official_project_profile(
            project,
            "first",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    saved = introductions.saved(tmp_path)[project.repository.lower()]
    # Old schema-2 partials remain valid reading material, but lacking a route/
    # rule/content binding must not silently upgrade them to reusable stages.
    legacy = dict(saved)
    legacy.pop("reuseIdentity")
    assert introductions.material(legacy)["materialState"] == "partial"
    introductions.save(
        tmp_path / "legacy-only",
        first.evidence,
        first.profile.identitySummaryZh,
        first.profile.claimEvidenceRefs[first.profile.identitySummaryZh],
        source_mode=saved["sourceMode"],
        source_label=saved["sourceLabel"],
        partial_profile=first.profile,
    )
    readme = profiles._cached_readme(tmp_path, project)
    assert readme is not None and readme["sha"] == first.evidence.readmeBlobSha
    original = profiles._build_evidence_context(project, "next", first.evidence.topLevelTree, readme)
    original_ids = profiles._profile_identity_candidates(project, original.evidence, "official_zh", "a" * 64)
    assert (
        introductions.compatible_partial(tmp_path / "legacy-only", project, original.evidence, original_ids, "a" * 64)
        is None
    )
    assert introductions.compatible_partial(tmp_path, project, original.evidence, original_ids, "a" * 64)
    context = profiles._build_evidence_context(project, "next", first.evidence.topLevelTree, None)
    identities = profiles._profile_identity_candidates(project, context.evidence, "rardar_derived", "a" * 64)
    assert introductions.compatible_partial(tmp_path, project, context.evidence, identities, "a" * 64) is None

    # A model-derived primary needs its actual route; a native-Chinese primary
    # is intentionally reusable without inventing a model dependency.
    translated = first.profile.model_copy(
        update={
            "translationState": "translated",
            "officialNarrativeMode": "rardar_derived",
            "sourceLabel": "Rardar 整理",
        }
    )
    route_identity = profiles._profile_identity_for_result(
        project,
        first.evidence,
        translated,
        model_route_identity="a" * 64,
        model_derived_used=True,
        deterministic_fallback_used=False,
    )
    introductions.save(
        tmp_path / "translated-only",
        first.evidence,
        translated.identitySummaryZh,
        translated.claimEvidenceRefs[translated.identitySummaryZh],
        source_mode="validated_translation",
        source_label=translated.sourceLabel,
        partial_profile=translated,
        reuse_identity=route_identity,
    )
    different_route = profiles._profile_identity_candidates(project, original.evidence, "rardar_derived", "b" * 64)
    assert (
        introductions.compatible_partial(
            tmp_path / "translated-only", project, original.evidence, different_route, "b" * 64
        )
        is None
    )


@pytest.mark.asyncio
async def test_explicit_source_refresh_checks_tree_and_new_readme_without_provider(tmp_path):
    import base64

    from tests_rardar_selection.test_profile_cache_v2 import MARKDOWN, TREE

    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        first = await profiles.collect_official_project_profile(
            project,
            "first",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )
    assert first.profile_cache_state == "rebuilt"
    calls = []

    def changed(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}, *TREE[1:]])
        assert request.url.path.endswith("/readme")
        return httpx.Response(
            200,
            json={
                "path": "README.md",
                "sha": "b" * 40,
                "encoding": "base64",
                "content": base64.b64encode(MARKDOWN.encode()).decode(),
            },
        )

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(changed)) as client:
        refreshed = await profiles.collect_official_project_profile(
            project,
            "next",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            refresh_source=True,
        )
    assert len(calls) == refreshed.github_requests == 2
    assert refreshed.translation_calls == 0
    assert refreshed.evidence.readmePath == "README.md"
    assert refreshed.evidence.readmeBlobSha == "b" * 40
    assert refreshed.profile_cache_state == "rebuilt"
    assert (tmp_path / "readmes" / str(project.githubRepositoryId) / f"{'a' * 40}.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["a" * 64, None])
async def test_source_refresh_failure_preserves_old_profile_without_claiming_fresh_hit(tmp_path, route):
    project = _project()
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        first = await profiles.collect_official_project_profile(
            project,
            "first",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )
    original = _files(tmp_path / "profile-store")

    def unavailable(_request):
        return httpx.Response(503)

    async def deny_model(_payload):
        raise AssertionError("failed source refresh may not pay for unverified current evidence")

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(unavailable)
    ) as client:
        failed = await profiles.collect_official_project_profile(
            project,
            "next",
            tmp_path,
            client=client,
            translate=True,
            translator=deny_model,
            narrative_translator=deny_model,
            positioning_translator=deny_model,
            model_route_identity=route,
            refresh_source=True,
        )
    assert first.profile_cache_state == "rebuilt"
    assert failed.profile_cache_state == "unavailable"
    assert failed.profile_failure_code == "profile_source_http_5xx"
    assert failed.translation_calls == 0
    assert _files(tmp_path / "profile-store") == original


@pytest.mark.asyncio
async def test_zero_model_check_does_not_create_content_failure_or_exhaust_retry(tmp_path):
    import base64

    project = _project().model_copy(update={"description": "A bounded evidence processing tool for technical teams."})

    def source(request):
        if request.url.path.endswith("/contents"):
            return httpx.Response(200, json=[{"path": "README.md", "type": "file"}])
        return httpx.Response(
            200,
            json={
                "path": "README.md",
                "sha": "c" * 40,
                "encoding": "base64",
                "content": base64.b64encode(
                    b"# A tool\n\nA bounded evidence processing tool for technical teams.\n"
                ).decode(),
            },
        )

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(source)) as client:
        result = await profiles.collect_official_project_profile(
            project,
            "first",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
        )
    assert result.profile_cache_state == "unavailable"
    assert result.translation_calls == 0 and result.profile_failure_code is None
    assert not list((tmp_path / "profile-attempts").rglob("*.json"))


@pytest.mark.asyncio
async def test_zero_model_semantic_rejection_keeps_diagnostic_without_retry_receipt(tmp_path, monkeypatch):
    rule = "profile_serving_v6_positioning_requires_a_mechanism_or_primary_outcome"
    code = f"positioning_candidate_official_zh_{rule}"
    monkeypatch.setattr(profiles, "_select_positioning_candidate", lambda *_a, **_kw: (None, [code]))
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        result = await profiles.collect_official_project_profile(
            _project(),
            "semantic-check",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    assert result.profile.positioningZh is None and result.translation_calls == 0
    assert result.profile_failure_code == "profile_model_invalid_output"
    failure = next(item for item in result.generation_failures if item.code == code)
    assert failure.diagnostic["classification"] == "semantic_invalid"
    assert failure.diagnostic["ruleCode"] == rule
    assert not list((tmp_path / "profile-attempts").rglob("*.json"))


def test_readme_blob_artifact_is_immutable_while_check_receipt_changes(tmp_path):
    project = _project()
    original = {
        "schemaVersion": 2,
        "repository": project.repository,
        "sha": "a" * 40,
        "path": "README.md",
        "etag": '"one"',
        "markdown": "# Project\n\nThe original material.\n",
        "fetchedAt": "2026-01-01T08:00:00+00:00",
    }
    profiles._store_readme_cache(tmp_path, project, original)
    path = profiles._readme_artifact_path(tmp_path, project.githubRepositoryId, original["sha"], original["path"])
    first_bytes = path.read_bytes()
    profiles._store_readme_cache(
        tmp_path,
        project,
        {**original, "etag": '"two"', "fetchedAt": "2026-01-02T08:00:00+00:00"},
    )
    assert path.read_bytes() == first_bytes
    current = profiles._cached_readme(tmp_path, project)
    assert current["etag"] == '"two"'
    assert current["fetchedAt"] == original["fetchedAt"]
    assert current["checkedAt"]
    with pytest.raises(ValueError, match="readme_blob_content_mismatch"):
        profiles._store_readme_cache(tmp_path, project, {**original, "markdown": "An unrelated claim."})
    assert path.read_bytes() == first_bytes

    # A real path move with the same Git Blob is not identity contamination.
    # Preserve both source paths instead of overwriting an old evidence file.
    moved = {**original, "path": "docs/README.md"}
    profiles._store_readme_cache(tmp_path, project, moved)
    moved_path = profiles._readme_artifact_path(tmp_path, project.githubRepositoryId, original["sha"], moved["path"])
    assert moved_path != path and moved_path.exists()
    assert profiles._cached_readme(tmp_path, project)["path"] == "docs/README.md"
    assert path.read_bytes() == first_bytes
    renamed = project.model_copy(update={"repository": "renamed-org/renamed-project"})
    profiles._store_readme_cache(tmp_path, renamed, {**original, "repository": renamed.repository})
    assert profiles._cached_readme(tmp_path, renamed)["repository"] == renamed.repository
    assert path.read_bytes() == first_bytes


@pytest.mark.parametrize("pointer_created_first", [False, True])
def test_saved_readme_source_is_selected_by_current_pointer_not_directory_order(tmp_path, pointer_created_first):
    project = _project()
    directory = tmp_path / "readmes" / str(project.githubRepositoryId)
    if pointer_created_first:
        profiles._atomic_json(
            directory / "current.json", {"schemaVersion": 2, "repository": project.repository, "sha": "a" * 40}
        )
    # A retained older Blob and the pointer are both JSON files, neither is a
    # substitute for the source currently referenced by the real cache reader.
    profiles._store_readme_cache(tmp_path, project, {**_readme("0" * 40), "repository": project.repository})
    profiles._store_readme_cache(tmp_path, project, {**_readme(), "repository": project.repository})
    assert len(list(directory.glob("*.json"))) == 3
    selected = profiles._cached_readme(tmp_path, project)
    assert selected["sha"] == "a" * 40
    assert selected["path"] == "README_ZH.md" and selected["markdown"] == _readme()["markdown"]


@pytest.mark.asyncio
async def test_source_witness_reads_moved_blob_without_rewriting_original_evidence(tmp_path, monkeypatch):
    from app.services.rardar_cache_reassembly import _source_witness
    from tests_rardar_selection.test_profile_cache_v2 import MARKDOWN, TREE

    project = _project()
    readme = {
        "schemaVersion": 2,
        "repository": project.repository,
        "sha": "a" * 40,
        "path": "README_ZH.md",
        "markdown": MARKDOWN,
        "etag": '"one"',
    }
    profiles._store_readme_cache(tmp_path, project, readme)
    original = (tmp_path / "readmes" / str(project.githubRepositoryId) / f"{'a' * 40}.json").read_bytes()
    moved = {**readme, "path": "docs/README_ZH.md"}
    profiles._store_readme_cache(tmp_path, project, moved)
    profiles._atomic_json(
        profiles._tree_cache_path(tmp_path, project),
        {"schemaVersion": 1, "repository": project.repository, "items": [*TREE, {"path": "docs", "type": "dir"}]},
    )
    monkeypatch.setattr(profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))

    def deny(_request):
        raise AssertionError("source-witness test must never leave the persisted cache")

    async with httpx.AsyncClient(transport=httpx.MockTransport(deny)) as client:
        # Build the ordinary partial artifact through the collector using the
        # already saved moved source; this is not a fabricated source response.
        await profiles.collect_official_project_profile(
            project,
            "moved-source",
            tmp_path,
            client=client,
            translate=True,
            allow_model_generation=False,
            model_route_identity="a" * 64,
            save_partial_introduction=True,
        )
    witness, saved_readme = _source_witness(tmp_path, project.repository.lower(), project.githubRepositoryId)
    assert saved_readme["path"] == witness["evidence"]["readmePath"] == "docs/README_ZH.md"
    assert saved_readme["markdown"] == MARKDOWN
    assert (tmp_path / "readmes" / str(project.githubRepositoryId) / f"{'a' * 40}.json").read_bytes() == original


@pytest.mark.asyncio
async def test_verified_numeric_identity_rename_rebinds_profile_without_model(tmp_path):
    project = _project()

    async def deny_model(_payload):
        raise AssertionError("proven rename of unchanged material must not regenerate it")

    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler([]))
    ) as client:
        first = await profiles.collect_official_project_profile(
            project,
            "before-rename",
            tmp_path,
            client=client,
            translate=True,
            translator=deny_model,
            narrative_translator=deny_model,
            positioning_translator=deny_model,
            model_route_identity="a" * 64,
        )
    original = _files(tmp_path / "profile-store")
    renamed = project.model_copy(
        update={"repository": "another-owner/renamed", "htmlUrl": "https://github.com/another-owner/renamed"}
    )
    calls = []
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler(calls))
    ) as client:
        rebound = await profiles.collect_official_project_profile(
            renamed,
            "after-rename",
            tmp_path,
            client=client,
            translate=True,
            translator=deny_model,
            narrative_translator=deny_model,
            positioning_translator=deny_model,
            model_route_identity="a" * 64,
            refresh_source=True,
        )
    assert rebound.profile_cache_state == "rebound"
    assert rebound.profile.githubRepositoryId == first.profile.githubRepositoryId
    assert rebound.profile.repository == renamed.repository
    assert rebound.profile.generatedAt == first.profile.generatedAt
    assert rebound.profile_revision == first.profile_revision
    assert rebound.translation_calls == 0
    assert rebound.github_requests == len(calls) == 2  # source revalidation, not a paid model round
    assert _files(tmp_path / "profile-store") == original

    def no_source(_request):
        raise AssertionError("an unchanged cached input must not issue an implicit source request")

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(no_source)) as client:
        reused = await profiles.collect_official_project_profile(
            renamed,
            "same-input-again",
            tmp_path,
            client=client,
            translate=True,
            translator=deny_model,
            narrative_translator=deny_model,
            positioning_translator=deny_model,
            model_route_identity="a" * 64,
        )
    assert reused.github_requests == reused.translation_calls == 0
