"""Host-restricted GitHub client for Rardar's public project materials."""

import httpx
from pydantic import SecretStr


def github_material_client(token: SecretStr) -> httpx.AsyncClient:
    credential = token.get_secret_value().strip()
    if any(character.isspace() for character in credential):
        raise ValueError("rardar_github_token_invalid")

    async def authorize(request: httpx.Request) -> None:
        # Check every request, including absolute URLs and explicit redirect
        # overrides. Never attach a project credential to a source-provided URL.
        url = request.url
        if url.scheme != "https" or url.host != "api.github.com" or url.port not in (None, 443) or url.userinfo:
            raise ValueError("rardar_github_origin_not_allowed")
        request.headers.pop("Authorization", None)
        if credential:
            request.headers["Authorization"] = f"Bearer {credential}"

    return httpx.AsyncClient(
        base_url="https://api.github.com",
        timeout=12,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "TopicEye-Rardar/2.0"},
        event_hooks={"request": [authorize]},
    )
