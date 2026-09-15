"""Synthetic failures only: no GitHub or Provider requests."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import BaseModel, ValidationError

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
