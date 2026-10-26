"""Numeric continuity proofs over persisted metadata; no external requests."""

from copy import deepcopy
from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.rardar import project_identity as identity, trending_metadata as metadata, trending_store
from tests_rardar_llm.test_rardar_trending_store import board


def response(repository, identifier=42, **changes):
    return {
        "id": identifier,
        "full_name": repository,
        "default_branch": "main",
        "description": "A self-hosted documentation service with full-text search.",
        "language": "Python",
        "topics": ["documentation"],
        "license": {"spdx_id": "MIT"},
        "stargazers_count": 10,
        **changes,
    }


@pytest.mark.parametrize("include_branch,stars", [(False, None), (True, None), (True, 25)])
def test_new_metadata_keeps_deployed_v2_reader_wire_contract(tmp_path, include_branch, stars):
    project = {"repository": "public/tool", "githubRepositoryId": 42}
    source = response(project["repository"], stargazers_count=stars)
    if not include_branch:
        source.pop("default_branch")
    payload = metadata.save(tmp_path, project, source)
    envelope = metadata.read_json(metadata._path(tmp_path, project["repository"]))
    # PR82's real reader accepts schema 1/2 and checks this exact payload set.
    # New source-revision metadata is an additive envelope, not a new wire
    # format that would make unchanged rollback readers discard every cache.
    assert envelope["schemaVersion"] == 2
    assert set(envelope["payload"]) == {
        "repository",
        "githubRepositoryId",
        "language",
        "topics",
        "license",
        "fetchedAt",
        "sourceUrl",
        "description",
        "totalStars",
        "totalStarsFetchedAt",
    }
    assert envelope["payload"] == payload
    assert envelope["digest"] == metadata.digest(payload)
    assert envelope["contentRevision"]["schemaVersion"] == 1
    revision = metadata.content_revision(tmp_path, project)
    assert revision["content"]["defaultBranch"] == ("main" if include_branch else None)
    assert metadata.read_content_version(tmp_path, 42, revision["metadataDigest"])["content"] == revision["content"]
    assert payload["totalStars"] == stars
    assert (payload["totalStarsFetchedAt"] is None) == (stars is None)
    assert metadata.read(tmp_path, project) == payload


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_metadata_can_be_refreshed_without_losing_known_star_time(tmp_path, version):
    project = {"repository": "public/tool", "githubRepositoryId": 42}
    when = datetime.now(UTC).isoformat()
    payload = {
        "repository": project["repository"],
        "githubRepositoryId": 42,
        "language": "Python",
        "topics": [],
        "license": "MIT",
        "fetchedAt": when,
        "sourceUrl": "https://api.github.com/repos/public/tool",
    }
    if version == 2:
        payload.update(description="A public documentation tool.", totalStars=55, totalStarsFetchedAt=when)
    path = metadata._path(tmp_path, project["repository"])
    path.parent.mkdir(parents=True)
    metadata.atomic(path, {"schemaVersion": version, "payload": payload, "digest": metadata.digest(payload)})
    assert metadata.read(tmp_path, project) == payload
    refreshed = metadata.save(
        tmp_path,
        project,
        {
            "id": 42,
            "full_name": project["repository"],
            "description": "A public documentation tool.",
            "language": "Python",
            "topics": [],
            "license": {"spdx_id": "MIT"},
        },
    )
    assert metadata.read_json(path)["schemaVersion"] == 2
    assert refreshed["totalStars"] == (55 if version == 2 else None)
    assert refreshed["totalStarsFetchedAt"] == (when if version == 2 else None)
    assert metadata.content_revision(tmp_path, project)["content"]["defaultBranch"] is None


def test_previous_v3_metadata_remains_readable_and_next_save_restores_v2_wire(tmp_path):
    project = {"repository": "public/tool", "githubRepositoryId": 42}
    payload = metadata.save(tmp_path, project, response(project["repository"]))
    path = metadata._path(tmp_path, project["repository"])
    record = metadata.read_json(path)
    record["schemaVersion"] = 3  # Simulate a record written by the prior branch revision.
    metadata.atomic(path, record)
    assert metadata.read(tmp_path, project) == payload
    original_revision = metadata.content_revision(tmp_path, project)
    archived = metadata.read_content_version(tmp_path, 42, original_revision["metadataDigest"])
    metadata.save(tmp_path, project, response(project["repository"]))
    assert metadata.read_json(path)["schemaVersion"] == 2
    assert metadata.content_revision(tmp_path, project)["revision"] == original_revision["revision"]
    assert metadata.read_content_version(tmp_path, 42, original_revision["metadataDigest"]) == archived


