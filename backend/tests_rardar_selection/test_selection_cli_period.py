from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm.daily_provider_budget import ProviderWorkYield
from scripts import rebuild_rardar_discover_selection as script


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", [False, True])
async def test_cli_computes_singletons_then_publishes_once(monkeypatch, tmp_path, waiting):
    from app.integrations.rardar import selection_period

    source = SimpleNamespace(source_observation_set_id="source", today_generation_id="today")
    monkeypatch.setattr(script.SelectionSourceAdapter, "from_config", lambda _: SimpleNamespace(load=lambda: source))
    monkeypatch.setattr(script, "resolve_rardar_route_identity", AsyncMock(return_value="a" * 64))
    attempts = []

    async def rebuild(target, **kwargs):
        attempts.append(kwargs)
        assert kwargs["publish"] is False
        (identifier,) = kwargs["process_candidate_ids"]
        if waiting and identifier == 1:
            raise ProviderWorkYield("daily_budget_exhausted")
        return {"selectionGenerationId": str(identifier), "modelCalls": 0}

    monkeypatch.setattr(script, "rebuild", rebuild)
    monkeypatch.setattr(selection_period, "with_current_period", lambda target, children: children)
    publications = []

    def publish(target, children, **kwargs):
        publications.append(children)
        return SimpleNamespace(selection_generation_id="period", current_changed=True, changed=True)

    monkeypatch.setattr(selection_period, "publish_period", publish)
    monkeypatch.setattr(
        script.SelectionServingLoader,
        "validate_generation",
        lambda *_: SimpleNamespace(
            currentEligible=True,
            state="ready",
            publishedCount=1,
        ),
    )
    result = await script.rebuild_period(tmp_path, recall_batch_id="batch", process_candidate_ids=(1, 2))
    assert len(attempts) == 2
    assert publications == [["2"] if waiting else ["1", "2"]]
    assert result["status"] == ("waiting" if waiting else "healthy")
    assert result["modelCalls"] == 0


def test_cli_waiting_has_distinct_exit_status(monkeypatch, tmp_path):
    monkeypatch.setattr(script.sys, "argv", ["selection", "build", "--target", str(tmp_path)])
    monkeypatch.setattr(script, "rebuild_period", AsyncMock(return_value={"status": "waiting"}))
    assert script.main() == 2
