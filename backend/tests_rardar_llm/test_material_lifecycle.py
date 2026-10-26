"""Existing durable attempts drive recovery; no source or Provider is contacted."""

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.rardar.profile_cache_v2 import latest_attempt, record_failure, retry_is_due


def test_same_content_semantic_failures_stop_paid_retries_after_existing_allowance(tmp_path):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    identity = "a" * 64
    first = record_failure(
        tmp_path,
        42,
        identity,
        error_code="profile_model_invalid_output",
        retryable=True,
        source_failure_stage="positioning",
        now=start,
    )
    assert first.retryable
    assert not retry_is_due(tmp_path, 42, identity, now=start + timedelta(minutes=4))
    assert retry_is_due(tmp_path, 42, identity, now=start + timedelta(minutes=6))
    second = record_failure(
        tmp_path,
        42,
        identity,
        error_code="profile_model_invalid_output",
        retryable=True,
        source_failure_stage="positioning",
        now=start + timedelta(minutes=6),
    )
    assert second.attemptCount == 2
    assert not second.retryable
    assert second.nextRetryAt is None
    assert not retry_is_due(tmp_path, 42, identity, now=start + timedelta(days=4))
    assert not retry_is_due(tmp_path, 42, identity, now=start + timedelta(days=4), force_retryable=True)
    # Changed evidence/rules have a different identity, not a reset of old debit.
    assert retry_is_due(tmp_path, 42, "b" * 64, now=start + timedelta(days=4))
    assert latest_attempt(tmp_path, 42, identity).attemptCount == 2


def test_network_failures_retain_existing_backoff_and_are_not_semantic_exhaustion(tmp_path):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    for offset in range(3):
        attempt = record_failure(
            tmp_path,
            42,
            "a" * 64,
            error_code="profile_source_timeout",
            retryable=True,
            source_failure_stage="readme",
            now=start + timedelta(days=offset),
        )
    assert attempt.retryable
    assert not retry_is_due(tmp_path, 42, "a" * 64, now=attempt.lastAttemptAt)
    assert retry_is_due(tmp_path, 42, "a" * 64, now=attempt.nextRetryAt)
    # Transport failures do not silently spend the semantic-content allowance.
    semantic = record_failure(
        tmp_path,
        42,
        "a" * 64,
        error_code="profile_model_invalid_output",
        retryable=True,
        source_failure_stage="positioning",
        now=start + timedelta(days=4),
    )
    assert semantic.attemptCount == 4
    assert semantic.retryable


