"""Find planning, comparison and provider retries share one existing ledger."""

import pytest

from app.services.llm.provider_budget import ProviderBudgetError, ProviderBudgetLedger, execution_budget


def test_find_retries_and_reopened_ledger_cannot_replenish_budget(tmp_path, monkeypatch):
    ledger = ProviderBudgetLedger.initialize(
        tmp_path / "find" / "provider-budget.json", "find-acceptance",
        task_id="RARDAR-FIND-PROJECT-REQUIREMENT-FIRST-01", limit=16,
    )
    for name, value in {
        "RARDAR_LLM_TASK_ID": ledger.task_id,
        "RARDAR_LLM_RUN_ID": ledger.run_id,
        "RARDAR_LLM_BUDGET_PATH": str(ledger.path),
        "RARDAR_LLM_BUDGET_LIMIT": str(ledger.limit),
    }.items():
        monkeypatch.setenv(name, value)
    for attempt in range(16):
        reopened, stage = execution_budget("rardar_find_project_comparison")
        assert stage == "find_project"
        if attempt == 0:
            with pytest.raises(TimeoutError), reopened.execution(stage):
                raise TimeoutError("mock failure still consumes one request")
        else:
            with reopened.execution(stage):
                pass
    with (
        pytest.raises(ProviderBudgetError, match="exhausted"),
        execution_budget("rardar_find_project_comparison")[0].execution("find_project"),
    ):
        pytest.fail("exhausted budget dispatched")
    assert ledger.snapshot()["attempted"] == 16
    assert ledger.snapshot()["failed"] == 1
    assert ledger.snapshot()["remaining"] == 0


def test_find_does_not_use_historical_shadow_budget(tmp_path, monkeypatch):
    ledger = ProviderBudgetLedger.initialize(tmp_path / "shadow" / "provider-budget.json", "shadow")
    for name, value in {
        "RARDAR_LLM_TASK_ID": ledger.task_id,
        "RARDAR_LLM_RUN_ID": ledger.run_id,
        "RARDAR_LLM_BUDGET_PATH": str(ledger.path),
        "RARDAR_LLM_BUDGET_LIMIT": str(ledger.limit),
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ProviderBudgetError, match="scene_forbidden"):
        execution_budget("rardar_find_project_comparison")
    assert ledger.snapshot()["reserved"] == 0
