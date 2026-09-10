from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.integrations.rardar import selection, selection_period, selection_serving
from app.services import rardar_daily_operations as daily


def artifact(identifier, project_id=1, **overrides):
    return SimpleNamespace(
        **{
            "selectionGenerationId": identifier,
            "sourceObservationSetId": "source",
            "sourceManifestSha256": "manifest",
            "todayGenerationId": "today",
            "modelRouteIdentity": "route",
            "contractVersions": selection._contract_versions(),
            "assessedCount": 1,
            "inputDigest": "binding",
            "publishedCount": 0,
            "generatedAt": datetime(2026, 9, 10, tzinfo=UTC),
            "assessments": [
                SimpleNamespace(
                    candidate=SimpleNamespace(githubRepositoryId=project_id),
                    gate=object(),
                    valueFailureCode=None,
                    copyFailureCode=None,
                )
            ],
            **overrides,
        }
    )


def source():
    return SimpleNamespace(source_observation_set_id="source", manifest_sha256="manifest", today_generation_id="today")


def test_publication_validates_then_filters_stale_route_policy_and_source(tmp_path, monkeypatch):
    children = {
        "current": artifact("current"),
        "old-route": artifact("old-route", modelRouteIdentity="old"),
        "old-policy": artifact("old-policy", contractVersions={"old": "policy"}),
        "old-source": artifact("old-source", sourceObservationSetId="old"),
        "old-today": artifact("old-today", todayGenerationId="old"),
        "period": SimpleNamespace(publishedCount=0, processedCount=1, currentEligible=True, semanticResolvedCount=1),
    }
    validated = []

    def validate(_self, key):
        validated.append(key)
        return children[key]

    monkeypatch.setattr(selection_serving.SelectionServingLoader, "validate_generation", validate)
    monkeypatch.setattr(selection_period, "with_current_period", lambda _target, keys: keys)
    publish = Mock(return_value=SimpleNamespace(current_changed=False, selection_generation_id="period"))
    monkeypatch.setattr(selection_period, "publish_period", publish)
    progress = {key: {"generationId": key} for key in children if key != "period"}
    result = daily._publish_discover(
        tmp_path, source(), [SimpleNamespace(githubRepositoryId=1)], progress, route="route"
    )
    assert publish.call_args.args[1] == ["current"]
    assert set(validated) == set(children)
    assert not result["installed"]
    assert result["reason"] == "unchanged"


def test_cursor_advances_in_actual_order_not_numeric_guess():
    batches = [("page", (value,)) for value in (9, 2, 7)]
    assert [ids[0] for _, ids in daily._rotate_discover_work(batches, 9)] == [2, 7, 9]
    assert [ids[0] for _, ids in daily._rotate_discover_work(batches, 7)] == [9, 2, 7]


@pytest.mark.asyncio
async def test_waiting_singleton_does_not_block_later_cache_and_counts_accumulate(tmp_path, monkeypatch):
    from app.services import rardar_discover_operations as manual, rardar_llm_control
    from app.services.llm import daily_provider_budget as budget
    from app.services.llm.daily_provider_budget import ProviderWorkYield
    from app.services.llm.run_failure_guard import RunFailureGuard
    from scripts import rebuild_rardar_discover_selection as builder

    monkeypatch.setattr(budget, "daily_root", lambda: tmp_path / "budget")
    monkeypatch.setattr(daily, "operation_root", lambda: tmp_path / "operations")
    monkeypatch.setattr(manual, "latest_operation", lambda: None)
    monkeypatch.setattr(rardar_llm_control, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    monkeypatch.setattr(selection, "selection_input_digest", lambda *_a, **_k: "binding")
    ledger = budget.daily_ledger(100)
    guard = RunFailureGuard(isolate_stages=True)
    artifacts = {}
    calls = []
    failure_allowances = []

    async def rebuild(_target, **kwargs):
        identifier = kwargs["process_candidate_ids"][0]
        calls.append(identifier)
        assert kwargs["publish"] is False
        if identifier == 1:
            raise ProviderWorkYield("interactive_budget_reserved")
        saved = artifact(str(identifier), identifier)
        if identifier == 3:
            failure_allowances.append(kwargs["provider_calls_allowed"])
            saved.assessments[0].gate = None
            saved.assessments[0].valueFailureCode = "schema_invalid"
        artifacts[str(identifier)] = saved
        return {
            "selectionGenerationId": str(identifier),
            "modelCalls": int(identifier == 3 and kwargs["provider_calls_allowed"]),
        }

    monkeypatch.setattr(builder, "rebuild", rebuild)
    monkeypatch.setattr(
        selection_serving.SelectionServingLoader, "validate_generation", lambda _self, key=None: artifacts[key]
    )
    universe = [SimpleNamespace(githubRepositoryId=index) for index in (1, 2, 3)]
    progress = {}
    results = []
    for _ in range(3):
        results.append(
            await daily._discover(
                tmp_path, source(), universe, ledger, progress, lambda: None, max_batches=1, guard=guard
            )
        )
    assert calls == [1, 2, 3]
    assert results[0]["waitingCount"] == 1 and results[0]["hasMore"]
    assert results[1]["processed"] == 1 and results[1]["completed"] == 1
    assert results[2]["processed"] == 2 and results[2]["completed"] == 1
    assert results[2]["failed"] == 1 and results[2]["waitingCount"] == 1
    assert not results[2]["hasMore"]
    assert "1" not in progress  # Waiting is not a false failed/complete artifact.
    assert progress["_waiting"]["1"]["reason"] == "interactive_budget_reserved"
    assert ledger.snapshot()["attempted"] == 0
    for _ in range(2):
        await daily._discover(
            tmp_path, source(), universe, ledger, progress, lambda: None, guard=RunFailureGuard(isolate_stages=True)
        )
    assert failure_allowances == [True, True, False]
    assert progress["3"]["failedAttempts"] == 2
    assert "failedAttempts" not in progress["_waiting"]["1"]