def test_retained_retryable_semantic_receipts_are_stopped_without_rewriting_history(tmp_path):
    import json

    from app.integrations.rardar.profile_cache_v2 import digest

    start = datetime(2026, 10, 1, tzinfo=UTC)
    for offset in range(2):
        record_failure(
            tmp_path,
            42,
            "a" * 64,
            error_code="profile_model_invalid_output",
            retryable=True,
            source_failure_stage="positioning",
            now=start + timedelta(days=offset),
        )
    # An old version recorded all semantic failures as retryable forever. Its
    # v1 schema/digest remains valid and the new reader does not mutate it.
    path = sorted((tmp_path / "profile-attempts" / "v1" / "42" / ("a" * 64)).glob("*.json"))[-1]
    payload = json.loads(path.read_bytes())
    payload["retryable"] = True
    payload["nextRetryAt"] = (start + timedelta(days=1, minutes=30)).isoformat().replace("+00:00", "Z")
    payload["recordDigest"] = digest({key: value for key, value in payload.items() if key != "recordDigest"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    assert not retry_is_due(tmp_path, 42, "a" * 64, now=start + timedelta(days=3), force_retryable=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("profile_source_timeout", "retry_transient_later"),
        ("profile_source_rate_limited", "retry_transient_later"),
        ("profile_evidence_mismatch", "needs_identity_evidence"),
        ("profile_evidence_incomplete", "degrade_with_evidence"),
        ("profile_path_unsafe", "not_recoverable_without_new_input"),
    ],
)
def test_action_uses_recorded_failure_not_generic_two_failures(tmp_path, code, expected):
    from app.services.rardar_material_lifecycle import material_next_action

    start = datetime(2026, 10, 1, tzinfo=UTC)
    record_failure(
        tmp_path,
        42,
        "a" * 64,
        error_code=code,
        retryable=code in {"profile_source_timeout", "profile_source_rate_limited"},
        source_failure_stage="collector",
        now=start,
    )
    attempt = latest_attempt(tmp_path, 42, "a" * 64)
    action = material_next_action(identity_verified=True, attempt=attempt, now=start)
    assert action["action"] == expected
    assert action["reason"] == code
    assert action["nextAllowedAt"] == (attempt.nextRetryAt.isoformat() if attempt.nextRetryAt else None)


def test_cache_only_work_precedes_budget_wait_and_unknown_does_not_become_zero():
    from app.services.rardar_material_lifecycle import material_next_action

    assert material_next_action(identity_verified=True, has_saved_stages=True, budget_available=False)["action"] == (
        "cache_only_reassemble"
    )
    assert material_next_action(identity_verified=True, budget_available=False)["action"] == "defer_budget"
    assert material_next_action(identity_verified=False)["action"] == "needs_identity_evidence"
    assert material_next_action(identity_verified=True, source_changed=True)["action"] == "fetch_changed_source"
    assert material_next_action(identity_verified=True)["action"] == "resume_missing_stage"
    identity_wait = material_next_action(
        identity_verified=True, has_saved_stages=True, previous_code="repository_identity_mismatch"
    )
    assert identity_wait["action"] == "needs_identity_evidence" and not identity_wait["canReassemble"]
    assert (
        material_next_action(identity_verified=True, previous_code="daily_budget_exhausted")["action"] == "defer_budget"
    )
    cooperative = material_next_action(identity_verified=True, previous_code="interactive_request_waiting")
    assert cooperative["action"] == "resume_missing_stage"
    assert cooperative["reason"] == "interactive_request_waiting" and not cooperative["requiresProvider"]


def test_content_revision_ignores_board_metric_and_generation_changes_but_tracks_material_changes():
    from app.integrations.rardar.serving_profiles import _build_evidence_context
    from app.services.rardar_material_lifecycle import source_content_digest
    from tests_rardar_selection.test_profile_cache_v2 import TREE, _project, _readme

    project = _project()
    original = _build_evidence_context(project, "original", TREE, _readme()).evidence
    changed_metrics = project.model_copy(update={"rank": 15, "totalStars": project.totalStars + 500})
    repeated = _build_evidence_context(changed_metrics, "tomorrow", TREE, _readme()).evidence
    assert original.digest != repeated.digest
    assert source_content_digest(original) == source_content_digest(repeated)
    readme = _readme()
    readme["markdown"] += "\n## 新能力\n\n支持离线证据整理并把结构化项目地图导出为独立 HTML 文件。\n"
    meaningful = _build_evidence_context(project, "tomorrow", TREE, readme).evidence
    assert source_content_digest(meaningful) != source_content_digest(original)


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_saved_source_reassembly_persists_and_reads_without_any_external_request(tmp_path, monkeypatch, partial):
    import json
    import shutil

    import httpx

    from app.integrations.rardar import serving_profiles, trending_metadata
    from app.integrations.rardar.serving_profiles import collect_official_project_profile
    from app.services.rardar_material_lifecycle import collect_cached_material, persist_cached_material
    from app.services.rardar_trending import saved_materials
    from tests_rardar_selection.test_profile_cache_v2 import _handler, _project

    project = _project()
    if partial:
        monkeypatch.setattr(serving_profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))
    cache_root = tmp_path / "profile-cache"
    calls = []
    route = "a" * 64
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(_handler(calls))
    ) as client:
        first = await collect_official_project_profile(
            project,
            "original-source-generation",
            cache_root,
            client=client,
            translate=True,
            model_route_identity=route,
            save_partial_introduction=True,
        )
    assert first.translation_calls == 0
    fact = {"repository": project.repository, "githubRepositoryId": project.githubRepositoryId}
    trending_metadata.save(
        tmp_path,
        fact,
        {
            "id": project.githubRepositoryId,
            "full_name": project.repository,
            "description": project.description,
            "language": project.primaryLanguage,
            "topics": project.topics,
            "license": {"spdx_id": project.licenseSpdxId},
            "default_branch": project.defaultBranch,
        },
    )
    # Isolated failure model: durable source/stages survive a missing final store.
    if (cache_root / "profile-store").exists():
        shutil.rmtree(cache_root / "profile-store")
    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    cached = await collect_cached_material(tmp_path, fact, route)
    assert cached is not None
    assert cached.receipt["sourceMode"] == "saved_evidence_not_refetched"
    assert cached.receipt["readmeCheckedAt"] is None
    assert cached.receipt["sourceGeneration"] == "original-source-generation"
    assert cached.receipt["providerRequests"] == cached.receipt["sourceRequests"] == 0
    assert before == {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    saved = persist_cached_material(tmp_path, cached)
    assert saved.profile_cache_state == ("partial_reused" if partial else "rebound")
    material = saved_materials(tmp_path, repositories={project.repository})[project.repository]
    assert material["materialState"] == ("partial" if partial else "complete")
    assert material["displayProfile"]["positioningZh"] == saved.profile.positioningZh
    if partial:
        assert not (cache_root / "profile-store").exists()
        assert cached.receipt["modelGeneratedAt"] is None
        assert before == {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    # Repeated reads and reassembly reuse the same immutable final record.
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    repeated = await collect_cached_material(tmp_path, fact, route)
    persist_cached_material(tmp_path, repeated)
    assert after == {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*.json")}
    artifact = cache_root / "readmes" / str(project.githubRepositoryId) / ("a" * 40 + ".json")
    polluted = json.loads(artifact.read_bytes())
    polluted["repository"] = "other/unproven-identity"
    artifact.write_text(json.dumps(polluted), encoding="utf-8")
    with pytest.raises(ValueError, match="cache_reassembly_readme_mismatch"):
        await collect_cached_material(tmp_path, fact, route)
