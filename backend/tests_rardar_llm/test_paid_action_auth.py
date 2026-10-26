"""Paid-action auth boundaries with in-process HTTP and inert business/DB doubles."""

import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, rardar as api
from app.schemas.rardar_product import FindProjectResponse, ProjectExplanationResponse, SharedProjectInsightStatus
from app.services import rardar_project_insights, rardar_trending

ORIGIN = "https://rardar.dokitool.com"
BASIC = "Basic c3ludGhldGljOnRlc3Q="
REQUEST_ID = "11000000-0000-4000-8000-000000000001"
PLAN_ID = "22000000-0000-4000-8000-000000000002"
PAID_POSTS = [
    ("/project-insights/saved-project", {"generationId": "saved-generation"}, "shared"),
    ("/projects/explain", {"repository": "owner/project", "generationId": "saved-generation"}, "explain"),
    ("/projects/42/insight", {"generationId": "saved-generation"}, "insight"),
    ("/discover/projects/42/insight", {"generationId": "saved-generation"}, "discover_insight"),
    ("/find-projects", {"requirement": "需要一个自托管文档工具"}, "find_legacy"),
    ("/find-runs", {"requirement": "需要一个自托管文档工具"}, "find_create"),
    ("/find-runs/saved-run/execute", {}, "find_execute"),
    ("/today/operations", {"requestId": REQUEST_ID}, "today"),
    ("/hotspot-news/operations", {"requestId": REQUEST_ID, "action": "refresh"}, "news"),
    ("/discover/operations/prepare", {"requestId": REQUEST_ID}, "discover_prepare"),
    ("/discover/operations", {"requestId": REQUEST_ID, "planId": PLAN_ID}, "discover"),
]
USER_POSTS = PAID_POSTS[:7]
ACTIVE_USER_POSTS = [case for case in USER_POSTS if case[2] != "discover_insight"]


def _explanation():
    return ProjectExplanationResponse(
        state="unavailable",
        repository="owner/project",
        githubRepositoryId=42,
        generationId="saved-generation",
        promptVersion="rardar-project-insight-v5",
        schemaVersion="rardar-project-insight-schema-v5",
        format="none",
        officialIntro={"text": "已保存的介绍", "sourceLabel": "官方介绍", "evidenceRefs": ["repository"]},
        errorCode="rardar_llm_unavailable",
        evidenceDigest="a" * 64,
        evidenceKinds=["repository"],
    )


@pytest.fixture
def setup(monkeypatch):
    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("Network is forbidden in auth regressions")

    monkeypatch.setattr(api, "is_rardar_product", lambda: True)
    monkeypatch.setattr(api.settings, "RARDAR_PRODUCT_MODE", True)
    monkeypatch.setattr(api.settings, "APP_ENV", "development")
    monkeypatch.setattr(api.settings, "CORS_ORIGINS", ORIGIN)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    db = SimpleNamespace(commit=AsyncMock())

    async def inert_db():
        yield db

    @asynccontextmanager
    async def inert_session():
        yield db

    app.dependency_overrides[api.get_db] = inert_db
    monkeypatch.setattr(api, "async_session", inert_session)

    async def token_user(_db, token):
        if token in {"valid-cookie", "valid-bearer"}:
            return SimpleNamespace(id=9, role="admin")
        return None

    token_lookup = AsyncMock(side_effect=token_user)
    monkeypatch.setattr(auth, "get_user_for_token", token_lookup)
    saved_result = FindProjectResponse(
        requirement="需要一个自托管文档工具",
        repositoryUrl=None,
        searchState="limited",
        coverageLabel="已保存的结果",
        sources=[],
        quickCandidates=[],
        aiState="insufficient_candidates",
        promptVersion="rardar-find-project-v4",
    ).model_dump(mode="json")
    run = {
        "runId": "saved-run",
        "status": "completed",
        "stage": "completed",
        "createdAt": "2026-10-26T00:00:00Z",
        "updatedAt": "2026-10-26T00:00:00Z",
        "finishedAt": "2026-10-26T00:00:00Z",
        "request": {"requirement": "需要一个自托管文档工具", "repositoryUrl": None},
        "result": saved_result,
        "errorCode": None,
        "requestLimit": 2,
        "requestsUsed": 0,
        "schemaVersion": "rardar-find-run-v1",
    }
    operations = {}
    for name, module, attribute, result in (
        ("shared", rardar_project_insights, "start_project_insight", SharedProjectInsightStatus(state="waiting")),
        ("explain", api, "explain_project", _explanation()),
        ("insight", api, "explain_project_by_id", _explanation()),
        ("discover_insight", api, "explain_discover_project_by_id", _explanation()),
        ("find_create", api.find_runs, "create", run),
        ("find_execute", api.find_runs, "execute", run),
        ("today", api.today_operations, "start_operation", {"id": "test", "status": "running"}),
        ("news", api.news_operations, "start_operation", {"id": "test", "status": "running"}),
        ("discover_prepare", api.discover_operations, "prepare_operation", {"id": "test"}),
        ("discover", api.discover_operations, "start_operation", {"id": "test", "status": "running"}),
    ):
        operations[name] = AsyncMock(return_value=result)
        monkeypatch.setattr(module, attribute, operations[name])
    with TestClient(app) as client:
        # Windows creates an internal loop socketpair while entering TestClient;
        # deny all subsequent connections, including local DB/source attempts.
        monkeypatch.setattr(socket.socket, "connect", forbidden_network)
        yield client, operations, token_lookup