def test_missing_default_branch_does_not_invalidate_a_known_content_revision(tmp_path):
    project = {"repository": "public/tool", "githubRepositoryId": 42}
    metadata.save(tmp_path, project, response(project["repository"]))
    previous = metadata.content_revision(tmp_path, project)
    source = response(project["repository"], stargazers_count=None)
    source.pop("default_branch")
    metadata.save(tmp_path, project, source)
    current = metadata.content_revision(tmp_path, project)
    assert current["content"]["defaultBranch"] == "main"
    assert current["metadataDigest"] == previous["metadataDigest"]
    assert current["revision"] == previous["revision"]
    assert metadata.read(tmp_path, project)["totalStars"] == 10


@pytest.mark.parametrize("corruption", ["revision_schema", "revision_digest", "archive_digest"])
def test_v2_compatible_metadata_still_validates_new_revision_evidence(tmp_path, corruption):
    project = {"repository": "public/tool", "githubRepositoryId": 42}
    saved = metadata.save(tmp_path, project, response(project["repository"]))
    path = metadata._path(tmp_path, project["repository"])
    record = metadata.read_json(path)
    revision = record["contentRevision"]
    if corruption == "archive_digest":
        archive = path.parent / "revisions" / "42" / f"{revision['metadataDigest']}.json"
        contents = metadata.read_json(archive)
        contents["payload"]["content"]["description"] = "Tampered source."
        metadata.atomic(archive, contents)
        with pytest.raises(ValueError, match="repository_content_revision_invalid"):
            metadata.read_content_version(tmp_path, 42, revision["metadataDigest"])
    else:
        revision["schemaVersion" if corruption == "revision_schema" else "recordDigest"] = (
            2 if corruption == "revision_schema" else "0" * 64
        )
        metadata.atomic(path, record)
        with pytest.raises(ValueError, match="repository_content_revision_invalid"):
            metadata.content_revision(tmp_path, project)
    # The legacy facts payload has its own unchanged digest and is independently
    # readable; corrupt derivation evidence is never mistaken for valid input.
    assert metadata.read(tmp_path, project) == saved


@pytest.mark.parametrize("old,new", [("old-team/docs", "new-team/docs"), ("sample/tool", "sample/tool-v2")])
@pytest.mark.asyncio
async def test_new_board_record_upgrades_then_proven_rename_keeps_urls_and_original_facts(tmp_path, old, new):
    original = board("github", [old])
    trending_store.publish_sources(tmp_path, [original])
    before = trending_store.load_snapshot(tmp_path)
    snapshot_file = tmp_path / "trending-boards" / "generations" / f"{before['generationId']}.json"
    immutable = snapshot_file.read_bytes()
    project = before["projects"][0]
    assert project["githubRepositoryId"] is None
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=response(old))

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        assert (await metadata.refresh(tmp_path, [project], client))["updated"] == 1
        assert (await metadata.refresh(tmp_path, [project], client))["reused"] == 1
    assert calls == [f"/repos/{old}"]
    first = identity.resolve(tmp_path, project)
    assert first["githubRepositoryId"] == 42
    assert first["projectId"] == identity.project_id_for_repository(old)

    # A response for a repository already bound to 42 proves name continuity.
    metadata.save(tmp_path, project, response(new))
    current = identity.resolve(tmp_path, {"repository": new, "githubRepositoryId": 42})
    assert current["aliases"] == [old, new]
    assert current["projectId"] == first["projectId"]
    assert identity.identifiers(current) == {
        identity.project_id_for_repository(old),
        identity.project_id_for_repository(new),
    }
    assert metadata.read(tmp_path, project)["repository"] == new
    assert metadata.read(tmp_path, {"repository": new})["githubRepositoryId"] == 42
    projected = metadata.apply(deepcopy(before), tmp_path)["projects"][0]
    assert projected["repository"] == old and projected["projectId"] == project["projectId"]
    assert projected["resolvedRepository"] == new and projected["stableProjectId"] == first["projectId"]
    assert projected["appearances"] == before["projects"][0]["appearances"]
    assert snapshot_file.read_bytes() == immutable


