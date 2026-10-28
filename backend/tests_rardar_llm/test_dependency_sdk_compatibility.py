"""Exercise upgraded dependencies at their real SDK boundaries, without egress."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import ipaddress
import json
import socket
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import pytest
from starlette.requests import Request

TEST_KEY = "sdk-contract-fixture-not-a-real-key"
API_BASE = "https://provider.invalid/v1"


@pytest.fixture(autouse=True)
def no_external_network_or_dotenv(monkeypatch):
    """Allow asyncio's local wakeup sockets, but no external TCP, DNS or HTTP."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def is_local(address):
        if not isinstance(address, tuple):
            return True  # Local Unix-domain sockets, where supported.
        try:
            return ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            return False

    def connect(sock, address):
        assert is_local(address), "SDK contract attempted external TCP"
        return original_connect(sock, address)

    def connect_ex(sock, address):
        assert is_local(address), "SDK contract attempted external TCP"
        return original_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        assert host in ("localhost", "127.0.0.1", "::1"), "SDK contract attempted external DNS"
        return original_getaddrinfo(host, *args, **kwargs)

    def deny_http(*_args, **_kwargs):
        raise AssertionError("Only an explicit SDK MockTransport may handle HTTP")

    async def deny_async_http(*_args, **_kwargs):
        deny_http()

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_http)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async_http)
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    monkeypatch.setenv("DO_NOT_TRACK", "true")

    # LiteLLM imports dotenv. Do not inspect or load any developer credentials.
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_args, **_kwargs: False)


def oauth_client(handler):
    from authlib.integrations.httpx_client._compat import httpx2
    from authlib.integrations.starlette_client import OAuth

    # Authlib 1.9.1 prefers httpx2 but retains the installed httpx fallback.
    registry = OAuth()
    registry.register(
        name="fixture",
        client_id="fixture-client",
        client_secret=TEST_KEY,
        authorize_url="https://oauth.invalid/authorize",
        access_token_url="https://oauth.invalid/token",
        api_base_url="https://oauth.invalid/",
        client_kwargs={
            "scope": "user:email",
            "transport": httpx2.MockTransport(handler),
            "trust_env": False,
        },
    )
    return registry.create_client("fixture"), httpx2


def request(session, query=""):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("rardar.invalid", 443),
            "path": "/callback",
            "query_string": query.encode(),
            "headers": [(b"host", b"rardar.invalid")],
            "session": session,
        }
    )


@pytest.mark.asyncio
async def test_authlib_real_registered_client_preserves_state_and_parses_callback():
    calls = []

    def handler(outgoing):
        calls.append(outgoing)
        assert outgoing.url.host == "oauth.invalid"
        if outgoing.url.path == "/token":
            assert outgoing.method == "POST"
            body = parse_qs(outgoing.content.decode())
            assert body["grant_type"] == ["authorization_code"]
            assert body["code"] == ["fixture-code"]
            assert body["redirect_uri"] == ["https://rardar.invalid/callback"]
            return transport_api.Response(
                200, json={"access_token": "fixture-access-token", "token_type": "Bearer", "expires_in": 3600}
            )
        assert outgoing.url.path == "/user"
        assert outgoing.headers["authorization"] == "Bearer fixture-access-token"
        return transport_api.Response(200, json={"id": 123, "login": "fixture-user"})

    client, transport_api = oauth_client(handler)
    assert client is not None
    session = {}
    redirected = await client.authorize_redirect(request(session), "https://rardar.invalid/callback")
    parameters = parse_qs(urlparse(redirected.headers["location"]).query)
    assert redirected.status_code == 302
    assert parameters["client_id"] == ["fixture-client"]
    assert parameters["response_type"] == ["code"]
    assert parameters["scope"] == ["user:email"]
    state = parameters["state"][0]
    assert state and session
    token = await client.authorize_access_token(request(session, urlencode({"state": state, "code": "fixture-code"})))
    assert token["access_token"] == "fixture-access-token"
    assert not session  # A callback consumes the saved state.
    user = await client.get("user", token=token)
    user.raise_for_status()
    assert user.json() == {"id": 123, "login": "fixture-user"}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_authlib_real_callback_rejects_unknown_state_before_http():
    from authlib.integrations.base_client.errors import MismatchingStateError

    calls = []

    def handler(outgoing):
        calls.append(outgoing)
        raise AssertionError("Invalid OAuth state must be rejected before HTTP")

    client, _ = oauth_client(handler)
    session = {}
    await client.authorize_redirect(request(session), "https://rardar.invalid/callback")
    with pytest.raises(MismatchingStateError):
        await client.authorize_access_token(request(session, "code=fixture-code&state=not-the-saved-state"))
    assert not calls


