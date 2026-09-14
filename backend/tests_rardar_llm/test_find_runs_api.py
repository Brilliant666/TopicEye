"""Private durable API routing with service doubles; no DB/source/Provider access."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import auth, rardar as api
from app.services.rardar_find_runs import FindRunError


def _saved_candidate_result():
    return {
        "requirement": "需要一个自托管文档站",
        "repositoryUrl": None,
        "searchState": "github_live",
        "coverageLabel": "Isolated regression fixture",
        "sources": ["https://github.com/example/docs"],
        "quickCandidates": [
            {
                "githubRepositoryId": 123,
                "repository": "example/docs",
                "totalStars": 20,
                "updatedAt": "2026-09-14T00:00:00Z",
                "pushedAt": "2026-09-13T00:00:00Z",
                "htmlUrl": "https://github.com/example/docs",
                "preliminaryMatch": "Documentation candidate",
                "dataState": "github_live",
            }
        ],
        "aiState": "unavailable",
        "errorCode": "rardar_llm_invalid_output",
        "promptVersion": "rardar-find-project-v5",
    }


def _run():
    return {
        "runId": "stable-id",
        "status": "created",
        "stage": "created",
        "createdAt": "2026-09-14T00:00:00Z",
        "updatedAt": "2026-09-14T00:00:00Z",
        "finishedAt": None,
        "request": {"requirement": "需要一个自托管文档站", "repositoryUrl": None},
        "result": None,
        "errorCode": None,
        "requestLimit": 2,
        "requestsUsed": 0,
        "schemaVersion": "rardar-find-run-v1",
    }


@pytest.fixture
def setup(monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    monkeypatch.setattr(api, "is_rardar_product", lambda: True)
    monkeypatch.setattr(api.settings, "CORS_ORIGINS", "http://testserver")
    service = SimpleNamespace(
        **{name: AsyncMock(return_value=_run()) for name in ("create", "get", "by_key", "execute")}
    )
    service.recent = AsyncMock(return_value={"runs": []})
    monkeypatch.setattr(api, "find_runs", service)
    return app, TestClient(app), service


def _headers():
    return {"Origin": api.settings.cors_origins[0], "Idempotency-Key": "test-same-key-0001"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/find-runs/stable-id"),
        ("get", "/find-runs/by-key/test-same-key-0001"),
        ("post", "/find-runs/stable-id/execute"),
        ("post", "/find-projects"),
    ],
)
def test_real_response_routes_restore_saved_json_dates(setup, method, path):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 1
    saved = {**_run(), "status": "partial", "result": _saved_candidate_result()}
    for name in ("get", "by_key", "execute"):
        getattr(service, name).return_value = saved
    response = getattr(client, method)(
        f"/api/v1/rardar{path}",
        headers=_headers(),
        **({"json": _run()["request"]} if path == "/find-projects" else {}),
    )
    assert response.status_code == 200
    body = response.json() if path == "/find-projects" else response.json()["result"]
    assert body["quickCandidates"][0]["updatedAt"] == "2026-09-14T00:00:00Z"
    assert body["errorCode"] == "rardar_llm_invalid_output"
    if method == "get":
        service.execute.assert_not_awaited()
        service.create.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value",
    [
        ("updatedAt", "not-a-date"),
        ("updatedAt", "2026-09-14T00:00:00"),
        ("totalStars", "20"),
        ("githubRepositoryId", "123"),
    ],
)
def test_json_restore_keeps_strict_types_and_timezone(field, value):
    from pydantic import ValidationError

    from app.schemas.rardar_find_runs import restore_find_result

    saved = _saved_candidate_result()
    saved["quickCandidates"][0][field] = value
    with pytest.raises(ValidationError):
        restore_find_result(saved)


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", ""),
        ("post", "/stable-id/execute"),
        ("get", ""),
        ("get", "/stable-id"),
        ("get", "/by-key/test-same-key-0001"),
    ],
)
def test_anonymous_requests_never_reach_service(setup, method, path):
    app, client, service = setup

    async def anonymous():
        raise HTTPException(401, "Application login required")

    app.dependency_overrides[api._find_user_id] = anonymous
    response = getattr(client, method)(
        f"/api/v1/rardar/find-runs{path}", **({"json": _run()["request"]} if method == "post" else {})
    )
    assert response.status_code == 401
    for operation in vars(service).values():
        operation.assert_not_awaited()


def test_basic_edge_authorization_alone_is_not_application_identity(setup, monkeypatch):
    _app, client, service = setup
    db = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def no_db():
        yield db

    monkeypatch.setattr(api, "async_session", no_db)
    response = client.get("/api/v1/rardar/find-runs", headers={"Authorization": "Basic c3ludGhldGljOnRlc3Q="})
    assert response.status_code == 401
    db.commit.assert_not_awaited()
    service.recent.assert_not_awaited()


def test_basic_header_with_valid_app_cookie_uses_app_identity(setup, monkeypatch):
    _app, client, service = setup
    db = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def no_db():
        yield db

    token_lookup = AsyncMock(return_value=SimpleNamespace(id=21))
    monkeypatch.setattr(api, "async_session", no_db)
    monkeypatch.setattr(auth, "get_user_for_token", token_lookup)
    client.cookies.set(api.settings.AUTH_COOKIE_NAME, "synthetic-app-cookie")
    response = client.get("/api/v1/rardar/find-runs", headers={"Authorization": "Basic c3ludGhldGljOnRlc3Q="})
    assert response.status_code == 200
    assert token_lookup.await_args.args[1] == "synthetic-app-cookie"
    db.commit.assert_awaited_once_with()
    service.recent.assert_awaited_once_with(21)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://untrusted.example"},
        {"Origin": "https://untrusted.example", "Authorization": "Basic c3ludGhldGljOnRlc3Q="},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
    ],
)
@pytest.mark.parametrize("path", ["", "/stable-id/execute"])
def test_cookie_posts_require_allowed_origin(setup, headers, path):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 11
    response = client.post(f"/api/v1/rardar/find-runs{path}", headers=headers, json=_run()["request"])
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "find_origin_rejected"
    service.create.assert_not_awaited()
    service.execute.assert_not_awaited()


def test_create_commits_identity_without_execute(setup):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 12
    response = client.post("/api/v1/rardar/find-runs", headers=_headers(), json=_run()["request"])
    assert response.status_code == 200
    assert response.json()["runId"] == "stable-id"
    assert response.headers["cache-control"] == "private, no-store"
    args = service.create.await_args.args
    assert args[0] == 12 and args[1].requirement == _run()["request"]["requirement"]
    assert args[2] == "test-same-key-0001"
    service.execute.assert_not_awaited()


def test_gets_forward_only_trusted_identity_and_never_execute(setup):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 13
    for path in ("", "/by-key/test-same-key-0001", "/stable-id"):
        response = client.get(f"/api/v1/rardar/find-runs{path}?owner=999")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
    service.recent.assert_awaited_once_with(13)
    service.by_key.assert_awaited_once_with(13, "test-same-key-0001")
    service.get.assert_awaited_once_with(13, "stable-id")
    service.create.assert_not_awaited()
    service.execute.assert_not_awaited()


def test_other_user_cannot_read_private_run(setup):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 14
    service.get.side_effect = FindRunError("find_run_not_found", 404)
    response = client.get("/api/v1/rardar/find-runs/stable-id")
    assert response.status_code == 404
    service.get.assert_awaited_once_with(14, "stable-id")
    service.execute.assert_not_awaited()


def test_execute_does_not_create_another_run(setup):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 15
    response = client.post("/api/v1/rardar/find-runs/stable-id/execute", headers=_headers())
    assert response.status_code == 200
    service.execute.assert_awaited_once_with(15, "stable-id")
    service.create.assert_not_awaited()


def test_persistence_failure_is_not_http_success(setup):
    app, client, service = setup
    app.dependency_overrides[api._find_user_id] = lambda: 16
    service.execute.side_effect = FindRunError("find_result_save_failed", 503)
    response = client.post("/api/v1/rardar/find-runs/stable-id/execute", headers=_headers())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "find_result_save_failed"
