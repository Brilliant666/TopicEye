"""Synthetic failures only: no GitHub or Provider requests."""

import ast
import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticCustomError

from app.integrations.rardar import serving_schemas
from app.integrations.rardar.profile_validation_rules import (
    PROFILE_VALIDATION_RULES,
    annotate_profile_validation,
    profile_validation_context,
)
from app.integrations.rardar.serving_profiles import (
    DerivedPositioning,
    EvidenceClaim,
    ProfileGenerationFailure,
    ProfileTranslation,
    ProfileTranslationError,
    _generation_failure_diagnostic,
    _validate_translation,
)
from app.integrations.rardar.serving_schemas import ServingCapability
from app.services import rardar_trending as service
from app.services.rardar_material_diagnostics import material_failure_diagnostic
from tests_rardar_llm.test_material_work_allowance import work  # noqa: F401 -- shared isolated entry fixture


def test_http_metadata_redacts_request_and_response():
    request = httpx.Request(
        "GET",
        "https://user:password@api.github.com/repos/a/b?token=secret",
        headers={"Authorization": "secret", "Cookie": "secret"},
    )
    response = httpx.Response(429, request=request, text="private body")
    error = httpx.HTTPStatusError("secret message", request=request, response=response)
    value = material_failure_diagnostic(error, project={"projectId": "project-a"}, stage="source")
    assert value["httpStatus"] == 429
    assert value["host"] == "api.github.com"
    assert value["endpointCategory"] == "repository_metadata"
    assert value["validationErrorCount"] is None
    rendered = json.dumps(value)
    for private in ("password", "token", "secret", "private body", "/repos/"):
        assert private not in rendered


@pytest.mark.parametrize("error", [httpx.ReadTimeout("secret"), httpx.ConnectError("secret")])
def test_no_response_is_not_an_http_status(error):
    value = material_failure_diagnostic(error, project={}, stage="source")
    assert value["httpStatus"] is None and value["host"] is None
    assert value["errorClass"] == type(error).__name__


def test_unknown_host_is_not_logged():
    request = httpx.Request("GET", "https://private.internal/secret")
    error = httpx.ConnectError("secret", request=request)
    value = material_failure_diagnostic(error, project={}, stage="source")
    assert value["host"] is None and value["endpointCategory"] is None


def test_underlying_generation_reason_survives_outer_readback_error_and_json_roundtrip(tmp_path):
    """A later projector ValueError must not erase the first, structured model failure."""
    from app.services.rardar_llm_control import RardarLLMError

    first = RardarLLMError(
        "rardar_llm_invalid_output",
        classification="schema_invalid",
        validation_stage="structure",
        field_path="$.positioning.positioningZh",
        validation_type="string_type",
    )
    failure = ProfileGenerationFailure(
        "positioning",
        "positioning_schema_invalid",
        False,
        _generation_failure_diagnostic(
            first,
            model_class="ProfileTranslation",
            prompt_version="rardar-assessment-zh-v12",
            input_digest="a" * 64,
        ),
    )
    collected = SimpleNamespace(generation_failures=(failure,), profile=None)
    value = material_failure_diagnostic(
        ValueError("private projector details"),
        project={"projectId": "fixture-project"},
        stage="profile",
        collected=collected,
    )
    path = tmp_path / "correction-receipt.json"
    service.atomic(path, {"diagnostic": value})
    saved = service.read_json(path)["diagnostic"]
    assert saved["errorClass"] == "ValueError"
    assert saved["generationFailureCount"] == 1
    underlying = saved["generationFailures"][0]
    assert underlying["stage"] == "positioning" and underlying["code"] == "positioning_schema_invalid"
    assert underlying["detail"]["fieldPath"] == "$.positioning.positioningZh"
    assert underlying["detail"]["validationType"] == "string_type"
    assert underlying["detail"]["inputDigest"] == "a" * 64
    assert "private projector" not in json.dumps(saved)


