"""Real persisted worker continuations with virtual GitHub and no Provider IO."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.integrations.rardar import profile_cache_v2, trending_metadata, trending_store
from app.services import rardar_trending as service
from app.services.llm import daily_provider_budget
from tests_rardar_llm.test_material_recovery_orchestration import (
    add,
    history,
    recovery as recovery_fixture,
    seed,
    work,
)
from tests_rardar_llm.test_rardar_trending_store import board

recovery = recovery_fixture  # reuse the real temporary material-store fixture


def current_board(recovery, project):
    value = board("github", [project.repository])
    value["entries"][0].update(reportedDelta=250, githubRepositoryId=project.githubRepositoryId)
    trending_store.publish_sources(recovery.target, [value])


@pytest.mark.asyncio
@pytest.mark.parametrize("header_kind", ["retry_after_seconds", "retry_after_date", "rate_limit_reset"])
async def test_metadata_rate_limit_waits_for_saved_retry_window_then_recovers(recovery, monkeypatch, header_kind):
    project = add(recovery, "recovery/rate-window", 851)
    current_board(recovery, project)
    clock = {"now": datetime.now(UTC).replace(microsecond=0)}
    available_at = clock["now"] + timedelta(seconds=60)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"].astimezone(tz) if tz else clock["now"].replace(tzinfo=None)

    monkeypatch.setattr(service, "datetime", Clock)
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 80}), {})),
    )
    headers = (
        {"Retry-After": "60"}
        if header_kind == "retry_after_seconds"
        else {"Retry-After": format_datetime(available_at, usegmt=True)}
        if header_kind == "retry_after_date"
        else {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(available_at.timestamp()))}
    )
    status = 403 if header_kind == "rate_limit_reset" else 429
    calls = []

    def response(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(status, headers=headers, json={"message": "rate limited"})
        return recovery.response(request)

    @asynccontextmanager
    async def client(_token):
        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(response)
        ) as value:
            yield value

    monkeypatch.setattr(service, "github_material_client", client)
    first = await work(recovery, {})
    assert first["failed"] == 1
    progress = service.read_json(recovery.target / "progress.json")
    second = await work(recovery, progress)
    assert calls == [f"/repos/{project.repository}"]
    record = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"][project.repository]
    assert record["failures"] == 1 and record["providerRequests"] == 0
    assert datetime.fromisoformat(record["nextRetryAt"]) == available_at
    assert second["failed"] == 0 and second["visited"] == 0
    assert second["waitReason"] == "source_rate_limit_wait"
    attempt = service.read_json(recovery.target / "trending-boards" / "material-work.json")["_attempts"][
        project.repository
    ]
    assert attempt["nextAllowedAt"] == available_at.isoformat()
    assert attempt["reason"] == "profile_source_rate_limited"
    # Unknown/invalid protocol values remain unknown, never a worker exception.
    assert (
        service._source_retry_after(
            httpx.Response(429, headers={"Retry-After": "not-a-date", "X-RateLimit-Reset": "9" * 100}), clock["now"]
        )
        is None
    )

    clock["now"] = available_at + timedelta(seconds=1)
    resumed = await work(recovery, service.read_json(recovery.target / "progress.json"))
    record = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"][project.repository]
    assert resumed["processed"] + resumed["refreshed"] == 1
    assert record["status"] == "completed" and record["failures"] == 1
    assert calls.count(f"/repos/{project.repository}") == 2
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("suppressed", [False, True])
async def test_today_saved_source_is_not_refetched_for_same_day_stage_continuation(recovery, monkeypatch, suppressed):
    project = add(recovery, "recovery/partial-resume", 852)
    collected = await seed(recovery, project, monkeypatch, partial=True)
    if suppressed:
        for _ in range(2):
            profile_cache_v2.record_failure(
                recovery.target / "profile-cache",
                project.githubRepositoryId,
                collected.profile_cache_identity,
                error_code="profile_model_invalid_output",
                retryable=True,
                source_failure_stage="profile",
            )
    current_board(recovery, project)
    # Keep this optional stage incomplete; no synthetic replacement of the
    # collector, source binding, stored introduction or worker is involved.
    from app.integrations.rardar import serving_profiles

    monkeypatch.setattr(serving_profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))
    first = await work(recovery, {})
    assert first["providerRequests"] == 0
    assert first["failed"] == 0
    material = service.saved_materials(recovery.target)[project.repository]
    assert material["materialState"] == "partial" and material["displayProfile"]["positioningZh"]
    after_check = list(recovery.requests)
    progress = service.read_json(recovery.target / "progress.json")
    second = await work(recovery, progress)
    assert recovery.requests == after_check
    assert second["providerRequests"] == 0
    rotation = service.read_json(recovery.target / "trending-boards" / "material-work.json")
    assert rotation["_attempts"][project.repository]["sourceCheckedAt"]
    assert rotation["_attempts"][project.repository]["metadataDigest"]
    record = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"][project.repository]
    assert record["failures"] == 0 and record["providerRequests"] == 0
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("paid_failure", [False, True])
async def test_funded_partial_keeps_valid_main_fields_without_claiming_full_profile_success(
    recovery, monkeypatch, paid_failure
):
    from app.integrations.rardar import serving_profiles

    project = add(recovery, "recovery/funded-partial", 853)
    await seed(recovery, project, monkeypatch, partial=True)
    current_board(recovery, project)
    original = service.saved_materials(recovery.target)[project.repository]
    directory = recovery.target / "profile-cache" / "introductions" / str(project.githubRepositoryId)
    saved_files = {path.name: path.read_bytes() for path in directory.glob("*.json")}
    virtual_spent = False

    def invalid_capabilities(*_):
        nonlocal virtual_spent
        current = daily_provider_budget._work_slice.get()
        if paid_failure and current is not None and not virtual_spent:
            current.used_requests += 1  # explicit virtual outbound debit, never external IO
            virtual_spent = True
        return [], ["capability_invalid_content"]

    monkeypatch.setattr(serving_profiles, "_valid_capabilities", invalid_capabilities)
    monkeypatch.setattr(
        daily_provider_budget,
        "daily_execution_budget",
        AsyncMock(return_value=(SimpleNamespace(snapshot=lambda: {"remaining": 80}), {})),
    )
    result = await work(recovery, {})
    record = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"][project.repository]
    assert record["status"] == "partial"
    assert record["nextAction"] == ("degrade_with_evidence" if paid_failure else "resume_missing_stage")
    assert record["failures"] == result["failed"] == int(paid_failure)
    assert record["providerRequests"] == result["providerRequests"] == int(paid_failure)
    material = service.saved_materials(recovery.target)[project.repository]
    assert material["materialState"] == "partial" and material["displayProfile"]["positioningZh"]
    assert material["profile"]["generatedAt"] == original["profile"]["generatedAt"]
    for field in ("identitySummaryZh", "positioningZh", "generatedAt"):
        assert material["displayProfile"][field] == original["displayProfile"][field]
    assert {path.name: path.read_bytes() for path in directory.glob("*.json")} == saved_files
    if paid_failure:
        attempts = list((recovery.target / "profile-cache" / "profile-attempts").rglob("*.json"))
        assert len(attempts) == 1
        receipt = profile_cache_v2.ProfileAttemptRecordV1.model_validate_json(attempts[0].read_bytes())
        assert record["errorCode"] == receipt.errorCode
        assert record["nextRetryAt"] == (receipt.nextRetryAt.isoformat() if receipt.nextRetryAt else None)
        before = list(recovery.requests)
        again = await work(recovery, service.read_json(recovery.target / "progress.json"))
        assert again["providerRequests"] == 0 and recovery.requests == before
        record = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"][project.repository]
        assert record["failures"] == 1 and record["providerRequests"] == 1
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["next_day", "metadata"])
async def test_same_day_source_reuse_does_not_skip_new_day_or_known_metadata_change(recovery, monkeypatch, change):
    from app.integrations.rardar import serving_profiles

    project = add(recovery, "recovery/legitimate-source-check", 854)
    await seed(recovery, project, monkeypatch, partial=True)
    current_board(recovery, project)
    monkeypatch.setattr(serving_profiles, "_valid_capabilities", lambda *_: ([], ["capability_invalid_content"]))
    await work(recovery, {})
    before = len(recovery.requests)
    if change == "next_day":
        tomorrow = datetime.now(UTC) + timedelta(days=1)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return tomorrow.astimezone(tz) if tz else tomorrow.replace(tzinfo=None)

        monkeypatch.setattr(service, "datetime", Clock)
    else:
        metadata = {**recovery.entries[project.repository]["metadata"], "description": "合法取得的新版本项目简介"}
        recovery.entries[project.repository]["metadata"] = metadata
        trending_metadata.save(recovery.target, {"repository": project.repository}, metadata)
    result = await work(recovery, service.read_json(recovery.target / "progress.json"))
    assert len(recovery.requests) == before + 3  # metadata, tree and conditional README
    assert result["providerRequests"] == 0
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_history_outside_current_scopes_checks_known_metadata_change(recovery, monkeypatch):
    project = add(recovery, "recovery/complete-history", 855)
    await seed(recovery, project, monkeypatch)
    history(recovery, [project.repository])
    await work(recovery, {})
    assert service.saved_materials(recovery.target)[project.repository]["materialState"] == "complete"
    path = recovery.target / "trending-boards" / "material-work.json"
    rotation = service.read_json(path)
    # A prior successful source check over these real stored source/material
    # inputs, outside both the current Today and the fixed daily review scopes.
    rotation["_successfulChecks"][project.repository] = {
        "checkedAt": datetime.now(UTC).isoformat(),
        "sourceCheckedAt": trending_metadata.read(recovery.target, {"repository": project.repository})["fetchedAt"],
        "metadataDigest": trending_metadata.content_revision(recovery.target, {"repository": project.repository})[
            "metadataDigest"
        ],
        "profileDigests": [],
    }
    service.atomic(path, rotation)
    old_digest = rotation["_successfulChecks"][project.repository]["metadataDigest"]
    assert old_digest
    assert not service.today_candidates(recovery.target)["projects"]
    metadata = {**recovery.entries[project.repository]["metadata"], "description": "已合法取得的资料内容变化"}
    recovery.entries[project.repository]["metadata"] = metadata
    trending_metadata.save(recovery.target, {"repository": project.repository}, metadata)
    before = len(recovery.requests)
    resumed = await work(recovery, service.read_json(recovery.target / "progress.json"))
    assert resumed["visited"] == 1
    assert len(recovery.requests) == before + 3
    assert resumed["providerRequests"] == 0
    rotation = service.read_json(recovery.target / "trending-boards" / "material-work.json")
    assert rotation["_successfulChecks"][project.repository]["metadataDigest"] != old_digest
    recovery.model.assert_not_awaited()


@pytest.mark.asyncio
async def test_corrupt_source_check_time_is_item_local_and_cannot_fund_a_retry(recovery, monkeypatch):
    bad = add(recovery, "recovery/bad-check-time", 856)
    healthy = add(recovery, "recovery/good-check-time", 857)
    for project in (bad, healthy):
        await seed(recovery, project, monkeypatch)
    history(recovery, [bad.repository, healthy.repository])
    await work(recovery, {})
    path = recovery.target / "trending-boards" / "material-work.json"
    rotation = service.read_json(path)
    rotation["_successfulChecks"][bad.repository] = {
        "sourceCheckedAt": "not-an-iso-timestamp",
        "metadataDigest": trending_metadata.content_revision(recovery.target, {"repository": bad.repository})[
            "metadataDigest"
        ],
    }
    service.atomic(path, rotation)
    current_board(recovery, bad)
    before = list(recovery.requests)
    result = await work(recovery, service.read_json(recovery.target / "progress.json"))
    assert result["checked"] == 2 and result["providerRequests"] == 0
    assert recovery.requests == before
    records = service.read_json(recovery.target / "progress.json")["materialWork"]["projects"]
    assert records[bad.repository]["status"] == "invalid"
    assert records[healthy.repository]["status"] == "completed"
    recovery.model.assert_not_awaited()
