from types import SimpleNamespace

import pytest

from app.integrations.rardar.selection import _prompt_json, _Usage
from app.integrations.rardar.selection_schemas import SelectionGateResult
from app.integrations.rardar.serving_profiles import ProfileTranslationError, _official_positioning_translation
from app.services.llm import run_failure_guard as module
from app.services.llm.provider_budget import ProviderBudgetError
from app.services.rardar_llm_control import RardarLLMError, RardarLLMResult, RardarLLMScene, ReasoningEffort
from tests_rardar_selection.test_selection import _metadata


def test_execution_policy_versions_shortcut_without_changing_result_contracts(tmp_path, monkeypatch):
    from app.integrations.rardar import selection
    from tests_rardar_selection.test_selection import _source

    target, source = _source(tmp_path)
    original_canonical = selection._canonical_bytes
    contracts = selection._contract_versions()
    current = selection.selection_input_digest(
        source, cache_root=target / "cache", model_route_identity="a" * 64, recall_limit=48
    )

    def previous_canonical(value):
        if isinstance(value, dict) and "executionFailurePolicy" in value:
            value = {key: item for key, item in value.items() if key != "executionFailurePolicy"}
        return original_canonical(value)

    monkeypatch.setattr(selection, "_canonical_bytes", previous_canonical)
    previous = selection.selection_input_digest(
        source, cache_root=target / "cache", model_route_identity="a" * 64, recall_limit=48
    )
    assert previous != current
    assert selection._contract_versions() == contracts


@pytest.mark.asyncio
async def test_phase_latches_persist_across_projects_and_batches():
    @module.selection_phase("profiles")
    async def broken_profile():
        module.before_attempt()
        module.failed("schema_invalid")

    @module.selection_phase("value")
    async def value(fail=False):
        module.before_attempt()
        if fail:
            module.failed("schema_invalid")

    with module.run_failure_guard(isolate_stages=True) as guard:
        await broken_profile()
        await broken_profile()
        assert guard.stopped
        with pytest.raises(ProviderBudgetError):
            await broken_profile()
        await value()
        await value(fail=True)
        await value(fail=True)
        with pytest.raises(ProviderBudgetError):
            await value()
        assert guard.stages["profiles"].failures == 2
        assert guard.stages["value"].failures == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["structure", "timeout"])
async def test_selection_third_attempt_is_not_dispatched(failure):
    calls = 0

    async def caller(**kwargs):
        nonlocal calls
        calls += 1
        if failure == "timeout":
            raise RardarLLMError("rardar_llm_timeout", classification="timeout")
        return RardarLLMResult("{}", _metadata(kwargs["scene"]))

    with module.run_failure_guard() as guard:
        outcomes = []
        for _ in range(3):
            outcomes.append(
                await _prompt_json(
                    scene=RardarLLMScene.WORTH_SEEING_GATE,
                    effort=ReasoningEffort.HIGH,
                    payload={"repository": "example/project"},
                    response_model=SelectionGateResult,
                    usage=_Usage(),
                    caller=caller,
                )
            )
        assert guard.stopped
        assert calls == 2
        assert outcomes[-1][1] == 0
        assert outcomes[-1][2] == "provider_operation_consecutive_failures"


@pytest.mark.asyncio
async def test_profile_retry_latches_and_next_project_does_not_dispatch(tmp_path):
    calls = 0

    async def translator(_payload):
        nonlocal calls
        calls += 1
        raise ProfileTranslationError("invalid structured output")

    with module.run_failure_guard() as guard:
        for identifier in (1, 2, 3):
            await _official_positioning_translation(
                project=SimpleNamespace(githubRepositoryId=identifier, repository=f"example/project-{identifier}"),
                evidence=SimpleNamespace(readmeBlobSha="a" * 40, digest="b" * 64),
                source_positioning="A documented development tool",
                cache_root=tmp_path,
                translator=translator,
            )
        assert calls == 2
        assert guard.stopped


def test_guard_success_cache_and_transport_double_reporting():
    with module.run_failure_guard() as guard:
        before = module.before_attempt()
        module.failed("timeout")  # SDK result
        module.failed("timeout", since=before)  # Same result mapped by caller
        assert guard.consecutive == 1
        module.succeeded(cache_hit=True)
        assert guard.consecutive == 1
        module.succeeded()
        assert guard.consecutive == 0
        before = module.before_attempt()
        module.response_received(cache_hit=True)
        module.failed("schema_invalid", since=before)
        assert guard.consecutive == 0
        module.before_attempt()
        module.failed("schema_invalid")
        module.failed("invalid_json")
        assert guard.stopped
        with pytest.raises(ProviderBudgetError, match="consecutive"):
            module.before_attempt()
    # No effect on another operation or existing callers without opt-in.
    module.before_attempt()
    with module.run_failure_guard() as fresh:
        assert not fresh.stopped


@pytest.mark.parametrize(
    "code",
    ["unknown_field", "missing_required_field", "invalid_enum", "wrong_field_type", "missing_content"],
)
def test_visible_format_errors_are_not_misclassified_as_transport(code):
    with module.run_failure_guard() as guard:
        module.failed(code)
        assert guard.failure_code == "structure"
    with module.run_failure_guard() as guard:
        module.failed("profile_rejected")
        assert guard.failure_code == "validation"