def test_fixed_translation_rule_and_dynamic_metadata_are_separated():
    known = _generation_failure_diagnostic(
        ProfileTranslationError("rardar_profile_translation_positioning_incomplete"),
        model_class="ProfileTranslation",
        prompt_version="rardar-assessment-zh-v12",
        input_digest="b" * 64,
    )
    unknown = _generation_failure_diagnostic(
        ProfileTranslationError("Authorization: private token"),
        model_class="ProfileTranslation",
        prompt_version="rardar-assessment-zh-v12",
        input_digest="b" * 64,
    )
    collected = SimpleNamespace(
        generation_failures=(
            ProfileGenerationFailure("positioning", "positioning_schema_invalid", False, known),
            ProfileGenerationFailure("positioning", "positioning_schema_invalid", False, unknown),
        )
    )
    value = material_failure_diagnostic(ValueError("outer"), project={}, stage="profile", collected=collected)
    assert value["generationFailures"][0]["detail"]["ruleCode"] == ("rardar_profile_translation_positioning_incomplete")
    assert value["generationFailures"][1]["detail"]["ruleCode"] is None
    assert "private token" not in json.dumps(value)


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        ("summary", "rardar_profile_translation_invalid_summary"),
        ("duplicate_roles", "rardar_profile_translation_invalid_positioning_roles"),
        ("duplicate_refs", "rardar_profile_translation_invalid_positioning_refs"),
        ("core_value_language", "rardar_profile_translation_invalid_core_value_language"),
        ("forbidden_capability", "rardar_profile_translation_invalid_capability_forbidden"),
    ],
)
def test_translation_rejection_preserves_distinct_fixed_rule_after_outer_failure(tmp_path, change, rule):
    """Synthetic same-shape output, not a replay of NiubiGEO's lost response."""
    source_ref = "readme:section:1"
    summary = EvidenceClaim(text="一个根据域名比较模型描述的工具。", evidenceRefs=[source_ref])
    positioning = DerivedPositioning(
        positioningZh="通过输入域名对比不同模型的产品描述和引用来源。",
        includedEvidenceRefs=[source_ref],
        includedRoles=["identity", "core_mechanism"],
    )
    value = ProfileTranslation(
        summary=summary,
        positioning=positioning,
        capabilities=[],
        productForms=[],
        supportedEnvironments=[],
        useCases=[],
        deliveryForms=[],
    )
    _validate_translation(value, {source_ref})
    if change == "summary":
        value = value.model_copy(update={"summary": summary.model_copy(update={"text": "English only"})})
    elif change == "duplicate_roles":
        value = value.model_copy(
            update={
                "positioning": positioning.model_copy(
                    update={"includedRoles": ["identity", "core_mechanism", "core_mechanism"]}
                )
            }
        )
    elif change == "duplicate_refs":
        value = value.model_copy(
            update={"positioning": positioning.model_copy(update={"includedEvidenceRefs": [source_ref, source_ref]})}
        )
    elif change == "core_value_language":
        value = value.model_copy(update={"coreValue": EvidenceClaim(text="English only", evidenceRefs=[source_ref])})
    else:
        value = value.model_copy(
            update={
                "capabilities": [
                    ServingCapability(
                        title="排名第1名的能力",
                        detail="提供可核验的项目资料。",
                        evidenceRefs=[source_ref],
                    )
                ]
            }
        )
    with pytest.raises(ProfileTranslationError) as rejected:
        _validate_translation(value, {source_ref})
    assert str(rejected.value) == rule
    failure = ProfileGenerationFailure(
        "positioning",
        "positioning_schema_invalid",
        False,
        _generation_failure_diagnostic(
            rejected.value,
            model_class="ProfileTranslation",
            prompt_version="rardar-assessment-zh-v12",
            input_digest="d" * 64,
        ),
    )
    diagnostic = material_failure_diagnostic(
        ValueError("private outer error"),
        project={"projectId": "fixture-project"},
        stage="profile",
        collected=SimpleNamespace(generation_failures=(failure,), profile=None),
    )
    path = tmp_path / f"{change}.json"
    service.atomic(path, {"diagnostic": diagnostic})
    stored = service.read_json(path)["diagnostic"]
    assert stored["generationFailures"][0]["detail"]["ruleCode"] == rule
    assert "private outer error" not in json.dumps(stored)


@pytest.mark.parametrize(
    "path", ["$.Authorization", "$.positioning.secret", "$.summary[0].token=hidden", "https://hidden"]
)
def test_untrusted_generation_field_path_is_not_persisted(path):
    from app.services.rardar_llm_control import RardarLLMError

    error = RardarLLMError(
        "rardar_llm_invalid_output",
        classification="schema_invalid",
        validation_stage="structure",
        field_path=path,
        validation_type="string_type",
    )
    detail = _generation_failure_diagnostic(
        error,
        model_class="ProfileTranslation",
        prompt_version="rardar-assessment-zh-v12",
        input_digest="c" * 64,
    )
    collected = SimpleNamespace(
        generation_failures=(ProfileGenerationFailure("positioning", "positioning_schema_invalid", False, detail),)
    )
    value = material_failure_diagnostic(ValueError("outer"), project={}, stage="profile", collected=collected)
    assert value["generationFailures"][0]["detail"]["fieldPath"] is None
    assert "hidden" not in json.dumps(value)


class SyntheticProfile(BaseModel):
    githubRepositoryId: int
    capabilities: list[int]


def validation_failure():
    try:
        SyntheticProfile.model_validate({"githubRepositoryId": "secret", "capabilities": ["secret"] * 6})
    except ValidationError as error:
        return error
    raise AssertionError("fixture did not fail")