@pytest.mark.asyncio
async def test_redirect_requires_old_numeric_proof_and_never_transfers_other_identity(tmp_path):
    unknown = {"repository": "before/tool", "githubRepositoryId": None}
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/repos/before/tool":
            return httpx.Response(301, headers={"location": "https://api.github.com/repositories/42"})
        return httpx.Response(200, json=response("after/tool"))

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        result = await metadata.refresh(tmp_path, [unknown], client)
        assert result["updated"] == 0 and len(result["failed"]) == 1
        assert identity.resolve(tmp_path, unknown) is None
        assert metadata.read(tmp_path, {"repository": "after/tool"}) is None
        proven = {**unknown, "githubRepositoryId": 42}
        meta = await metadata.fetch(tmp_path, proven, client)
        metadata.save(tmp_path, proven, meta)
    assert identity.resolve(tmp_path, unknown)["repository"] == "after/tool"
    assert calls == ["/repos/before/tool", "/repositories/42"] * 2

    with pytest.raises(ValueError, match="repository_identity"):
        metadata.save(tmp_path, proven, response("after/tool", identifier=43))
    assert metadata.read(tmp_path, proven)["githubRepositoryId"] == 42


@pytest.mark.parametrize(
    "location",
    [
        "https://untrusted.example/repos/after/tool",
        "http://api.github.com/repositories/42",
        "https://api.github.com/repos/after/tool/readme",
        "https://api.github.com/repositories/42?access_token=hidden",
        "https://api.github.com:444/repositories/42",
        "https://user@api.github.com/repositories/42",
    ],
)
@pytest.mark.asyncio
async def test_metadata_redirect_is_bounded_to_public_github_metadata(tmp_path, location):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(301, headers={"location": location})

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="repository_redirect_invalid"):
            await metadata.fetch(tmp_path, {"repository": "before/tool", "githubRepositoryId": 42}, client)
    assert len(calls) == 1
    assert identity.resolve(tmp_path, {"repository": "before/tool"}) is None


def test_material_metadata_revision_ignores_stars_push_time_and_rename(tmp_path):
    project = {"repository": "docs/first", "githubRepositoryId": 42}
    metadata.save(tmp_path, project, response("docs/first"))
    first = metadata.content_revision(tmp_path, project)
    archived_first = metadata.read_content_version(tmp_path, 42, first["metadataDigest"])
    metadata.save(
        tmp_path,
        project,
        response("docs/second", stargazers_count=900, pushed_at="2026-10-26T00:00:00Z"),
    )
    second = metadata.content_revision(tmp_path, project)
    assert second["metadataDigest"] == first["metadataDigest"]
    assert second["revision"] == first["revision"] == 1
    assert second["changedAt"] == first["changedAt"]
    metadata.save(tmp_path, project, response("docs/second", description="Now includes offline full-text search."))
    third = metadata.content_revision(tmp_path, project)
    assert third["revision"] == 2 and third["metadataDigest"] != first["metadataDigest"]
    assert third["content"]["defaultBranch"] == "main"
    metadata.save(tmp_path, project, response("docs/second", description="Now includes offline full-text search."))
    fourth = metadata.content_revision(tmp_path, project)
    assert fourth["revision"] == 2 and fourth["metadataDigest"] == third["metadataDigest"]
    assert metadata.read_content_version(tmp_path, 42, first["metadataDigest"]) == archived_first
    assert archived_first["repository"] == "docs/first"
    assert archived_first["content"]["description"] == response("docs/first")["description"]
    assert len(list((tmp_path / "profile-cache" / "repository-metadata" / "revisions" / "42").glob("*.json"))) == 2


def test_renamed_name_already_bound_to_other_id_is_not_merged(tmp_path):
    metadata.save(tmp_path, {"repository": "before/tool"}, response("before/tool", identifier=42))
    metadata.save(tmp_path, {"repository": "after/tool"}, response("after/tool", identifier=43))
    with pytest.raises(ValueError, match="repository_identity_mismatch"):
        metadata.save(tmp_path, {"repository": "before/tool", "githubRepositoryId": 42}, response("after/tool"))
    assert metadata.read(tmp_path, {"repository": "before/tool"})["githubRepositoryId"] == 42
    assert metadata.read(tmp_path, {"repository": "after/tool"})["githubRepositoryId"] == 43


