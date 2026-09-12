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


def _with_rows(rows):
    wire = '34:{"initialData":' + json.dumps(rows) + "}"
    return trendshift(len(rows)) + "<script>self.__next_f.push(" + json.dumps([1, wire]) + ")</script>"


def _source_row(index=0, source_date="2026-09-12", rank=None):
    return {
        "full_name": f"owner/repo{index}",
        "rank": index + 1 if rank is None else rank,
        "date": source_date + "T00:00:00Z",
        "repository_stars": 5000,
        "repository_stars_gained": 17,
        "repository_id": index + 42,
    }


def test_daily_fallback_preserves_actual_day_and_does_not_claim_target_complete():
    result = boards.parse_board(
        "trendshift",
        _with_rows([_source_row()]),
        fetched_at=datetime(2026, 9, 12, 1, tzinfo=UTC),
        target_date="2026-09-11",
    )
    assert result["sourceDate"] == "2026-09-12"
    assert result["targetPeriodDate"] == "2026-09-11"
    assert result["acquisitionMode"] == "daily_snapshot"
    assert result["historicalDateFetchSupported"] is False
    assert result["periodStartAt"] == "2026-09-12T00:00:00+00:00"
    assert result["periodEndAt"] == "2026-09-13T00:00:00+00:00"
    assert result["sourceTimezone"] == "UTC"
    assert result["entries"][0]["trendshiftStarsGained"] == 17
    assert "not a verified final historical day" in result["sourceDateNote"]


def test_github_target_never_becomes_source_day_or_known_exact_window():
    result = boards.parse_board("github", github(), target_date="2026-09-11")
    assert result["targetPeriodDate"] == "2026-09-11"
    assert result["sourceDate"] is None
    assert "periodStartAt" not in result
    assert result["acquisitionMode"] == "daily_snapshot"


def test_mixed_historical_ranks_or_dates_with_current_metrics_rejected():
    with pytest.raises(boards.BoardParseError, match="mixed_source_dates"):
        boards.parse_board("trendshift", _with_rows([_source_row(), _source_row(1, "2026-09-11")]))
    with pytest.raises(boards.BoardParseError, match="source_rank_disagreement"):
        boards.parse_board("trendshift", _with_rows([_source_row(rank=2)]))


@pytest.mark.parametrize("value", ["2026-09-31", "2026-9-1", "../../secret", "2026-09-11?x=1"])
def test_target_date_is_a_calendar_identifier_not_an_arbitrary_endpoint(value):
    with pytest.raises(ValueError):
        boards.parse_board("github", github(), target_date=value)


def test_public_date_action_discovery_is_named_bounded_and_same_origin():
    chunks = [f"/_next/static/chunks/chunk{i}.js" for i in range(7)]
    wire = "36:I" + json.dumps([77910, chunks, "default"]) + '\n37:["$","$L36",null,{"initialData":[]}]'
    html = "<script>self.__next_f.push(" + json.dumps([1, wire]) + ")</script>"
    assert boards._date_action_assets(html) == ["https://trendshift.io" + path for path in reversed(chunks[-4:])]
    action = "a" * 40
    script = f'(0,m.createServerReference)("{action}",m.callServer,void 0,m.findSourceMapURL,"getRepositoryRecommendationsByDate")'
    assert boards._date_action_id(script) == action
    assert (
        boards._date_action_id(script.replace("getRepositoryRecommendationsByDate", "setRepositoryMarkAction")) is None
    )
    assert boards._date_action_assets(html.replace("/_next/static/chunks/chunk6.js", "https://evil.test/data.js")) == [
        "https://trendshift.io" + path for path in reversed(chunks[3:6])
    ]


def _dated_wire(rows):
    return '0:{"a":"$@1"}\n1:' + json.dumps(rows)