def test_validation_counts_and_fields_without_values_or_messages():
    value = material_failure_diagnostic(validation_failure(), project={}, stage="profile")
    assert value["validationErrorCount"] == 7
    assert len(value["validationErrors"]) == 4
    assert value["validationErrorsOmitted"] == 3
    assert value["validationErrors"][0]["loc"] == ["githubRepositoryId"]
    assert value["validationErrors"][0]["type"] == "int_parsing"
    assert "secret" not in json.dumps(value)
    assert value["profileGenerationId"] is None  # no invented revision


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["http", "validation"])
async def test_real_material_catch_persists_diagnostic_and_keeps_failure_debit(work, monkeypatch, kind):  # noqa: F811
    work.projects[:] = work.projects[:1]
    if kind == "http":
        request = httpx.Request("GET", "https://api.github.com/repos/current/one?secret=hidden")
        error = httpx.HTTPStatusError("hidden", request=request, response=httpx.Response(404, request=request))
    else:
        error = validation_failure()
    monkeypatch.setattr(service, "_collect_project_material", AsyncMock(side_effect=error))
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    record = progress["materialWork"]["projects"]["current/one"]
    saved = service.read_json(work.target / "trending-boards" / "material-work.json")["_attempts"]["current/one"]
    assert result["failed"] == 1 and result["providerRequests"] == 0
    assert record["status"] == "failed" and record["failures"] == 1
    assert saved["diagnostic"] == record["diagnostic"]
    assert saved["errorCode"] == type(error).__name__
    assert saved["diagnostic"]["httpStatus"] == (404 if kind == "http" else None)
    assert "hidden" not in json.dumps(saved)
    await service.historical_work(work.target, progress, lambda: None)
    third = await service.historical_work(work.target, progress, lambda: None)
    assert record["failures"] == 2
    assert third["visited"] == 0 and third["waitReason"] == "material_retry_limit_reached"


def root_failure(message, *, custom=None):
    """Synthetic root failure, not a replay of a production Provider response."""
    error_type = (
        PydanticCustomError(custom, "private response {secret}", {"secret": "hidden"}) if custom else "value_error"
    )
    return ValidationError.from_exception_data(
        "OfficialProjectProfile",
        [{"type": error_type, "loc": (), "input": {"token": "hidden"}, "ctx": {"error": ValueError(message)}}],
    )


def test_all_fixed_serving_validator_reasons_have_reviewed_codes():
    tree = ast.parse(inspect.getsource(serving_schemas))
    messages = {
        node.exc.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "ValueError"
        and node.exc.args
        and isinstance(node.exc.args[0], ast.Constant)
    }
    assert messages <= PROFILE_VALIDATION_RULES.keys()
    assert len(set(PROFILE_VALIDATION_RULES.values())) == len(PROFILE_VALIDATION_RULES)


@pytest.mark.parametrize("message", list(PROFILE_VALIDATION_RULES))
def test_fixed_reason_is_distinguishable_without_changing_root_location_or_type(message):
    value = material_failure_diagnostic(root_failure(message), project={}, stage="profile")
    assert value["modelClass"] == "OfficialProjectProfile"
    issue = value["validationErrors"][0]
    assert issue["loc"] == [] and issue["type"] == "value_error"
    assert issue["ruleCode"] == PROFILE_VALIDATION_RULES[message]
    assert issue["safeExplanation"] == message
    assert "hidden" not in json.dumps(value)


def test_custom_code_survives_whitelist_without_dynamic_message():
    message = "Serving v6 positioning requires a mechanism or primary outcome"
    code = PROFILE_VALIDATION_RULES[message]
    value = material_failure_diagnostic(root_failure("hidden", custom=code), project={}, stage="profile")
    issue = value["validationErrors"][0]
    assert issue["type"] == issue["ruleCode"] == code
    assert issue["safeExplanation"] == message
    assert "hidden" not in json.dumps(value)


@pytest.mark.parametrize("custom", [None, "private_custom_hidden"])
def test_unknown_dynamic_reason_stays_unknown(custom):
    value = material_failure_diagnostic(
        root_failure("Authorization: hidden", custom=custom), project={}, stage="profile"
    )
    issue = value["validationErrors"][0]
    assert issue["ruleCode"] == "unknown" and issue["safeExplanation"] is None
    assert issue["type"] == ("custom_error" if custom else "value_error")
    assert "hidden" not in json.dumps(value)


