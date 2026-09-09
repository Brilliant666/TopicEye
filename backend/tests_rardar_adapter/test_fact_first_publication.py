"""Today v8 publishes verified facts independently from optional reading material."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from app.integrations.rardar import serving
from app.integrations.rardar.adapter import RardarIntelligenceAdapter
from app.integrations.rardar.serving_schemas import ServingCapability, ServingTodaySnapshot
from tests_rardar_adapter.test_serving import _root


def _board(root):
    board = RardarIntelligenceAdapter.from_config(str(root)).load_explosion_board()
    template = board.exactRanked[0]
    projects = [
        template.model_copy(
            update={
                "githubRepositoryId": 80000 + rank,
                "rank": rank,
                "repository": f"fixture/project-{rank}",
                "htmlUrl": f"https://github.com/fixture/project-{rank}",
                "description": "A documented developer tool.",
                "observedStarDelta": 1000 - rank,
                "totalStars": 2000,
                "baselineStars": 1000 + rank,
            }
        )
        for rank in range(1, 21)
    ]
    return board.model_copy(
        update={"exactRanked": projects, "coverage": board.coverage.model_copy(update={"exactCount": 20})}
    )


def _build(root, board, provider=None):
    manifest, artifact = serving.source_hashes(root, board.generationId)
    return serving.build_serving_projection(
        board=board,
        source_manifest_sha256=manifest,
        source_explosion_sha256=artifact,
        synced_at=None,
        source_host=None,
        cache_root=root / "profile-cache",
        profile_provider=provider,
    )


def _facts(items):
    return [
        (
            p.githubRepositoryId,
            p.repository,
            p.rank,
            p.totalStars,
            p.observedStarDelta,
            p.windowStartedAt,
            p.windowEndedAt,
        )
        for p in items
    ]


@pytest.mark.parametrize("missing", [1, 7, 20])
def test_missing_optional_material_keeps_all_twenty_facts_and_details(tmp_path, missing):
    root = _root(tmp_path)
    board = _board(root)

    def provider(projects, generation, cache):
        result = serving._fallback_profiles(projects, generation, cache)
        values = dict(result.profiles)
        for i, (key, value) in enumerate(values.items()):
            if i >= missing:
                summary = "一个帮助开发者组织文档的工具。"
                values[key] = replace(
                    value,
                    profile=value.profile.model_copy(
                        update={
                            "officialSummaryZh": summary,
                            "identitySummaryZh": summary,
                            "claimEvidenceRefs": {summary: ["description"]},
                        }
                    ),
                )
        return replace(result, profiles=values)

    built = _build(root, board, provider)
    assert built.publication_audit["activationAllowed"] is True
    serving.install_serving_projection(root, built)
    loader = serving.ServingProjectionLoader(root)
    today, _ = loader.load_today_with_etag()
    assert today.schemaVersion == 8
    assert _facts(today.exactRanked) == _facts(board.exactRanked)
    assert len(today.exactRanked) == 20
    for i, project in enumerate(today.exactRanked):
        detail, _ = loader.load_project_with_etag(project.githubRepositoryId, board.generationId)
        assert _facts([detail.project]) == _facts([project])
        if i < missing:
            assert detail.profile.summarySource == "original_description"
            assert detail.profile.officialSummaryZh is None
        else:
            assert detail.profile.summarySource == "chinese_profile"


def test_same_facts_can_gain_material_without_changing_rank_and_repeat_is_noop(tmp_path):
    root = _root(tmp_path)
    board = _board(root)
    bare = _build(root, board)
    serving.install_serving_projection(root, bare)

    def enriched(projects, generation, cache):
        result = serving._fallback_profiles(projects, generation, cache)
        key = projects[0].githubRepositoryId
        item = result.profiles[key]
        summary = "一个帮助开发者组织文档的工具。"
        position = "通过可追溯文档帮助开发者核对工具的适用范围。"
        detail = "将工具说明组织为可查阅的文档，帮助开发者核对使用方式。"
        profile = item.profile.model_copy(
            update={
                "officialSummaryZh": summary,
                "identitySummaryZh": summary,
                "positioningZh": position,
                "positioningEvidenceRefs": ["description"],
                "officialPositioningZh": position,
                "officialPositioningEvidenceRefs": ["description"],
                "positioningIncludedRoles": ["core_mechanism", "primary_outcome"],
                "positioningSourceMode": "rardar_derived",
                "capabilities": [
                    ServingCapability(
                        title="文档组织", detail=detail, evidenceRefs=["description"], sourceMode="rardar_derived"
                    )
                ],
                "claimEvidenceRefs": {summary: ["description"], position: ["description"], detail: ["description"]},
            }
        )
        return replace(result, profiles={**result.profiles, key: replace(item, profile=profile)})

    complete = _build(root, board, enriched)
    serving.install_serving_projection(root, complete)
    today, _ = serving.ServingProjectionLoader(root).load_today_with_etag()
    assert _facts(today.exactRanked) == _facts(board.exactRanked)
    assert today.exactRanked[0].materialState == "complete"
    assert today.exactRanked[0].identitySummaryZh == "一个帮助开发者组织文档的工具。"
    assert complete.serving_generation_id != bare.serving_generation_id
    assert (root / "serving/generations" / bare.serving_generation_id).is_dir()
    again = _build(root, board, enriched)
    assert again.files == complete.files
    assert again.serving_generation_id == complete.serving_generation_id
    assert serving.install_serving_projection(root, again).changed is False


def test_bad_optional_reference_is_omitted_but_identity_and_digest_are_not_repaired(tmp_path):
    root = _root(tmp_path)
    board = _board(root)

    def provider(projects, generation, cache):
        result = serving._fallback_profiles(projects, generation, cache)
        key = projects[0].githubRepositoryId
        item = result.profiles[key]
        profile = item.profile.model_copy(
            update={
                "identitySummaryZh": "未经证据支持的能力声明。",
                "officialSummaryZh": "未经证据支持的能力声明。",
                "claimEvidenceRefs": {"未经证据支持的能力声明。": ["missing-evidence"]},
            }
        )
        return replace(result, profiles={**result.profiles, key: replace(item, profile=profile)})

    built = _build(root, board, provider)
    assert "未经证据支持的能力声明" not in built.files["today.json"].decode()
    for field, value in (("repository", "attacker/other"), ("evidenceDigest", "0" * 64)):

        def corrupt(projects, generation, cache, field=field, value=value):
            result = provider(projects, generation, cache)
            key = projects[0].githubRepositoryId
            item = result.profiles[key]
            return replace(
                result,
                profiles={
                    **result.profiles,
                    key: replace(item, profile=item.profile.model_copy(update={field: value})),
                },
            )

        with pytest.raises((ValueError, serving.ServingProjectionError)):
            _build(root, board, corrupt)
    files = {**built.files, "today.json": b"{}"}
    with pytest.raises(serving.ServingProjectionError):
        serving._validate_built_projection(built.pointer_raw, files)


def test_v7_still_rejects_missing_top20_capabilities(tmp_path):
    root = _root(tmp_path)
    built = _build(root, _board(root))
    payload = json.loads(built.files["today.json"])
    payload["schemaVersion"] = 7
    with pytest.raises(ValueError):
        ServingTodaySnapshot.model_validate_json(json.dumps(payload), strict=True)


def test_no_description_and_no_ai_still_has_readable_identity_and_fact_details(tmp_path):
    root = _root(tmp_path)
    board = _board(root)
    board = board.model_copy(
        update={
            "exactRanked": [p.model_copy(update={"description": None}) for p in board.exactRanked],
        }
    )
    built = _build(root, board)
    assert built.profile_result.translation_calls == 0
    serving.install_serving_projection(root, built)
    loader = serving.ServingProjectionLoader(root)
    today, _ = loader.load_today_with_etag()
    assert _facts(today.exactRanked) == _facts(board.exactRanked)
    for project in today.exactRanked:
        assert project.materialState == "unavailable"
        assert project.identitySummaryZh is None
        assert project.originalDescription is None
        detail, _ = loader.load_project_with_etag(project.githubRepositoryId, board.generationId)
        assert str(detail.project.htmlUrl).startswith("https://github.com/fixture/")
        assert detail.profile.capabilities == []


def test_unchanged_collector_material_reuses_saved_generated_time(tmp_path):
    root = _root(tmp_path)
    board = _board(root)
    first = _build(root, board)
    serving.install_serving_projection(root, first)

    def recollect(projects, generation, cache):
        result = serving._fallback_profiles(projects, generation, cache)
        return replace(
            result,
            profiles={
                key: replace(
                    item,
                    profile=item.profile.model_copy(
                        update={
                            "generatedAt": item.profile.generatedAt + timedelta(hours=1),
                        }
                    ),
                )
                for key, item in result.profiles.items()
            },
        )

    second = _build(root, board, recollect)
    assert second.serving_generation_id == first.serving_generation_id
    assert second.files == first.files
    assert serving.install_serving_projection(root, second).changed is False
    # The reused material must come from a fully validated current, not merely
    # from a matching file name or a forgiving read of damaged published data.
    today_path = root / "serving/generations" / first.serving_generation_id / "today.json"
    today_path.write_bytes(b"{}")
    serving.clear_serving_cache()
    with pytest.raises(serving.ServingProjectionError):
        _build(root, board, recollect)
