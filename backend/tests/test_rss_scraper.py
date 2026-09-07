"""RSS scraper 单测: 聚焦 arXiv 摘要前缀清理。

arXiv RSS 的 <description> 带 'arXiv:XXXX.NNNNN Announce Type: new\nAbstract: '
固定前缀，清理后 LLM 才能拿到干净摘要做分类/评分。
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from app.services.scrapers.rss import RSSScraper, _clean_summary


def test_clean_arxiv_prefix_new():
    """arXiv 'new' 类型: 前缀被清理，保留真实摘要。"""
    raw = (
        "arXiv:2606.26155v1 Announce Type: new \n"
        "Abstract: We focus on detecting and steering away from sycophancy "
        "in language models. Code & Data: https://example.com"
    )
    cleaned = _clean_summary(raw)
    assert cleaned.startswith("We focus on detecting")
    assert "arXiv:" not in cleaned
    assert "Announce Type" not in cleaned
    assert "Abstract:" not in cleaned


def test_clean_arxiv_prefix_cross_list():
    """arXiv 'cross-list' 类型前缀同样被清理。"""
    raw = (
        "arXiv:2606.26164v1 Announce Type: cross-list \n"
        "Abstract: Finding all modes of a multimodal black-box function."
    )
    cleaned = _clean_summary(raw)
    assert cleaned == "Finding all modes of a multimodal black-box function."


def test_clean_preserves_non_arxiv_summary():
    """普通 RSS 摘要(无 arXiv 前缀)原样保留。"""
    raw = "这是一篇关于 AI 发展的深度分析文章。"
    assert _clean_summary(raw) == raw


def test_clean_empty_and_whitespace():
    """空字符串安全返回。纯空白会被 strip(无前缀时正则不匹配但 strip 生效)。"""
    assert _clean_summary("") == ""
    # 纯空白: 正则不匹配, 但 .strip() 会清掉, 符合预期
    assert _clean_summary("   ") == ""


def test_clean_arxiv_no_abstract_section():
    """arXiv 前缀但没有 Abstract: 行的异常格式 —— 原样保留(正则不匹配)。"""
    raw = "arXiv:2606.26155v1 Announce Type: new (no abstract body)"
    # 没有 'Abstract:' 分隔，正则不匹配，原样返回
    assert _clean_summary(raw) == raw.strip()


def test_clean_arxiv_preserves_latex():
    """arXiv 摘要中的 LaTeX 符号(如 \\chisao{})不被破坏。"""
    raw = (
        "arXiv:2606.26164v1 Announce Type: new \n"
        "Abstract: We introduce \\chisao{} (Convergence-Halt-Invert-Stick-And-Oscillate)."
    )
    cleaned = _clean_summary(raw)
    assert "\\chisao{}" in cleaned
    assert cleaned.startswith("We introduce")


@pytest.mark.asyncio
async def test_truthful_timestamp_mode_keeps_published_updated_and_fetch_time_separate():
    atom = """<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Example</title>
      <entry>
        <title>Updated only</title>
        <link href="https://example.com/updated-only" />
        <id>updated-only</id>
        <updated>2026-09-08T01:02:03Z</updated>
        <summary>Concrete change details.</summary>
      </entry>
      <entry>
        <title>No timestamp</title>
        <link href="https://example.com/no-time" />
        <id>no-time</id>
        <summary>Another concrete change.</summary>
      </entry>
    </feed>"""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=atom, request=request)

    scraper = RSSScraper("https://example.com/feed.xml", {"preserve_feed_timestamps": True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        entries = await scraper.fetch(client)

    assert entries[0]["published_at"] is None
    assert entries[0]["updated_at"] == datetime(2026, 9, 8, 1, 2, 3, tzinfo=UTC)
    assert entries[1]["published_at"] is None
    assert entries[1]["updated_at"] is None


@pytest.mark.asyncio
async def test_rss_scraper_marks_304_without_clearing_saved_content_contract():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"feed-v1"'
        return httpx.Response(304, request=request)

    scraper = RSSScraper("https://example.com/feed.xml", {"preserve_feed_timestamps": True})
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"If-None-Match": '"feed-v1"'},
    ) as client:
        entries = await scraper.fetch(client)

    assert entries == []
    assert scraper.not_modified is True
