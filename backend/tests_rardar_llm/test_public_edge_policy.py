"""Static policy contract, not a substitute for nginx -t or live auth checks."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "deploy/nginx/rardar-public-edge-map.conf"
SITE = ROOT / "deploy/nginx/rardar-public-reading-site.conf"


def edge_realm(method: str, uri: str) -> str:
    # This intentionally small config uses anchored PCRE/Python-compatible
    # expressions, no captures, includes, variable destinations or wildcards.
    patterns = re.findall(r"^\s*~(\^\S+\$) off;\s*$", POLICY.read_text(encoding="utf-8"), re.MULTILINE)
    assert patterns
    return "off" if any(re.fullmatch(pattern, f"{method}:{uri}") for pattern in patterns) else "Rardar"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/"),
        ("HEAD", "/historical-hot"),
        ("GET", "/find"),
        ("GET", "/activity"),
        ("GET", "/login"),
        ("GET", "/news"),
        ("GET", "/discover"),
        ("GET", "/candidates"),
        ("GET", "/watchlist"),
        ("GET", "/_next/static/chunks/app/find/page.js"),
        ("GET", "/_next/static/chunks/app/project/stable/[projectId]/page-abc.js"),
        ("GET", "/project/stable/first-public-project--abcdef"),
        ("GET", "/project/github/123"),
        ("GET", "/api/v1/rardar/trending-today"),
        ("GET", "/api/v1/rardar/historical-hot"),
        ("GET", "/api/v1/rardar/trending-projects/project--abc"),
        ("GET", "/api/v1/rardar/historical-projects/project--abc"),
        ("GET", "/api/v1/rardar/project-insights/project--abc"),
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/rardar/find-runs"),
        ("GET", "/api/v1/rardar/find-runs/private-run"),
        ("GET", "/api/v1/rardar/find-runs/by-key/private-key"),
        ("POST", "/api/v1/rardar/find-runs"),
        ("POST", "/api/v1/rardar/find-runs/private-run/execute"),
        ("POST", "/api/v1/rardar/find-projects"),
        ("POST", "/api/v1/rardar/project-insights/project--abc"),
        ("POST", "/api/v1/rardar/projects/explain"),
        ("POST", "/api/v1/rardar/projects/123/insight"),
    ],
)
def test_public_edge_paths_reach_application_authorization(method, path):
    assert edge_realm(method, path) == "off"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/"),
        ("DELETE", "/api/v1/rardar/find-runs/private-run"),
        ("PUT", "/api/v1/rardar/project-insights/project--abc"),
        ("GET", "/api/v1/rardar/find-runs/private-run/execute"),
        ("GET", "/api/v1/rardar/find-runs/by-key/key/extra"),
        ("GET", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/send-code"),
        ("GET", "/api/v1/auth/oauth/providers"),
        ("GET", "/api/v1/auth/oauth/github/login"),
        ("GET", "/oauth/callback"),
        ("GET", "/admin"),
        ("GET", "/admin/settings"),
        ("GET", "/api/v1/settings/feature-flags"),
        ("GET", "/api/v1/contents"),
        ("POST", "/api/v1/rardar/today/operations"),
        ("POST", "/api/v1/rardar/discover/operations"),
        ("POST", "/api/v1/rardar/discover/projects/123/insight"),
        ("GET", "/metrics"),
        ("GET", "/dashboard"),
        ("GET", "/openapi.json"),
        ("GET", "/api/v1/unknown"),
        ("GET", "/api/health"),
        ("GET", "/project/stable/%2fadmin"),
        ("GET", "/project/stable/%252fadmin"),
        ("GET", "/project/stable/..\\admin"),
        ("GET", "/api/v1/rardar/project-insights/%2e%2e"),
        ("GET", "/api/v1/rardar/project-insights/%252e%252e"),
        ("GET", "/api/v1/rardar/find-runs/by-key/%252fcontents"),
        ("GET", "/_next/static/%252e%252e/api/v1/contents"),
        ("GET", "/_next/static/..\\..\\api\\v1\\contents"),
    ],
)
def test_unlisted_or_management_routes_retain_edge_protection(method, path):
    assert edge_realm(method, path) == "Rardar"


def test_fixed_vhost_retains_transport_limits_and_private_fallback():
    value = SITE.read_text(encoding="utf-8")
    assert "auth_basic $rardar_access_realm;" in value
    assert 'proxy_set_header Authorization "";' in value
    assert "limit_req zone=rardar_general burst=40 nodelay;" in value
    assert "proxy_read_timeout 300s;" in value
    assert "proxy_pass http://127.0.0.1:13000;" in value
    assert "server_name rardar.dokitool.com;" in value
    assert not re.search(r"location\s+(?:\^~\s+)?/api/", value)
