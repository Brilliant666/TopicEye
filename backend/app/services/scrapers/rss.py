"""
RSS / Atom feed scraper.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from . import BaseScraper, fetch_feed_with_retry, register_scraper

logger = logging.getLogger(__name__)

# arXiv RSS 的 <description> 带 'arXiv:XXXX.NNNNN Announce Type: new\nAbstract: '
# 固定前缀，并非真正的摘要。清理掉让 LLM 拿到干净摘要。
# 很多 RSS 源的 description 都带类似模板前缀，这是通用清理，不只服务 arXiv。
_ARXIV_PREFIX_RE = re.compile(r"^arXiv:\S+\s+Announce Type:\s*\S+\s*\n?Abstract:\s*", re.IGNORECASE)


def _clean_summary(text: str) -> str:
    """清理 RSS summary 中的模板前缀（如 arXiv 的 announce 行）。"""
    if not text:
        return text
    return _ARXIV_PREFIX_RE.sub("", text, count=1).strip()


@register_scraper("RSS")
class RSSScraper(BaseScraper):
    """Fetch and parse RSS/Atom feeds."""

    async def fetch(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        self.not_modified = False
        resp = await fetch_feed_with_retry(
            client,
            self.url,
            context=f"RSS {self.url}",
        )
        if resp is None:
            logger.warning("RSS feed exhausted retries, returning empty: %s", self.url)
            # 保留空列表降级契约，但打标记让 pipeline 把失败落到信源状态面
            self.fetch_degraded = True
            return []
        # Capture conditional request state so the pipeline can persist it on
        # the Source row and send If-None-Match / If-Modified-Since next time.
        self._latest_etag = resp.headers.get("etag")
        self._latest_last_modified = resp.headers.get("last-modified")
        self._latest_content_type = resp.headers.get("content-type")

        if resp.status_code == 304:
            logger.info("RSS feed not modified: %s", self.url)
            self.not_modified = True
            return []

        feed = feedparser.parse(resp.text)
        entries: list[dict[str, Any]] = []
        preserve_feed_timestamps = self.config.get("preserve_feed_timestamps") is True

        for entry in feed.entries:
            published = entry.get("published_parsed")
            updated = entry.get("updated_parsed")
            if preserve_feed_timestamps:
                # Hotspot News exposes the feed's actual published/updated
                # facts separately.  Missing publication time must remain
                # unknown instead of being replaced with fetch time.
                published_at = datetime(*published[:6], tzinfo=UTC) if published else None
                updated_at = datetime(*updated[:6], tzinfo=UTC) if updated else None
            else:
                # Preserve the established generic ingestion contract.  The
                # dedicated news path opts into truthful split timestamps.
                effective = published or updated
                published_at = datetime(*effective[:6]) if effective else datetime.now(UTC)
                updated_at = None

            entries.append(
                {
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "author": entry.get("author", ""),
                    "summary": _clean_summary(entry.get("summary", "")),
                    "raw_content": (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else ""),
                    "tags": [tag.get("term", "") for tag in entry.get("tags", [])],
                    "published_at": published_at,
                    "updated_at": updated_at,
                }
            )

        return entries
