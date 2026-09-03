from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.llm.provider_budget import (
    ProviderBudgetError,
    ProviderBudgetLedger,
    budget_stage,
    execution_budget,
)


def ledger_at(tmp_path: Path) -> ProviderBudgetLedger:
    return ProviderBudgetLedger.initialize(tmp_path / "run-1" / "provider-budget.json", "run-1")


def test_missing_and_invalid_environment_fail_closed(monkeypatch, tmp_path):
    for name in ("RARDAR_LLM_RUN_ID", "RARDAR_LLM_BUDGET_PATH", "RARDAR_LLM_BUDGET_LIMIT"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ProviderBudgetError, match="missing"):
        execution_budget("rardar_worth_seeing_gate")
    assert execution_budget("general") is None
    ledger = ledger_at(tmp_path)
    monkeypatch.setenv("RARDAR_LLM_RUN_ID", "run-1")
    monkeypatch.setenv("RARDAR_LLM_BUDGET_PATH", str(ledger.path))
    monkeypatch.setenv("RARDAR_LLM_BUDGET_LIMIT", "40")
    with budget_stage("negative_control"):
        assert execution_budget("rardar_worth_seeing_gate")[1] == "negative_control"
    with pytest.raises(ProviderBudgetError, match="scene_forbidden"):
        execution_budget("rardar_project_profile")
    monkeypatch.setenv("RARDAR_LLM_RUN_ID", "different")
    with pytest.raises(ProviderBudgetError):
        execution_budget("rardar_worth_seeing_gate")


def test_shared_stages_failure_cache_and_crash_reservation(tmp_path):
    ledger = ledger_at(tmp_path)
    with ledger.execution("negative_control"):
        pass
    with pytest.raises(TimeoutError), ledger.execution("scope_value"):
        raise TimeoutError("not persisted")
    ledger.record("reserved", "format_retry")  # Simulated process death; never refunded.
    ledger.record("cache_hit", "user_copy")
    resumed = ProviderBudgetLedger(ledger.path, ledger.run_id).snapshot()
    assert (resumed["reserved"], resumed["attempted"], resumed["completed"]) == (3, 2, 2)
    assert (resumed["succeeded"], resumed["failed"], resumed["cacheHits"], resumed["remaining"]) == (1, 1, 1, 37)
    assert resumed["stageBreakdown"]["format_retry"] == 1
    assert "not persisted" not in ledger.events.read_text()


def test_two_processes_cannot_exceed_40(tmp_path):
    ledger = ledger_at(tmp_path)
    script = """
import sys
from pathlib import Path
from app.services.llm.provider_budget import ProviderBudgetLedger, ProviderBudgetError
ledger = ProviderBudgetLedger(Path(sys.argv[1]), 'run-1')
for _ in range(40):
    try: ledger.record('reserved', 'scope_value')
    except ProviderBudgetError as exc:
        assert exc.code == 'provider_budget_exhausted'
        break
"""
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(ledger.path)], cwd=Path(__file__).resolve().parents[1])
        for _ in range(2)
    ]
    for process in processes:
        assert process.wait(timeout=30) == 0
    assert ledger.snapshot()["reserved"] == 40
    before = ledger.events.read_bytes()
    with pytest.raises(ProviderBudgetError, match="exhausted"):
        ledger.record("reserved", "user_copy")
    assert ledger.events.read_bytes() == before


def test_no_reset_no_second_run_no_implicit_child_creation(tmp_path):
    ledger = ledger_at(tmp_path)
    with pytest.raises(ProviderBudgetError, match="already_initialized"):
        ledger_at(tmp_path)
    with pytest.raises(ProviderBudgetError, match="already_initialized"):
        ProviderBudgetLedger.initialize(tmp_path / "run-2" / "provider-budget.json", "run-2")
    missing = tmp_path / "child" / "provider-budget.json"
    with pytest.raises(ProviderBudgetError):
        ProviderBudgetLedger(missing, "child").snapshot()
    assert not missing.exists()
    assert ledger.snapshot()["remaining"] == 40


def test_digest_tamper_and_valid_crash_tail(tmp_path):
    ledger = ledger_at(tmp_path)
    old = ledger.path.read_bytes()
    ledger.record("reserved", "scope_value")
    ledger.path.write_bytes(old)  # Crash after journal fsync, before snapshot replacement.
    assert ledger.snapshot()["remaining"] == 39
    saved = json.loads(old)
    saved["remaining"] = 99
    ledger.path.write_text(json.dumps(saved))
    with pytest.raises(ProviderBudgetError):
        ledger.snapshot()


def test_journal_truncation_and_link_rejected(tmp_path):
    ledger = ledger_at(tmp_path)
    ledger.events.write_bytes(ledger.events.read_bytes()[:-1])
    with pytest.raises(ProviderBudgetError):
        ledger.snapshot()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(ledger.path.parent, target_is_directory=True)
    except OSError:
        if os.name == "nt":
            pytest.skip("Windows symlink privilege unavailable")
        raise
    with pytest.raises(ProviderBudgetError, match="unsafe_path"):
        ProviderBudgetLedger(linked / "provider-budget.json", "run-1").snapshot()


def test_execution_concurrency_is_one(tmp_path):
    ledger = ledger_at(tmp_path)
    with (
        ledger.execution("scope_value"),
        pytest.raises(ProviderBudgetError, match="busy"),
        ProviderBudgetLedger(ledger.path, "run-1").execution("user_copy"),
    ):
        pytest.fail("must not execute concurrently")
    assert ledger.snapshot()["attempted"] == 1