def test_corrupt_identity_index_is_not_used_to_rebind_content(tmp_path):
    metadata.save(tmp_path, {"repository": "before/tool"}, response("before/tool"))
    path = identity._index_path(tmp_path)
    original = path.read_bytes()
    path.write_bytes(original.replace(b'"before/tool":42', b'"before/tool":43'))
    with pytest.raises(ValueError, match="repository_identity_index_invalid"):
        metadata.read(tmp_path, {"repository": "before/tool"})


def test_material_alias_join_requires_saved_numeric_proof_not_public_hint_fields(tmp_path):
    snapshot = {
        "projects": [
            {
                "repository": "after/tool",
                "projectId": identity.project_id_for_repository("after/tool"),
                "githubRepositoryId": 42,
                "identityAliases": ["before/tool", "after/tool"],
                "resolvedRepository": "before/tool",
            }
        ]
    }
    original_material = {
        "repository": "before/tool",
        "githubRepositoryId": 42,
        "materialState": "partial",
        "displayProfile": {"repository": "before/tool", "positioningZh": "A documented service."},
        "displayEvidence": {"repository": "before/tool", "sourceGeneration": "original-generation"},
    }
    materials = {"before/tool": original_material}
    assert trending_store.apply_materials(snapshot, materials)["projects"][0]["displayProfile"] is None
    assert trending_store.apply_materials(snapshot, materials, target=tmp_path)["projects"][0]["displayProfile"] is None

    metadata.save(tmp_path, {"repository": "before/tool"}, response("before/tool"))
    metadata.save(tmp_path, {"repository": "before/tool", "githubRepositoryId": 42}, response("after/tool"))
    saved = deepcopy(original_material)
    result = trending_store.apply_materials(snapshot, materials, target=tmp_path)["projects"][0]
    assert result["displayProfile"] == original_material["displayProfile"]
    assert result["displayEvidence"] == original_material["displayEvidence"]
    assert original_material == saved  # Original evidence identities are not rewritten.
    assert result["repository"] == "after/tool"

    wrong = {"before/tool": {**original_material, "githubRepositoryId": 43}}
    assert trending_store.apply_materials(snapshot, wrong, target=tmp_path)["projects"][0]["displayProfile"] is None
    conflicting = deepcopy(snapshot)
    conflicting["projects"][0]["githubRepositoryId"] = 43
    assert (
        trending_store.apply_materials(conflicting, materials, target=tmp_path)["projects"][0]["displayProfile"] is None
    )


def test_work_dedup_uses_persisted_identity_and_keeps_source_metrics_unmixed(tmp_path):
    metadata.save(tmp_path, {"repository": "before/tool"}, response("before/tool"))
    metadata.save(tmp_path, {"repository": "before/tool", "githubRepositoryId": 42}, response("after/tool"))
    rows = [
        {"repository": "before/tool", "githubRepositoryId": 42, "totalStars": 5, "appearances": [{"rank": 1}]},
        {"repository": "after/tool", "githubRepositoryId": 42, "totalStars": 8, "appearances": [{"rank": 9}]},
        {"repository": "after/tool-extra", "githubRepositoryId": 42, "totalStars": 2, "appearances": [{"rank": 3}]},
    ]
    before = deepcopy(rows)
    result = identity.unique_projects(tmp_path, rows)
    assert len(result) == 2
    assert result[0]["repository"] == "after/tool"
    assert result[0]["sourceRepositories"] == ["before/tool", "after/tool"]
    assert set(result[0]["sourceProjectIds"]) == {
        identity.project_id_for_repository(row["repository"]) for row in rows[:2]
    }
    assert result[0]["totalStars"] == 8 and result[0]["appearances"] == [{"rank": 9}]
    # A similar name, or a number without the same saved alias proof, cannot
    # inherit continuity solely from a caller-supplied numeric hint.
    assert result[1]["repository"] == "after/tool-extra"
    assert "stableProjectId" not in result[1]
    assert rows == before


def test_unproven_rename_does_not_share_a_processing_slot(tmp_path):
    rows = [{"repository": name, "githubRepositoryId": 42} for name in ("before/tool", "after/tool")]
    assert len(identity.unique_projects(tmp_path, rows)) == 2
