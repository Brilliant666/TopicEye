"""The v8 contract separates optional material from immutable ranking facts."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.integrations.rardar.serving_completeness import audit_candidate_publication
from app.integrations.rardar.serving_schemas import OfficialProjectProfile, ServingTodaySnapshot
from tests_rardar_adapter.test_serving import _build, _complete_top20_candidate, _root


def _candidate(tmp_path: Path) -> ServingTodaySnapshot:
    today = _complete_top20_candidate(_build(_root(tmp_path)), count=20)
    projects = []
    for project in today.exactRanked:
        projects.append(
            project.model_copy(
                update={
                    "materialState": "complete",
                    "summarySource": "chinese_profile",
                    "originalDescription": None,
                    "sourceLabel": "Rardar 整理",
                }
            )
        )
    return today.model_copy(update={"schemaVersion": 8, "exactRanked": projects})


def _without_material(project):
    return project.model_copy(
        update={
            "officialSummaryZh": None,
            "identitySummaryZh": None,
            "officialTaglineZh": None,
            "officialTaglineEvidenceRefs": [],
            "officialPositioningZh": None,
            "officialPositioningEvidenceRefs": [],
            "positioningZh": None,
            "positioningSourceMode": "insufficient",
            "positioningEvidenceRefs": [],
            "positioningIncludedRoles": [],
            "positioningExcludedClauses": [],
            "capabilities": [],
            "capabilityBulletsZh": [],
            "keyDifferentiators": [],
            "coreValueZh": None,
            "coreValueEvidenceRefs": [],
            "rardarAssessmentZh": None,
            "rardarAssessmentEvidenceRefs": [],
            "rardarDifferentiators": [],
            "officialHighlights": [],
            "materialState": "unavailable",
            "summarySource": "unavailable",
        }
    )


@pytest.mark.parametrize("missing", [1, 9, 20])
def test_v8_missing_material_does_not_change_or_block_twenty_facts(tmp_path: Path, missing: int) -> None:
    today = _candidate(tmp_path)
    original = [(p.rank, p.githubRepositoryId, p.totalStars, p.observedStarDelta) for p in today.exactRanked]
    projects = [_without_material(p) if index < missing else p for index, p in enumerate(today.exactRanked)]
    candidate = today.model_copy(
        update={
            "exactRanked": projects,
            "profileSummary": today.profileSummary.model_copy(update={"chineseSummaries": 20 - missing}),
        }
    )
    checked = ServingTodaySnapshot.model_validate_json(candidate.model_dump_json())
    audit = audit_candidate_publication(checked, None, candidate_serving_id="candidate-test")
    assert audit["activationAllowed"] is True
    assert audit["publicationPolicy"] == "fact_first"
    assert audit["identityCompleteCount"] == 20 - missing
    assert original == [(p.rank, p.githubRepositoryId, p.totalStars, p.observedStarDelta) for p in checked.exactRanked]


def test_v8_missing_member_still_blocks_fact_publication(tmp_path: Path) -> None:
    today = _candidate(tmp_path)
    short = today.model_copy(update={"exactRanked": today.exactRanked[:19]})
    assert not audit_candidate_publication(short, None, candidate_serving_id="candidate-test")["activationAllowed"]


def test_v7_still_rejects_null_summary(tmp_path: Path) -> None:
    today = _candidate(tmp_path)
    candidate = today.model_copy(update={"schemaVersion": 7, "exactRanked": [_without_material(today.exactRanked[0])]})
    with pytest.raises(ValidationError, match="legacy Serving requires a summary"):
        ServingTodaySnapshot.model_validate_json(candidate.model_dump_json())


def test_v8_does_not_accept_invented_material_completion_or_chinese_label(tmp_path: Path) -> None:
    today = _candidate(tmp_path)
    absent = _without_material(today.exactRanked[0])
    for update in ({"materialState": "complete"}, {"summarySource": "chinese_profile"}):
        candidate = today.model_copy(update={"exactRanked": [absent.model_copy(update=update)]})
        with pytest.raises(ValidationError):
            ServingTodaySnapshot.model_validate_json(candidate.model_dump_json())


def test_v8_present_bad_positioning_remains_rejected(tmp_path: Path) -> None:
    today = _candidate(tmp_path)
    bad = today.exactRanked[0].model_copy(update={"positioningEvidenceRefs": []})
    candidate = today.model_copy(update={"exactRanked": [bad, *today.exactRanked[1:]]})
    with pytest.raises(ValidationError, match="positioning"):
        ServingTodaySnapshot.model_validate_json(candidate.model_dump_json())
    assert not audit_candidate_publication(candidate, None, candidate_serving_id="candidate-test")["activationAllowed"]


def test_v8_snapshot_profile_nullable_does_not_relax_collector_v7(tmp_path: Path) -> None:
    import json

    built = _build(_root(tmp_path))
    record = json.loads(next(value for path, value in built.files.items() if path.startswith("projects/")))
    profile = record["profile"]
    profile["profileSchemaVersion"] = "rardar-project-profile-v7"
    profile["officialSummaryZh"] = None
    with pytest.raises(ValidationError, match="legacy profile requires a summary"):
        OfficialProjectProfile.model_validate_json(json.dumps(profile))


def _collected(project, *, failures=(), refs=()):
    return SimpleNamespace(
        profile=SimpleNamespace(capabilities=project.capabilities, claimEvidenceRefs={}),
        evidence=SimpleNamespace(evidenceIndex=dict.fromkeys(refs, "saved evidence")),
        generation_failures=failures,
        deterministic_fallback_used=False,
        last_known_good_available=False,
        last_known_good_reused=False,
        current_evidence_fingerprint=None,
        last_known_good_fingerprint=None,
    )


def test_v8_unresolved_generation_failure_is_diagnostic_not_fact_gate(tmp_path: Path) -> None:
    today = _candidate(tmp_path)
    projects = [_without_material(project) for project in today.exactRanked]
    today = today.model_copy(update={"exactRanked": projects})
    failure = SimpleNamespace(stage="translation", code="timeout", resolved=False)
    profiles = SimpleNamespace(
        profiles={project.githubRepositoryId: _collected(project, failures=[failure]) for project in projects}
    )
    result = audit_candidate_publication(today, profiles, candidate_serving_id="candidate-test")
    assert result["unresolvedFailureCount"] == 20
    assert result["activationAllowed"] is True


def test_v8_present_reference_outside_saved_evidence_still_blocks(tmp_path: Path) -> None:
    today = _candidate(tmp_path)
    profiles = SimpleNamespace(
        profiles={
            project.githubRepositoryId: _collected(project, refs=["other-evidence"]) for project in today.exactRanked
        }
    )
    result = audit_candidate_publication(today, profiles, candidate_serving_id="candidate-test")
    assert result["missingCapabilityEvidenceCount"] == 20
    assert result["activationAllowed"] is False
