import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.integrations.rardar.selection_execution import selection_writer
from app.integrations.rardar.selection_serving import SelectionServingError
from app.services.llm.provider_budget import ProviderBudgetError
from scripts import rebuild_rardar_discover_selection as rebuild_module


def test_writer_reenters_same_execution_but_rejects_other_thread(tmp_path):
    observed = []

    def contender():
        try:
            with selection_writer(tmp_path):
                observed.append("entered")
        except ProviderBudgetError as exc:
            observed.append(exc.code)

    with selection_writer(tmp_path):
        with selection_writer(tmp_path):
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive()
        assert observed == ["provider_budget_busy"]
    with selection_writer(tmp_path):
        pass


def test_writer_releases_after_failure(tmp_path):
    with pytest.raises(ValueError), selection_writer(tmp_path):
        raise ValueError("test")
    with selection_writer(tmp_path):
        pass


@pytest.mark.asyncio
async def test_confirmed_route_change_stops_before_build(tmp_path, monkeypatch):
    source = SimpleNamespace(source_observation_set_id="source", today_generation_id="today")
    monkeypatch.setattr(
        rebuild_module.SelectionSourceAdapter, "from_config", lambda _: SimpleNamespace(load=lambda: source)
    )
    monkeypatch.setattr(rebuild_module, "resolve_rardar_route_identity", AsyncMock(return_value="changed"))
    build = AsyncMock()
    monkeypatch.setattr(rebuild_module, "build_selection", build)
    with pytest.raises(SelectionServingError) as error:
        await rebuild_module.rebuild(
            tmp_path, recall_batch_id="batch", expected_source_id="source", expected_route_identity="confirmed"
        )
    assert error.value.code == "rardar_selection_route_changed"
    build.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_drift_before_install_keeps_current(tmp_path, monkeypatch):
    source = SimpleNamespace(source_observation_set_id="source", today_generation_id="today")
    changed = SimpleNamespace(source_observation_set_id="changed", today_generation_id="today")
    read = Mock(side_effect=[source, source, changed])
    monkeypatch.setattr(rebuild_module.SelectionSourceAdapter, "from_config", lambda _: SimpleNamespace(load=read))
    monkeypatch.setattr(rebuild_module, "resolve_rardar_route_identity", AsyncMock(return_value="route"))
    monkeypatch.setattr(rebuild_module, "selection_input_digest", lambda *a, **kw: "digest")
    loader = SimpleNamespace(
        validate_generation=Mock(side_effect=SelectionServingError("rardar_selection_not_configured", "missing"))
    )
    monkeypatch.setattr(rebuild_module, "SelectionServingLoader", lambda _: loader)
    monkeypatch.setattr(rebuild_module, "build_selection", AsyncMock(return_value=object()))
    monkeypatch.setattr(rebuild_module, "build_selection_serving", lambda _: object())
    install = Mock()
    monkeypatch.setattr(rebuild_module, "install_selection_serving", install)
    with pytest.raises(SelectionServingError) as error:
        await rebuild_module.rebuild(tmp_path, recall_batch_id="batch", expected_source_id="source")
    assert error.value.code == "rardar_selection_source_changed"
    install.assert_not_called()
