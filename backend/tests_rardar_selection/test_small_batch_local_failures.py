from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.rardar.selection import (
    SelectionBuildError,
    build_candidate_universe,
    build_selection,
    recall_candidates,
)
from app.integrations.rardar.selection_serving import build_selection_serving, install_selection_serving
from app.services.rardar_llm_control import RardarLLMResult, RardarLLMScene
from tests_rardar_selection.test_selection import (
    ModelDouble,
    NegativeControlDouble,
    _client,
    _github_transport,
    _metadata,
    _source,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2, 5])
async def test_actual_build_accepts_available_small_batch_without_padding(tmp_path, count):
    target, source = _source(tmp_path)
    recalled = recall_candidates(build_candidate_universe(source)[0], 30, batch_id="available")
    ids = tuple(item.githubRepositoryId for item in recalled[:count])
    async with _client() as client:
        built = await build_selection(
            source=source,
            cache_root=target / "cache",
            caller=ModelDouble(copy_why_now=None),
            github_client=client,
            recall_limit=30,
            recall_batch_id="available",
            process_candidate_ids=ids,
            model_route_identity="c" * 64,
        )
    assert built.artifact.processedCandidateIds == list(ids)
    assert built.artifact.processedCount == count
    assert built.artifact.currentEligible
    install_selection_serving(target, build_selection_serving(built))


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["value", "copy"])
async def test_local_invalid_model_output_is_not_published_or_replaced(tmp_path, stage):
    target, source = _source(tmp_path)
    recalled = recall_candidates(build_candidate_universe(source)[0], 30, batch_id="model-failures")[:6]
    failed = {item.repository for item in recalled[:2]}

    class PartialDouble(ModelDouble):
        async def __call__(self, **kwargs):
            payload = json.loads(kwargs["messages"][1]["content"])
            is_stage = (
                (kwargs["scene"] == RardarLLMScene.WORTH_SEEING_GATE)
                if stage == "value"
                else (kwargs["scene"] == RardarLLMScene.WORTH_SEEING_COPY)
            )
            if payload.get("repository") in failed and is_stage:
                self.calls.append((kwargs["scene"], kwargs["messages"]))
                return RardarLLMResult("{}", _metadata(kwargs["scene"]))
            return await super().__call__(**kwargs)

    async with _client() as client:
        built = await build_selection(
            source=source,
            cache_root=target / "cache",
            caller=PartialDouble(copy_why_now=None),
            github_client=client,
            recall_limit=30,
            recall_batch_id="model-failures",
            process_candidate_ids=tuple(item.githubRepositoryId for item in recalled),
            model_route_identity="c" * 64,
        )
    assert built.artifact.currentEligible
    assert built.artifact.publishedCount > 0
    assert built.artifact.processedCandidateIds == [item.githubRepositoryId for item in recalled]
    assert all(item.publicationDisposition != "publish" for item in built.artifact.assessments[:2])
    assert all(item.failureCode for item in built.artifact.assessments[:2])
    install_selection_serving(target, build_selection_serving(built))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_count", [2, 5, 6])
async def test_two_missing_profiles_do_not_block_safe_results(tmp_path, failure_count):
    target, source = _source(tmp_path)
    recalled = recall_candidates(build_candidate_universe(source)[0], 30, batch_id="local-failures")[:6]
    failed = {item.repository for item in recalled[:failure_count]}

    def transport(request):
        if any(request.url.path.startswith(f"/repos/{repo}/") for repo in failed):
            return httpx.Response(404, json={})
        return _github_transport(request)

    async with httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(transport)) as client:
        built = await build_selection(
            source=source,
            cache_root=target / "cache",
            caller=ModelDouble(copy_why_now=None),
            github_client=client,
            recall_limit=30,
            recall_batch_id="local-failures",
            process_candidate_ids=tuple(item.githubRepositoryId for item in recalled),
            model_route_identity="c" * 64,
        )
    assert (
        built.artifact.profilePermanentUnavailableCount + built.artifact.profileRetryableFailureCount == failure_count
    )
    assert built.artifact.unresolvedCount >= failure_count
    assert built.artifact.currentEligible is (failure_count < 6)
    assert (built.artifact.publishedCount > 0) is (failure_count < 6)
    assert all(item.publicationDisposition != "publish" for item in built.artifact.assessments[:failure_count])
    install_selection_serving(target, build_selection_serving(built))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["invalid_structure", "invalid_evidence", "provider_failure", "false_positive"])
async def test_small_batch_still_requires_valid_negative_controls(tmp_path, mode):
    target, source = _source(tmp_path)
    recalled = recall_candidates(build_candidate_universe(source)[0], 30, batch_id="controls")[:2]
    async with _client() as client:
        with pytest.raises(SelectionBuildError, match="Negative"):
            await build_selection(
                source=source,
                cache_root=target / "cache",
                caller=NegativeControlDouble(mode),
                github_client=client,
                recall_limit=30,
                recall_batch_id="controls",
                process_candidate_ids=tuple(item.githubRepositoryId for item in recalled),
                model_route_identity="c" * 64,
            )
