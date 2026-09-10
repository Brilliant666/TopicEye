from dataclasses import replace

import pytest

from app.integrations.rardar import selection
from app.integrations.rardar.selection_serving import build_selection_serving
from app.integrations.rardar.serving_profiles import ProfileGenerationFailure
from tests_rardar_selection.test_selection import ModelDouble, _client, _source


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", [None, "identity", "digest", "missing_readme", "unsafe_path", "valid_reject"])
async def test_actual_build_can_assess_raw_material_without_display_profile(tmp_path, monkeypatch, damage):
    target, source = _source(tmp_path)
    candidates = selection.recall_candidates(selection.build_candidate_universe(source)[0], 30, batch_id="raw")
    identifier = candidates[0].githubRepositoryId
    original = selection.build_official_profiles

    async def incomplete(*args, **kwargs):
        result = await original(*args, **kwargs)
        collected = result.profiles[identifier]
        evidence = collected.evidence
        if damage == "identity":
            evidence = evidence.model_copy(update={"githubRepositoryId": identifier + 1000})
        elif damage == "digest":
            evidence = evidence.model_copy(update={"digest": "0" * 64})
        elif damage in {"missing_readme", "unsafe_path"}:
            data = evidence.model_dump(mode="json", exclude={"digest"})
            if damage == "missing_readme":
                data.update(readmePath=None, readmeBlobSha=None, originalExcerpts=[])
            else:
                data["readmePath"] = "../README.md"
            data["digest"] = selection._sha(selection._canonical_bytes(data))
            evidence = evidence.model_validate(data)
        result.profiles[identifier] = replace(
            collected,
            evidence=evidence,
            profile=collected.profile.model_copy(
                update={
                    "identitySummaryZh": "UNVALIDATED_GENERATED_CLAIM",
                    "positioningZh": None,
                    "capabilities": [],
                    "evidenceDigest": evidence.digest,
                }
            ),
            generation_failures=(ProfileGenerationFailure("positioning", "schema_invalid", False),),
            profile_failure_code="profile_model_invalid_output",
            profile_failure_retryable=True,
            profile_cache_state="unavailable",
        )
        return result

    monkeypatch.setattr(selection, "build_official_profiles", incomplete)
    double = ModelDouble(copy_why_now=None, regular_value="weak" if damage == "valid_reject" else "strong")
    async with _client() as client:
        built = await selection.build_selection(
            source=source,
            cache_root=target / "cache",
            caller=double,
            github_client=client,
            recall_limit=30,
            recall_batch_id="raw",
            process_candidate_ids=(identifier,),
            model_route_identity="c" * 64,
        )
    assessment = built.artifact.assessments[0]
    if damage in {"identity", "digest", "missing_readme", "unsafe_path"}:
        assert assessment.gate is None
        assert assessment.failureCode in {
            "profile_evidence_mismatch",
            "profile_evidence_incomplete",
            "profile_path_unsafe",
        }
        assert built.artifact.publishedCount == 0
        return
    assert assessment.gate is not None
    assert all(item.sourceType != "profile" for item in assessment.valueEvidence)
    assert any(item.sourceType == "readme" for item in assessment.valueEvidence)
    assert built.artifact.profileReadyCount == 0
    assert built.artifact.profileRetryableFailureCount == 1
    assert built.artifact.profileFailureSummary == {"profile_model_invalid_output": 1}
    assert built.artifact.assessmentCoverage == 1
    assert built.artifact.publishedCount == (0 if damage == "valid_reject" else 1)
    assert built.artifact.state == ("empty" if damage == "valid_reject" else "ready")
    serving = build_selection_serving(built)
    assert "UNVALIDATED_GENERATED_CLAIM" not in str(serving)
    assert "UNVALIDATED_GENERATED_CLAIM" not in str(double.calls)
