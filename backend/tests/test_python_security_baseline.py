"""Focused regressions for the audited FastAPI/Starlette security boundary."""

from __future__ import annotations

from importlib.metadata import version

import httpx
import pytest
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest


def _request(*, path: str, host: str) -> StarletteRequest:
    return StarletteRequest(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(b"host", host.encode())],
            "client": ("127.0.0.1", 1234),
            "server": ("trusted.test", 80),
        }
    )


def _form_app() -> FastAPI:
    app = FastAPI()

    @app.post("/form")
    async def parse_form(request: Request):
        form = await request.form(max_fields=1, max_part_size=4)
        return {"keys": list(form.keys())}

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)):
        return {"filename": file.filename, "content": (await file.read()).decode()}

    return app


def test_audited_framework_versions_are_installed_together():
    assert version("fastapi") == "0.133.0"
    assert version("starlette") == "1.3.1"
    assert version("cryptography") == "50.0.0"


def test_request_url_keeps_host_and_path_authority_boundaries():
    host_injection = _request(path="/callback", host="trusted.test/forged")
    assert str(host_injection.url) == "http://trusted.test/callback"
    assert host_injection.url.hostname == "trusted.test"

    authority_like_path = _request(path="@evil.test/callback", host="trusted.test")
    assert str(authority_like_path.url) == "http://trusted.test/@evil.test/callback"
    assert authority_like_path.url.hostname == "trusted.test"
    assert authority_like_path.url.path == "/@evil.test/callback"


@pytest.mark.asyncio
async def test_urlencoded_form_limits_are_enforced():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_form_app()),
        base_url="http://testserver",
    ) as client:
        too_many = await client.post(
            "/form",
            content="one=1&two=2",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        too_large = await client.post(
            "/form",
            content="first=12345",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert too_many.status_code == 400
    assert too_many.json()["detail"] == "Too many fields. Maximum number of fields is 1."
    assert too_large.status_code == 400
    assert too_large.json()["detail"] == "Field exceeded maximum size of 0KB."


@pytest.mark.asyncio
async def test_multipart_upload_and_malformed_body_contracts():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_form_app()),
        base_url="http://testserver",
    ) as client:
        uploaded = await client.post(
            "/upload",
            files={"file": ("feeds.opml", b"<opml />", "text/xml")},
        )
        malformed = await client.post(
            "/upload",
            content=b"--bad",
            headers={"content-type": "multipart/form-data; boundary=missing"},
        )

    assert uploaded.status_code == 200
    assert uploaded.json() == {"filename": "feeds.opml", "content": "<opml />"}
    assert malformed.status_code == 400
    assert malformed.json()["detail"] == "There was an error parsing the body"


@pytest.mark.asyncio
async def test_cors_and_base_http_middleware_contracts():
    class MarkerMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers["x-security-baseline"] = request.url.path
            return response

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://frontend.test"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.add_middleware(MarkerMiddleware)

    @app.get("/status")
    async def status():
        return {"status": "ok"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/status", headers={"origin": "https://frontend.test"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.test"
    assert response.headers["x-security-baseline"] == "/status"


def test_default_application_openapi_still_contains_core_routes():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/sources" in paths
    assert "/api/v1/sources/import-opml" in paths
