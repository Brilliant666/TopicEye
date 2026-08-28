from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import rardar as rardar_api
from app.schemas.rardar_product import FindProjectResponse, ProjectExplanationResponse
from app.services.rardar_product import RardarProductError


def _client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(rardar_api.router, prefix="/api/v1")
    monkeypatch.setattr(rardar_api, "is_rardar_product", lambda: True)
    return TestClient(app)


def test_explanation_endpoint_exposes_stable_revision_error(monkeypatch) -> None:
    async def changed(_payload):
        raise RardarProductError("rardar_project_revision_changed")

    monkeypatch.setattr(rardar_api, "explain_project", changed)
    response = _client(monkeypatch).post(
        "/api/v1/rardar/projects/explain",
        json={"repository": "owner/repository", "generationId": "generation-v1"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "rardar_project_revision_changed"}


def test_explanation_endpoint_keeps_ai_failure_as_a_product_state(monkeypatch) -> None:
    async def unavailable(payload):
        return ProjectExplanationResponse(
            state="unavailable",
            repository=payload.repository,
            generationId=payload.generationId,
            promptVersion="rardar-project-insight-v3",
            schemaVersion="rardar-project-insight-schema-v3",
            format="none",
            officialIntro={
                "text": "官方资料暂未提供简介。",
                "sourceLabel": "AI受限概括",
                "evidenceRefs": ["repository"],
            },
            errorCode="rardar_llm_unavailable",
            evidenceDigest="a" * 64,
            evidenceKinds=["repository"],
        )

    monkeypatch.setattr(rardar_api, "explain_project", unavailable)
    response = _client(monkeypatch).post(
        "/api/v1/rardar/projects/explain",
        json={"repository": "owner/repository", "generationId": "generation-v1"},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"


def test_stable_insight_endpoint_uses_numeric_identity_and_generation_only(monkeypatch) -> None:
    received: list[tuple[int, str]] = []

    async def unavailable(identifier, generation):
        received.append((identifier, generation))
        return ProjectExplanationResponse(
            state="unavailable",
            repository="owner/repository",
            githubRepositoryId=identifier,
            generationId=generation,
            promptVersion="rardar-project-insight-v3",
            schemaVersion="rardar-project-insight-schema-v3",
            format="none",
            officialIntro={
                "text": "官方资料暂未提供简介。",
                "sourceLabel": "AI受限概括",
                "evidenceRefs": ["repository"],
            },
            errorCode="rardar_llm_unavailable",
            evidenceDigest="a" * 64,
            evidenceKinds=["repository"],
        )

    monkeypatch.setattr(rardar_api, "explain_project_by_id", unavailable)
    response = _client(monkeypatch).post(
        "/api/v1/rardar/projects/1211139949/insight",
        json={"generationId": "generation-v2"},
    )

    assert response.status_code == 200
    assert received == [(1211139949, "generation-v2")]
    assert response.json()["githubRepositoryId"] == 1211139949


def test_find_endpoint_returns_facts_when_ai_is_unavailable(monkeypatch) -> None:
    async def find(payload):
        return FindProjectResponse(
            requirement=payload.requirement,
            repositoryUrl=payload.repositoryUrl,
            searchState="limited",
            coverageLabel="有限覆盖",
            sources=[],
            quickCandidates=[],
            aiState="insufficient_candidates",
            promptVersion="rardar-find-project-v1",
        )

    monkeypatch.setattr(rardar_api, "find_projects", find)
    response = _client(monkeypatch).post(
        "/api/v1/rardar/find-projects",
        json={"requirement": "我需要一个可复用的视频工具", "repositoryUrl": None},
    )
    assert response.status_code == 200
    assert response.json()["aiState"] == "insufficient_candidates"


def test_product_endpoints_are_hidden_outside_rardar_mode(monkeypatch) -> None:
    monkeypatch.setattr(rardar_api, "is_rardar_product", lambda: False)
    client = TestClient(FastAPI())
    client.app.include_router(rardar_api.router, prefix="/api/v1")
    response = client.post(
        "/api/v1/rardar/find-projects",
        json={"requirement": "我需要一个可复用的视频工具", "repositoryUrl": None},
    )
    assert response.status_code == 404