def _post(client, path, payload, headers=None):
    return client.post(
        f"/api/v1/rardar{path}",
        json=payload,
        headers={"Idempotency-Key": "auth-regression-key-0001", **(headers or {})},
    )


@pytest.mark.parametrize("path,payload,_operation", PAID_POSTS)
@pytest.mark.parametrize("credential", ["anonymous", "expired_cookie", "invalid_bearer", "edge_basic"])
def test_every_paid_post_rejects_missing_or_invalid_application_identity(setup, path, payload, _operation, credential):
    client, operations, _lookup = setup
    headers = {"Origin": ORIGIN}
    if credential == "expired_cookie":
        client.cookies.set(api.settings.AUTH_COOKIE_NAME, "expired-cookie")
    elif credential == "invalid_bearer":
        headers["Authorization"] = "Bearer invalid-token"
    elif credential == "edge_basic":
        headers["Authorization"] = BASIC
    response = _post(client, path, payload, headers)
    assert response.status_code == 401, response.text
    for operation in operations.values():
        operation.assert_not_awaited()


@pytest.mark.parametrize("path,payload,_operation", USER_POSTS)
@pytest.mark.parametrize("authorization", [None, BASIC])
@pytest.mark.parametrize(
    "origin_headers",
    [{}, {"Origin": "https://attacker.invalid"}, {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"}],
)
def test_cookie_paid_posts_require_trusted_origin_even_with_edge_basic(
    setup, path, payload, _operation, authorization, origin_headers
):
    client, operations, _lookup = setup
    client.cookies.set(api.settings.AUTH_COOKIE_NAME, "valid-cookie")
    headers = {**origin_headers}
    if authorization:
        headers["Authorization"] = authorization
    response = _post(client, path, payload, headers)
    assert response.status_code == 403, response.text
    for operation in operations.values():
        operation.assert_not_awaited()


@pytest.mark.parametrize("path,payload,operation", ACTIVE_USER_POSTS)
@pytest.mark.parametrize("credential", ["cookie", "cookie_and_basic", "bearer"])
def test_authorized_paid_posts_only_reach_the_expected_business_call(setup, path, payload, operation, credential):
    client, operations, lookup = setup
    headers = {"Origin": ORIGIN}
    if credential == "bearer":
        headers = {"Authorization": "Bearer valid-bearer"}
        expected_token = "valid-bearer"
    else:
        client.cookies.set(api.settings.AUTH_COOKIE_NAME, "valid-cookie")
        expected_token = "valid-cookie"
        if credential == "cookie_and_basic":
            headers["Authorization"] = BASIC
    response = _post(client, path, payload, headers)
    assert response.status_code == 200, response.text
    assert lookup.await_args.args[1] == expected_token
    expected = {operation} if operation != "find_legacy" else {"find_create", "find_execute"}
    for name, business_call in operations.items():
        if name in expected:
            business_call.assert_awaited_once()
        else:
            business_call.assert_not_awaited()


@pytest.mark.parametrize("path,payload,_operation", USER_POSTS)
@pytest.mark.parametrize("authorization", ["Bearer invalid-token", "Bearer", "Digest not-an-app-token"])
def test_invalid_explicit_application_header_never_falls_back_to_valid_cookie(
    setup, path, payload, _operation, authorization
):
    client, operations, _lookup = setup
    client.cookies.set(api.settings.AUTH_COOKIE_NAME, "valid-cookie")
    response = _post(client, path, payload, {"Origin": ORIGIN, "Authorization": authorization})
    assert response.status_code == 401, response.text
    for operation in operations.values():
        operation.assert_not_awaited()


def test_edge_basic_cannot_skip_admin_cookie_origin_guard(setup):
    client, operations, _lookup = setup
    # Admin auth remains owned by the existing application dependency; isolate
    # the independent origin gate after a successfully resolved admin here.
    client.app.dependency_overrides[api.get_current_admin_user] = lambda: SimpleNamespace(id=9)
    response = _post(
        client,
        "/today/operations",
        {"requestId": REQUEST_ID},
        {"Origin": "https://attacker.invalid", "Authorization": BASIC},
    )
    assert response.status_code == 403
    operations["today"].assert_not_awaited()


def test_discover_insight_stays_paused_after_authorization(setup):
    client, operations, _lookup = setup
    response = _post(
        client,
        "/discover/projects/42/insight",
        {"generationId": "saved-generation"},
        {"Authorization": "Bearer valid-bearer"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "rardar_discover_paused"}
    operations["discover_insight"].assert_not_awaited()


@pytest.mark.parametrize(
    "path,service",
    [
        ("/trending-today", "today"),
        ("/historical-hot", "history"),
        ("/trending-projects/saved-project?generation=saved-generation", "detail"),
        ("/historical-projects/saved-project", "detail"),
        ("/project-insights/saved-project?generationId=saved-generation", "shared"),
    ],
)
def test_saved_public_gets_remain_anonymous_and_never_start_paid_work(setup, monkeypatch, path, service):
    client, operations, lookup = setup
    if service == "shared":
        read = AsyncMock(return_value=SharedProjectInsightStatus(state="unprocessed"))
        monkeypatch.setattr(rardar_project_insights, "read_project_insight", read)
    else:
        monkeypatch.setattr(rardar_trending, service, lambda *_args, **_kwargs: {"saved": True})
    response = client.get(f"/api/v1/rardar{path}")
    assert response.status_code == 200, response.text
    lookup.assert_not_awaited()
    for operation in operations.values():
        operation.assert_not_awaited()
