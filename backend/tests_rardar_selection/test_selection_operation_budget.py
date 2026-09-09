from __future__ import annotations

import asyncio
import os

import pytest

from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    budget_stage,
    execution_budget,
    selection_execution_budget,
)


def make_ledger(path, run):
    return ProviderBudgetLedger.initialize(
        path / run / "provider-budget.json", run, task_id="discover-operation", limit=2
    )


@pytest.mark.asyncio
async def test_selection_context_is_task_local_and_preserves_environment(tmp_path):
    first, second = make_ledger(tmp_path, "first"), make_ledger(tmp_path, "second")
    before = dict(os.environ)

    async def run(ledger):
        with selection_execution_budget(ledger):
            await asyncio.sleep(0)
            for scene, stage in (
                ("rardar_project_profile", "project_profile"),
                ("rardar_worth_seeing_gate", "scope_value"),
                ("rardar_worth_seeing_copy", "user_copy"),
            ):
                assert execution_budget(scene) == (ledger, stage)
            with budget_stage("negative_control"):
                assert execution_budget("rardar_worth_seeing_gate") == (ledger, "negative_control")
            with pytest.raises(ProviderBudgetError, match="scene_forbidden"):
                execution_budget("rardar_find_project_comparison")

    await asyncio.gather(run(first), run(second))
    assert dict(os.environ) == before
    assert first.snapshot()["attempted"] == second.snapshot()["attempted"] == 0


def test_all_selection_stages_share_cap_and_resume_without_reset(tmp_path):
    ledger = make_ledger(tmp_path, "run")
    with selection_execution_budget(ledger):
        for scene in ("rardar_project_profile", "rardar_worth_seeing_gate"):
            bound, stage = execution_budget(scene)
            with bound.execution(stage):
                pass
    resumed = ProviderBudgetLedger(ledger.path, ledger.run_id, task_id=ledger.task_id, limit=2)
    with selection_execution_budget(resumed):
        bound, stage = execution_budget("rardar_worth_seeing_copy")
        with pytest.raises(ProviderBudgetError, match="exhausted"), bound.execution(stage):
            pytest.fail("must never dispatch")
    assert resumed.snapshot()["attempted"] == 2