@pytest.mark.parametrize("empty_key", [b"", ""])
def test_authlib_rejects_empty_hmac_but_verifies_a_valid_signature(empty_key):
    from authlib.jose import JsonWebSignature
    from authlib.jose.errors import JoseError

    def encoded(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    payload = b'{"sub":"fixture-user"}'
    signing_input = encoded(b'{"alg":"HS256"}') + b"." + encoded(payload)
    forged = signing_input + b"." + encoded(hmac.new(b"", signing_input, hashlib.sha256).digest())
    signer = JsonWebSignature(algorithms=["HS256"])
    with pytest.raises((JoseError, ValueError)):
        signer.deserialize_compact(forged, empty_key)
    with pytest.raises((JoseError, ValueError)):
        signer.serialize_compact({"alg": "HS256"}, payload, empty_key)
    valid_key = b"fixture-signing-key-with-at-least-32-bytes"
    signed = signer.serialize_compact({"alg": "HS256"}, payload, valid_key)
    assert signer.deserialize_compact(signed, valid_key)["payload"] == payload


def real_litellm(monkeypatch):
    sdk = importlib.import_module("litellm")
    monkeypatch.setattr(sdk, "telemetry", False)
    monkeypatch.setattr(sdk, "suppress_debug_info", True)
    monkeypatch.setattr(sdk, "callbacks", [])
    monkeypatch.setattr(sdk, "success_callback", [])
    monkeypatch.setattr(sdk, "failure_callback", [])
    return sdk


async def completion(sdk, transport):
    from openai import AsyncOpenAI

    async with AsyncOpenAI(
        api_key=TEST_KEY,
        base_url=API_BASE,
        http_client=httpx.AsyncClient(transport=transport, trust_env=False),
        max_retries=0,
    ) as client:
        return await sdk.acompletion(
            model="openai/sdk-contract-fixture",
            messages=[{"role": "user", "content": "Return a fixture JSON object."}],
            api_key=TEST_KEY,
            api_base=API_BASE,
            client=client,
            temperature=0.3,
            max_tokens=123,
            response_format={"type": "json_object"},
            num_retries=0,
            timeout=2.0,
        )


@pytest.mark.asyncio
async def test_litellm_real_openai_compatible_request_and_response(monkeypatch):
    sdk = real_litellm(monkeypatch)
    calls = []

    def handler(outgoing):
        calls.append(outgoing)
        assert str(outgoing.url) == f"{API_BASE}/chat/completions"
        assert outgoing.method == "POST"
        body = json.loads(outgoing.content)
        assert body["model"] == "sdk-contract-fixture"
        assert body["temperature"] == 0.3
        assert body["max_tokens"] == 123
        assert body["response_format"] == {"type": "json_object"}
        assert "num_retries" not in body
        return httpx.Response(
            200,
            json={
                "id": "fixture-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "sdk-contract-fixture",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"ok":true}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    result = await completion(sdk, httpx.MockTransport(handler))
    assert len(calls) == 1
    assert result.choices[0].message.content == '{"ok":true}'
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 429])
async def test_litellm_real_error_shape_and_zero_sdk_retries(monkeypatch, status):
    sdk = real_litellm(monkeypatch)
    calls = []

    def handler(outgoing):
        calls.append(outgoing)
        return httpx.Response(
            status,
            headers={"retry-after": "0"},
            json={"error": {"message": "fixture rejection", "type": "invalid_request_error", "code": "fixture_error"}},
        )

    error_type = sdk.BadRequestError if status == 400 else sdk.RateLimitError
    with pytest.raises(error_type) as error:
        await completion(sdk, httpx.MockTransport(handler))
    assert error.value.status_code == status
    assert error.value.llm_provider == "openai"
    assert len(calls) == 1
