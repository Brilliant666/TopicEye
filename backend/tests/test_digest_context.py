from datetime import date, timedelta

import pytest

from app.services import digest_context


class FailingDb:
    async def execute(self, *args, **kwargs):
        raise AssertionError("digest context should not query SQLAlchemy for analytical reads")


@pytest.mark.asyncio
async def test_fetch_analyzed_content_uses_duckdb_only(monkeypatch):
    expected = [
        {
            "id": 1,
            "title": "DuckDB 摘要上下文样本",
            "category": "AI",
            "source_name": "测试信源",
            "creator_score": 80,
            "viral_score": 70,
            "quality_score": 75,
            "risk_score": 10,
            "curation_score": 82,
        }
    ]
    calls = []

    def fake_query_content_for_weekly(start_date: str, end_date: str):
        calls.append((start_date, end_date))
        return expected

    monkeypatch.setattr(digest_context, "query_content_for_weekly", fake_query_content_for_weekly)

    result = await digest_context.fetch_analyzed_content(FailingDb(), "2026-06-01", "2026-06-07")

    assert result == expected
    assert calls == [("2026-06-01", "2026-06-07")]


@pytest.mark.asyncio
async def test_fetch_analyzed_content_propagates_duckdb_errors(monkeypatch):
    def fail_query_content_for_weekly(start_date: str, end_date: str):
        raise RuntimeError("duckdb unavailable")

    monkeypatch.setattr(digest_context, "query_content_for_weekly", fail_query_content_for_weekly)

    with pytest.raises(RuntimeError, match="duckdb unavailable"):
        await digest_context.fetch_analyzed_content(FailingDb(), "2026-06-01", "2026-06-07")


@pytest.mark.asyncio
async def test_fetch_analyzed_content_expands_window_without_db_fallback(monkeypatch):
    calls = []
    end_date = date(2026, 6, 30)
    expanded_start = (end_date - timedelta(days=29)).isoformat()
    expected = [{"id": 2, "title": "扩展窗口样本", "category": "产品"}]

    def fake_query_content_for_weekly(start_date: str, end_date: str):
        calls.append((start_date, end_date))
        return [] if len(calls) == 1 else expected

    monkeypatch.setattr(digest_context, "query_content_for_weekly", fake_query_content_for_weekly)

    result = await digest_context.fetch_analyzed_content_with_expanded_window(
        FailingDb(),
        "2026-06-01",
        "2026-06-30",
        expanded_days=30,
    )

    assert result == expected
    assert calls == [
        ("2026-06-01", "2026-06-30"),
        (expanded_start, "2026-06-30"),
    ]


def test_build_items_text_prefers_adjusted_score_for_digest_prompt():
    text = digest_context.build_items_text(
        [
            {
                "title": "反馈提升后的选题",
                "category": "AI",
                "source_name": "测试信源",
                "curation_score": 70,
                "adjusted_score": 73,
                "creator_score": 68,
                "viral_score": 66,
                "quality_score": 72,
                "risk_score": 10,
            }
        ]
    )

    assert "精选:73" in text
