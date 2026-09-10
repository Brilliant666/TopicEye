"""Pure public board contracts: no database or Provider calls."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.rardar import trending_boards as boards


def github(count=2):
    return "".join(
        f'<article class="Box-row"><h2><a href="/owner/repo{i}">repo</a></h2>'
        f'<p>Actual description {i}</p><a href="/owner/repo{i}/stargazers">1,234</a>'
        "<span>12 stars today</span></article>"
        for i in range(count)
    )


def trendshift(count=2):
    listing = {
        "@type": "ItemList",
        "name": "Live trending repositories daily",
        "url": "https://trendshift.io",
        "numberOfItems": count,
        "itemListElement": [
            {
                "position": i + 1,
                "url": f"https://trendshift.io/repositories/{i}",
                "item": {
                    "@type": "SoftwareSourceCode",
                    "name": f"owner/repo{i}",
                    "codeRepository": f"https://github.com/owner/repo{i}",
                    "dateModified": "2020-01-01",
                },
            }
            for i in range(count)
        ],
    }
    cards = "".join(
        f'<div><div><div><a href="/repositories/{i}">owner/repo{i}</a></div>'
        '</div><span><svg class="lucide-star"></svg>2.2k</span></div>'
        for i in range(count)
    )
    return f'<script type="application/ld+json">{json.dumps(listing)}</script>{cards}'


def test_github_full_scope_and_reported_delta_not_exact_window():
    result = boards.parse_board("github", github(31), fetched_at=datetime(2026, 9, 10, tzinfo=UTC))
    assert len(result["entries"]) == 31
    assert result["sourceDate"] is None
    assert result["captureDate"] == "2026-09-10"
    assert result["entries"][0]["totalStars"] == 1234
    assert result["entries"][0]["reportedDeltaPeriod"] == "GitHub reported stars today"


def test_trendshift_own_list_excludes_ads_preserves_rounded_unknown():
    html = trendshift(28) + '<a href="https://github.com/ad/sponsor">Featured</a>'
    result = boards.parse_board("trendshift", html)
    assert len(result["entries"]) == 28
    assert result["sourceDate"] is None
    assert result["entries"][0]["totalStars"] is None
    assert result["entries"][0]["trendshiftStarsGainedLabel"] == "2.2k"
    assert result["entries"][0]["reportedDelta"] is None


def test_hydration_date_and_metrics_not_repository_modified_or_github_delta():
    data = [
        {
            "full_name": "owner/repo0",
            "rank": 1,
            "date": "2026-09-10T00:00:00Z",
            "repository_stars": 5000,
            "repository_stars_gained": 2200,
            "repository_id": 42,
        }
    ]
    wire = '34:{"initialData":' + json.dumps(data) + "}"
    script = "<script>self.__next_f.push(" + json.dumps([1, wire]) + ")</script>"
    result = boards.parse_board("trendshift", trendshift(1) + script)
    assert result["sourceDate"] == "2026-09-10"
    assert result["entries"][0]["totalStars"] == 5000
    assert result["entries"][0]["trendshiftStarsGained"] == 2200
    assert "githubRepositoryId" not in result["entries"][0]


@pytest.mark.parametrize("source,html", [("github", ""), ("trendshift", ""), ("trendshift", trendshift(0))])
def test_empty_or_unrecognized_is_failure_not_empty_success(source, html):
    with pytest.raises(boards.BoardParseError):
        boards.parse_board(source, html)


def test_trendshift_github_mirror_not_second_board():
    with pytest.raises(boards.BoardParseError, match="own_daily"):
        boards.parse_trendshift(
            trendshift().replace('"https://trendshift.io"', '"https://trendshift.io/github-trending"')
        )


def test_hidden_entry_or_inconsistent_count_fails_closed():
    with pytest.raises(boards.BoardParseError, match="source_count"):
        boards.parse_trendshift(trendshift().replace('"numberOfItems": 2', '"numberOfItems": 3'))
    with pytest.raises(boards.BoardParseError, match="visible_board"):
        boards.parse_trendshift(trendshift().replace('href="/repositories/1"', 'href="/other/1"'))


def test_invalid_repository_and_duplicate_rejected():
    with pytest.raises(boards.BoardParseError):
        boards.parse_github(github().replace("owner/repo0", "owner/.."))
    with pytest.raises(boards.BoardParseError, match="duplicate"):
        boards.parse_github(github().replace("repo1", "repo0"))


@pytest.mark.asyncio
async def test_fetch_single_failure_and_recovery(monkeypatch):
    def transport(request):
        if request.url.host == "github.com":
            return httpx.Response(200, text=github(), headers={"content-type": "text/html"})
        return httpx.Response(503)

    monkeypatch.setattr(
        boards,
        "build_scraper_client_kwargs",
        lambda *args, **kwargs: {"transport": httpx.MockTransport(transport), "headers": {}},
    )
    result = await boards.fetch_boards()
    assert [row["status"] for row in result] == ["healthy", "failed"]
    assert result[1]["errorCode"] == "HTTPStatusError"
    monkeypatch.setattr(
        boards,
        "build_scraper_client_kwargs",
        lambda *args, **kwargs: {
            "transport": httpx.MockTransport(
                lambda request: httpx.Response(200, text=trendshift(), headers={"content-type": "text/html"})
            ),
            "headers": {},
        },
    )
    assert (await boards.fetch_board("trendshift"))["status"] == "healthy"


@pytest.mark.asyncio
async def test_real_client_guard_rejects_reserved_dns_without_request(monkeypatch):
    from app.utils import url_safety

    async def private_dns(host):
        return ["127.0.0.1"]

    monkeypatch.setattr(url_safety, "_resolve_host", private_dns)
    result = await boards.fetch_board("github")
    assert result["status"] == "failed"
    assert result["errorCode"] == "UnsafeUrlError"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,headers,body,expected",
    [
        (302, {"location": "http://127.0.0.1/"}, "", "HTTPStatusError"),
        (200, {"content-type": "application/json"}, "{}", "unexpected_content_type"),
        (200, {"content-type": "text/html"}, "x" * 101, "source_response_too_large"),
    ],
)
async def test_redirect_type_and_size_guard(monkeypatch, status, headers, body, expected):
    monkeypatch.setattr(boards, "_MAX_BYTES", 100)
    calls = []

    def transport(request):
        calls.append(request.url)
        return httpx.Response(status, text=body, headers=headers)

    monkeypatch.setattr(
        boards,
        "build_scraper_client_kwargs",
        lambda *args, **kwargs: {"transport": httpx.MockTransport(transport), "headers": {}, "follow_redirects": False},
    )
    result = await boards.fetch_board("github")
    assert result["errorCode"] == expected
    assert len(calls) == 1


def test_history_proves_appearance_without_fabricating_date_or_rank():
    row = {
        "full_name": "owner/repo",
        "repository_id": 8,
        "featured_count": 23,
        "watchers": 4000,
        "description": "A real project",
        "updated_at": "2026-01-01",
    }
    wire = '32:{"repositories":' + json.dumps([row]) + "}"
    html = '<h1>GitHub trending repositories</h1><div><div><div><a href="/repositories/8">owner/repo</a></div></div><p>Featured on GitHub Trending 23 times of all days</p></div>'
    html += "<script>self.__next_f.push(" + json.dumps([1, wire]) + ")</script>"
    result = boards.parse_history_page(html)
    assert result["period"] == "historical-all-days"
    assert result["sourceDate"] is None
    assert result["entries"][0]["rank"] is None
    assert result["entries"][0]["reportedAppearanceCount"] == 23
    with pytest.raises(boards.BoardParseError, match="history_count_not_visible"):
        boards.parse_history_page(html.replace("23 times", "22 times"))
