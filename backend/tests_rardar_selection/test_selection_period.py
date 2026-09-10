from __future__ import annotations

import pytest

from app.integrations.rardar.selection import build_candidate_universe, build_selection, recall_candidates
from app.integrations.rardar.selection_period import build_period_serving
from app.integrations.rardar.selection_serving import (
    SelectionServingLoader,
    build_selection_serving,
    install_selection_serving,
)
from tests_rardar_selection.test_selection import ModelDouble, _client, _source


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_valid_negative_singleton_can_publish_empty_but_incomplete_cannot_clear_current(tmp_path, failed):
    import json

    from app.services.rardar_llm_control import RardarLLMResult, RardarLLMScene
    from tests_rardar_selection.test_selection import _metadata

    class NegativeOrInvalid(ModelDouble):
        async def __call__(self, **kwargs):
            payload = json.loads(kwargs["messages"][1]["content"])
            if (
                failed
                and kwargs["scene"] == RardarLLMScene.WORTH_SEEING_GATE
                and not str(payload.get("repository", "")).startswith("negative-control/")
            ):
                return RardarLLMResult("invalid-json", _metadata(kwargs["scene"]))
            return await super().__call__(**kwargs)

    target, source = _source(tmp_path)
    candidate = recall_candidates(build_candidate_universe(source)[0], 30, batch_id="negative-period")[0]
    async with _client() as client:
        healthy = await build_selection(
            source=source,
            cache_root=target / "old-cache",
            caller=ModelDouble(copy_why_now=None),
            github_client=client,
            recall_limit=30,
            recall_batch_id="negative-period",
            process_candidate_ids=(candidate.githubRepositoryId,),
            model_route_identity="c" * 64,
        )
        install_selection_serving(target, build_selection_serving(healthy))
        before = (target / "discover-worth-seeing/current.json").read_bytes()
        evaluated = await build_selection(
            source=source,
            cache_root=target / "new-cache",
            caller=NegativeOrInvalid(regular_value="weak"),
            github_client=client,
            recall_limit=30,
            recall_batch_id="negative-period",
            process_candidate_ids=(candidate.githubRepositoryId,),
            model_route_identity="c" * 64,
        )
    assert not evaluated.artifact.negativeControlFailures
    child = install_selection_serving(target, build_selection_serving(evaluated), activate=False)
    period = build_period_serving(target, [child.selection_generation_id])
    assert period.state == ("degraded" if failed else "empty")
    installed = install_selection_serving(target, period)
    snapshot, _ = SelectionServingLoader(target).load_latest_attempt_with_etag()
    assert snapshot.processedCount == 1
    assert snapshot.unprocessedCount > 0
    assert "未处理不代表淘汰" in snapshot.coverageLabelZh
    if failed:
        assert not installed.current_changed
        assert (target / "discover-worth-seeing/current.json").read_bytes() == before
    else:
        assert installed.current_changed
        assert SelectionServingLoader(target).load_with_etag()[0].status == "empty"


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size", [1, 6])
async def test_period_collects_batches_without_early_activation_and_is_order_independent(tmp_path, chunk_size):
    target, source = _source(tmp_path)
    recalled = recall_candidates(build_candidate_universe(source)[0], 30, batch_id="period-test")
    generations = []
    async with _client() as client:
        for start in range(0, len(recalled), chunk_size):
            built = await build_selection(
                source=source,
                cache_root=target / "selection-profile-cache",
                caller=ModelDouble(copy_why_now=None),
                github_client=client,
                recall_limit=30,
                recall_batch_id="period-test",
                process_candidate_ids=tuple(x.githubRepositoryId for x in recalled[start : start + chunk_size]),
                model_route_identity="c" * 64,
            )
            installed = install_selection_serving(target, build_selection_serving(built), activate=False)
            generations.append(installed.selection_generation_id)
            assert not installed.current_changed
            assert not (target / "discover-worth-seeing/current.json").exists()
            assert not (target / "discover-worth-seeing/latest-attempt.json").exists()
    if chunk_size != 1:
        from app.integrations.rardar.selection_serving import SelectionServingError

        # Retained legacy batches still validate, but pre-packed batches cannot
        # silently become inputs to partition-independent period packing.
        assert SelectionServingLoader(target).validate_generation(generations[0]).processedCount == 6
        with pytest.raises(SelectionServingError, match="one project"):
            build_period_serving(target, generations)
        return
    period = build_period_serving(target, generations)
    reverse = build_period_serving(target, generations[::-1])
    assert period.files == reverse.files
    for grouping in (2, 3):
        work_slices = [generations[start : start + grouping] for start in range(0, len(generations), grouping)]
        reordered = [key for group in reversed(work_slices) for key in group]
        assert build_period_serving(target, reordered).files == period.files
    import json

    from app.integrations.rardar.selection_period import load_period_view
    from app.integrations.rardar.selection_serving import SelectionServingError

    broken_envelope = json.loads(period.files["raw/selection.json"])
    broken_envelope["payloadDigest"] = "0" * 64
    with pytest.raises(SelectionServingError, match="digest"):
        load_period_view(SelectionServingLoader(target), json.dumps(broken_envelope).encode())
    result = install_selection_serving(target, period)
    assert result.current_changed
    loader = SelectionServingLoader(target)
    artifact = loader.validate_generation()
    assert artifact.processedCount == len(recalled)
    assert artifact.executionMode == "period"
    snapshot, _ = loader.load_with_etag()
    assert snapshot.processedCount == len(recalled)
    assert snapshot.unprocessedCount == snapshot.candidateCount - len(recalled)
    assert 0 < snapshot.publishedCount <= 6
    for card in snapshot.items:
        detail, _ = loader.load_project_with_etag(card.githubRepositoryId, period.selection_generation_id)
        assert detail.card == card
        assert detail.canonicalProfile
    repeat = install_selection_serving(target, period)
    assert not repeat.changed
    from app.services.rardar_daily_operations import _cached_profile_candidates

    ready = _cached_profile_candidates(target, recalled, "c" * 64)
    assert ready
    identifier = next(iter(ready))
    changed = [
        item.model_copy(update={"primaryLanguage": "changed-language"})
        if item.githubRepositoryId == identifier
        else item
        for item in recalled
    ]
    assert identifier not in _cached_profile_candidates(target, changed, "c" * 64)
    # A late smaller slice cannot silently re-publish less current coverage.
    from types import SimpleNamespace
    from unittest.mock import patch

    from app.integrations.rardar import selection_source, serving
    from app.integrations.rardar.selection_period import publish_period
    from app.integrations.rardar.selection_serving import SelectionServingError

    before = (target / "discover-worth-seeing/current.json").read_bytes()
    with (
        patch.object(selection_source.SelectionSourceAdapter, "load", return_value=source),
        patch.object(
            serving.ServingProjectionLoader,
            "load_today_with_etag",
            return_value=(SimpleNamespace(generationId=source.today_generation_id), "etag"),
        ),
    ):
        late_subset = publish_period(
            target,
            generations[:1],
            expected_source_id=source.source_observation_set_id,
            expected_today_generation=source.today_generation_id,
        )
        assert not late_subset.current_changed
        if chunk_size == 1:
            async with _client() as client:
                renewed = await build_selection(
                    source=source,
                    cache_root=target / "selection-profile-cache",
                    caller=ModelDouble(copy_why_now=None),
                    github_client=client,
                    recall_limit=30,
                    recall_batch_id="period-test",
                    process_candidate_ids=(recalled[0].githubRepositoryId,),
                    model_route_identity="c" * 64,
                )
            newer = install_selection_serving(target, build_selection_serving(renewed), activate=False)
            published = publish_period(
                target,
                [newer.selection_generation_id],
                expected_source_id=source.source_observation_set_id,
                expected_today_generation=source.today_generation_id,
            )
            assert published.current_changed
            before = (target / "discover-worth-seeing/current.json").read_bytes()
            # Same IDs do not authorize a late old child to undo the newer result.
            late_old = publish_period(
                target,
                generations,
                expected_source_id=source.source_observation_set_id,
                expected_today_generation=source.today_generation_id,
            )
            assert not late_old.current_changed
    assert (target / "discover-worth-seeing/current.json").read_bytes() == before
    # Published parent still depends on exact retained child bytes.
    raw = target / "discover-worth-seeing/generations" / generations[-1] / "raw/selection.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(SelectionServingError):
        loader.load_with_etag()
    assert (target / "discover-worth-seeing/current.json").read_bytes() == before