@pytest.mark.asyncio
async def test_actual_profile_constructor_root_rules_are_distinct(tmp_path):
    from tests_rardar_llm.test_managed_materials import seed

    # A synthetic complete profile from HTTP substitutes; no upstream calls.
    path = await seed(tmp_path)
    payload = json.loads(path.read_bytes())["profile"]
    cases = [
        (
            {"profileSchemaVersion": "rardar-project-profile-v1", "officialSummaryZh": None},
            "legacy profile requires a summary",
        ),
        (
            {"profileSchemaVersion": "rardar-project-profile-v4", "identitySummaryZh": None},
            "profile v4 requires identity and quality state",
        ),
    ]
    codes = []
    for changes, reason in cases:
        with pytest.raises(ValidationError) as caught:
            serving_schemas.OfficialProjectProfile.model_validate_json(json.dumps({**payload, **changes}))
        value = material_failure_diagnostic(caught.value, project={}, stage="profile")
        issue = value["validationErrors"][0]
        assert issue["loc"] == [] and issue["type"] == "value_error"
        assert issue["ruleCode"] == PROFILE_VALIDATION_RULES[reason]
        codes.append(issue["ruleCode"])
    assert len(set(codes)) == 2


@pytest.mark.asyncio
async def test_root_reason_real_catch_save_and_operational_read(work, monkeypatch):  # noqa: F811
    work.projects[:] = work.projects[:1]
    message = "Serving v8 tagline identity projection is inconsistent"
    error = root_failure(message)
    evidence = SimpleNamespace(
        generationId="attempt-new",
        digest="a" * 64,
        readmeBlobSha="b" * 40,
        githubRepositoryId=123,
        evidenceIndex={"private": "not persisted"},
    )
    annotate_profile_validation(error, evidence)
    collect = AsyncMock(side_effect=error)
    monkeypatch.setattr(service, "_collect_project_material", collect)
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    saved = service.read_json(work.target / "trending-boards" / "material-work.json")["_attempts"]["current/one"]
    assert saved["status"] == "failed" and saved["errorCode"] == "ValidationError"
    assert saved["diagnostic"]["modelClass"] == "OfficialProjectProfile"
    assert saved["diagnostic"]["attemptEvidence"] == {
        "generationId": "attempt-new",
        "evidenceDigest": "a" * 64,
        "readmeBlobSha": "b" * 40,
        "githubRepositoryId": 123,
    }
    assert "not persisted" not in json.dumps(saved)
    assert saved["diagnostic"]["validationErrors"][0]["ruleCode"] == PROFILE_VALIDATION_RULES[message]
    assert saved["diagnostic"] == progress["materialWork"]["projects"]["current/one"]["diagnostic"]
    assert result["providerRequests"] == 0 and collect.await_count == 1
    # Existing v1 records remain readable without inventing a missing cause.
    old = {"schemaVersion": 1, "validationErrors": [{"loc": [], "type": "value_error"}]}
    path = work.target / "old-diagnostic.json"
    service.atomic(path, old)
    assert service.read_json(path) == old


def test_context_preserves_original_exception_and_refuses_unbounded_metadata():
    error = root_failure("legacy profile requires a summary")
    evidence = SimpleNamespace(
        generationId="https://secret.invalid/?token=hidden",
        digest="secret",
        readmeBlobSha="hidden",
        githubRepositoryId=True,
    )
    with pytest.raises(ValidationError) as caught, profile_validation_context(evidence):
        raise error
    assert caught.value is error
    value = material_failure_diagnostic(error, project={}, stage="profile")
    assert value["attemptEvidence"] is None
    assert "hidden" not in json.dumps(value)
    # Persistence rechecks even an attribute not produced by our constructor wrapper.
    error.rardar_attempt_evidence = {"input": "hidden", "generationId": "invalid/path"}
    assert material_failure_diagnostic(error, project={}, stage="profile")["attemptEvidence"] is None


@pytest.mark.asyncio
async def test_diagnostic_failure_does_not_replace_business_failure_or_repeat(work, monkeypatch):  # noqa: F811
    from app.services import rardar_material_diagnostics as diagnostics

    work.projects[:] = work.projects[:1]
    collect = AsyncMock(side_effect=root_failure("legacy profile requires a summary"))
    monkeypatch.setattr(service, "_collect_project_material", collect)

    def broken(*args, **kwargs):
        raise RuntimeError("secret diagnostic failure")

    monkeypatch.setattr(diagnostics, "_material_failure_diagnostic", broken)
    progress = {}
    result = await service.historical_work(work.target, progress, lambda: None)
    saved = service.read_json(work.target / "trending-boards" / "material-work.json")["_attempts"]["current/one"]
    assert saved["errorCode"] == "ValidationError"
    assert saved["diagnostic"]["diagnosticStatus"] == "unavailable"
    assert progress["materialWork"]["projects"]["current/one"]["failures"] == 1
    assert result["providerRequests"] == 0 and collect.await_count == 1
    assert "secret" not in json.dumps(saved)