def test_date_response_binds_all_rows_and_metrics_to_ended_period():
    result = boards.parse_trendshift_date_response(
        _dated_wire([_source_row(0, "2026-09-11"), _source_row(1, "2026-09-11")]),
        target_date="2026-09-11",
        fetched_at=datetime(2026, 9, 12, 1, tzinfo=UTC),
    )
    assert result["acquisitionMode"] == "ended_utc_day"
    assert result["sourceDate"] == "2026-09-11"
    assert result["periodEndAt"] == "2026-09-12T00:00:00+00:00"
    assert len(result["entries"]) == 2
    for row in result["entries"]:
        assert row["sourceDate"] == "2026-09-11"
        assert row["trendshiftStarsGained"] == 17


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda r: r.update(date="2026-09-12T00:00:00Z"), "source_date_mismatch"),
        (lambda r: r.update(rank=2), "invalid_rank_sequence"),
        (lambda r: r.update(repository_stars_gained="2.2k"), "invalid_date_metrics"),
    ],
)
def test_date_response_rejects_wrong_day_rank_or_metric(mutation, error):
    row = _source_row(0, "2026-09-11")
    mutation(row)
    with pytest.raises(boards.BoardParseError, match=error):
        boards.parse_trendshift_date_response(
            _dated_wire([row]), target_date="2026-09-11", fetched_at=datetime(2026, 9, 12, tzinfo=UTC)
        )


@pytest.mark.asyncio
async def test_fetch_exact_date_uses_observed_named_action_and_no_alternative_endpoint(monkeypatch):
    wire = (
        "36:I"
        + json.dumps([77910, ["/_next/static/chunks/date.js"], "default"])
        + '\n37:["$","$L36",null,{"initialData":[]}]'
    )
    html = trendshift(1) + "<script>self.__next_f.push(" + json.dumps([1, wire]) + ")</script>"
    calls = []

    def transport(request):
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            assert str(request.url) == "https://trendshift.io/"
            assert json.loads(request.content) == ["2026-09-11", "all"]
            assert request.headers["next-action"] == "a" * 40
            return httpx.Response(
                200, text=_dated_wire([_source_row(0, "2026-09-11")]), headers={"content-type": "text/x-component"}
            )
        if request.url.path.endswith(".js"):
            return httpx.Response(
                200,
                text='(0,m.createServerReference)("'
                + "a" * 40
                + '",m.callServer,void 0,m.findSourceMapURL,"getRepositoryRecommendationsByDate")',
                headers={"content-type": "application/javascript"},
            )
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    monkeypatch.setattr(
        boards,
        "build_scraper_client_kwargs",
        lambda *a, **k: {"transport": httpx.MockTransport(transport), "headers": {}},
    )
    result = await boards.fetch_board("trendshift", target_date="2026-09-11")
    assert result["status"] == "healthy"
    assert result["acquisitionMode"] == "ended_utc_day"
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_unsupported_calendar_is_honest_snapshot_not_infinite_retry(monkeypatch):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, text=_with_rows([_source_row()]), headers={"content-type": "text/html"})

    monkeypatch.setattr(
        boards,
        "build_scraper_client_kwargs",
        lambda *a, **k: {"transport": httpx.MockTransport(transport), "headers": {}},
    )
    result = await boards.fetch_board("trendshift", target_date="2026-09-11")
    assert result["status"] == "healthy"
    assert result["sourceDate"] == "2026-09-12"
    assert result["targetPeriodDate"] == "2026-09-11"
    assert result["acquisitionMode"] == "daily_snapshot"
    assert result["historicalDateFetchSupported"] is False
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_http_200_wrong_date_does_not_become_success_or_snapshot_fallback(monkeypatch):
    async def wrong_date(client, html, target_date):
        return boards.parse_trendshift_date_response(
            _dated_wire([_source_row(0, "2026-09-10")]),
            target_date=target_date,
            fetched_at=datetime(2026, 9, 12, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(boards, "_fetch_ended_trendshift", wrong_date)
    monkeypatch.setattr(
        boards,
        "build_scraper_client_kwargs",
        lambda *a, **k: {
            "transport": httpx.MockTransport(
                lambda r: httpx.Response(200, text=trendshift(), headers={"content-type": "text/html"})
            ),
            "headers": {},
        },
    )
    result = await boards.fetch_board("trendshift", target_date="2026-09-11")
    assert result["status"] == "failed"
    assert result["errorCode"] == "source_date_mismatch"
    assert result["entries"] == []
    assert result["fetchedAt"] is None
    assert result["checkedAt"] is not None


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
